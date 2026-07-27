"""
FiscAudit AI - Document Extraction Engine (PRODUCTION-READY)

Extracts financial data from PDF documents using Google Gemini 1.5 Pro vision model.
Features:
  - Strict Pydantic v2 validation (ConfigDict strict mode)
  - Comprehensive error handling with retries
  - Multiple JSON parsing fallbacks
  - Audit logging for compliance
  - Type hints throughout
"""

import asyncio
import json
import base64
import logging
import re
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationError
import google.generativeai as genai


logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC MODELS (STRICT VALIDATION)
# ============================================================================

class BankBalance(BaseModel):
    """Bank account balance information with strict validation."""
    
    model_config = ConfigDict(
        strict=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "account_number": "NL12ABNA0123456789",
                "bank_name": "ABN AMRO",
                "balance_eur": 50000.0,
                "currency": "EUR"
            }
        }
    )
    
    account_number: str = Field(
        ...,
        min_length=2,
        max_length=34,
        description="IBAN or account number (max 34 chars)"
    )
    bank_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name of the bank"
    )
    balance_eur: float = Field(
        ...,
        gt=0,
        description="Account balance in EUR (must be positive)"
    )
    currency: str = Field(
        default="EUR",
        pattern="^[A-Z]{3}$",
        description="ISO 4217 currency code"
    )

    @field_validator('balance_eur')
    @classmethod
    def validate_balance(cls, v: float) -> float:
        """Round balance to 2 decimals and check reasonableness."""
        if v > 1e10:  # > €10 billion is unrealistic
            raise ValueError(f"Balance exceeds maximum reasonable value: €{v:,.2f}")
        if v < 0.01:
            raise ValueError("Balance must be at least €0.01")
        return round(v, 2)


class MortgageInfo(BaseModel):
    """Mortgage loan information with strict validation."""
    
    model_config = ConfigDict(
        strict=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "principal_eur": 300000.0,
                "current_balance_eur": 250000.0,
                "interest_rate_pct": 2.5,
                "monthly_payment_eur": 1200.0,
                "loan_type": "hypotheek"
            }
        }
    )
    
    principal_eur: float = Field(..., gt=0, description="Original loan amount")
    current_balance_eur: float = Field(..., ge=0, description="Current outstanding balance")
    interest_rate_pct: float = Field(..., ge=0, le=20, description="Annual interest rate (0-20%)")
    monthly_payment_eur: float = Field(..., gt=0, description="Monthly payment amount")
    loan_type: str = Field(default="hypotheek", description="Type of loan (hypotheek, persoonlijk, etc.)")

    @field_validator('current_balance_eur')
    @classmethod
    def validate_balance_vs_principal(cls, v: float, info) -> float:
        """Validate current balance doesn't exceed principal (with 10% tolerance)."""
        data = info.data
        if 'principal_eur' in data:
            max_allowed = data['principal_eur'] * 1.1
            if v > max_allowed:
                raise ValueError(
                    f"Current balance (€{v:,.2f}) exceeds principal "
                    f"(€{data['principal_eur']:,.2f})"
                )
        return round(v, 2)


class BusinessIncome(BaseModel):
    """Business/self-employment income information."""
    
    model_config = ConfigDict(
        strict=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "gross_income_eur": 150000.0,
                "deductible_expenses_eur": 50000.0,
                "net_profit_eur": 100000.0
            }
        }
    )
    
    gross_income_eur: float = Field(..., gt=0, description="Total business income")
    deductible_expenses_eur: float = Field(..., ge=0, description="Deductible business expenses")
    net_profit_eur: float = Field(..., description="Net profit after deductions")

    @field_validator('net_profit_eur')
    @classmethod
    def validate_net_profit(cls, v: float, info) -> float:
        """Validate net profit approximately equals gross - deductions."""
        data = info.data
        if 'gross_income_eur' in data and 'deductible_expenses_eur' in data:
            expected = data['gross_income_eur'] - data['deductible_expenses_eur']
            tolerance = expected * 0.02  # 2% tolerance for rounding
            difference = abs(v - expected)
            
            if difference > tolerance:
                logger.warning(
                    f"Net profit mismatch: actual €{v:,.2f}, "
                    f"expected €{expected:,.2f} (diff: €{difference:,.2f})"
                )
        return round(v, 2)


class PropertyInfo(BaseModel):
    """Real estate property information."""
    
    model_config = ConfigDict(
        strict=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "address": "Straat 1, Amsterdam, Netherlands",
                "woz_value_eur": 500000.0,
                "year_valued": 2024,
                "ownership_pct": 100.0
            }
        }
    )
    
    address: str = Field(..., min_length=5, description="Property address (street, city)")
    woz_value_eur: float = Field(..., gt=0, description="WOZ valuation in EUR")
    year_valued: int = Field(
        ...,
        ge=2000,
        le=datetime.now().year,
        description="Year of WOZ valuation"
    )
    ownership_pct: float = Field(
        default=100.0,
        ge=1,
        le=100,
        description="Ownership percentage (1-100%)"
    )

    @field_validator('woz_value_eur')
    @classmethod
    def validate_woz_value(cls, v: float) -> float:
        """Validate WOZ is realistic for Netherlands."""
        if v > 1e7:  # > €10 million is unrealistic for NL
            raise ValueError(f"WOZ value exceeds reasonable maximum: €{v:,.0f}")
        return round(v, 0)


class ExtractedFinancialData(BaseModel):
    """Complete extracted financial data from PDF (STRICT MODE)."""
    
    model_config = ConfigDict(
        strict=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )
    
    extraction_confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Extraction confidence 0-1 (0% to 100%)"
    )
    bank_accounts: list[BankBalance] = Field(
        default_factory=list,
        description="All bank accounts found in document"
    )
    mortgages: list[MortgageInfo] = Field(
        default_factory=list,
        description="All mortgage loans found"
    )
    business_income: Optional[BusinessIncome] = Field(
        None,
        description="Business income if document contains business info"
    )
    real_estate: list[PropertyInfo] = Field(
        default_factory=list,
        description="All real estate properties found"
    )
    other_assets_eur: float = Field(
        default=0,
        ge=0,
        description="Other assets/investments value"
    )
    deductible_items_eur: float = Field(
        default=0,
        ge=0,
        description="Tax deductible items"
    )
    kia_profit_eur: float = Field(
        default=0,
        description="KIA profit (young entrepreneur deduction)"
    )
    document_type: str = Field(
        default="unknown",
        description="Type of document (WOZ_beschikking, bank_statement, etc.)"
    )

    @field_validator('extraction_confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Log warnings for low confidence extractions."""
        if v < 0.6:
            logger.warning(f"Very low extraction confidence: {v*100:.0f}%")
        elif v < 0.8:
            logger.info(f"Moderate extraction confidence: {v*100:.0f}%")
        return v


# ============================================================================
# DOCUMENT EXTRACTOR
# ============================================================================

class DocumentExtractor:
    """Extract financial data from PDFs using Gemini 1.5 Pro vision model.
    
    Features:
    - Strict Pydantic validation in strict mode
    - Retry logic with exponential backoff
    - JSON parsing with 3 fallback strategies
    - Comprehensive error handling
    - Audit logging for compliance
    
    Example:
        >>> extractor = DocumentExtractor(api_key="your-gemini-key")
        >>> data = extractor.extract_from_pdf("invoice.pdf")
        >>> print(data.bank_accounts)
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    def __init__(self, api_key: str):
        """Initialize DocumentExtractor with Gemini API key.
        
        Args:
            api_key: Google Gemini API key
            
        Raises:
            ValueError: If API key is empty or invalid
        """
        if not api_key or not api_key.strip():
            raise ValueError("Google API key cannot be empty")
        
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-1.5-pro-vision-latest")
            logger.info("DocumentExtractor initialized with Gemini 1.5 Pro")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {str(e)}")
            raise ValueError(f"Invalid API key: {str(e)}")

    def _pdf_to_base64(self, pdf_path: str) -> str:
        """Convert PDF file to base64 string for Gemini API.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Base64 encoded PDF content
            
        Raises:
            ValueError: If file doesn't exist, is empty, or not a valid PDF
        """
        try:
            with open(pdf_path, "rb") as pdf_file:
                content = pdf_file.read()
                
                # Validate PDF
                if not content:
                    raise ValueError("PDF file is empty")
                
                if not content.startswith(b"%PDF"):
                    raise ValueError("File is not a valid PDF (missing PDF header)")
                
                # Limit file size (Gemini has limits)
                if len(content) > 100_000_000:  # 100 MB limit
                    raise ValueError("PDF file is too large (max 100 MB)")
                
                return base64.b64encode(content).decode("utf-8")
                
        except FileNotFoundError:
            raise ValueError(f"PDF file not found: {pdf_path}")
        except IOError as e:
            raise ValueError(f"Error reading PDF: {str(e)}")

    def _parse_gemini_response(self, response_text: str) -> dict:
        """Parse Gemini response with multiple fallback strategies.
        
        Tries:
        1. Direct JSON parse
        2. Extract from markdown code block
        3. Extract first JSON object
        
        Args:
            response_text: Raw response from Gemini
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            ValueError: If no valid JSON found
        """
        if not response_text or not response_text.strip():
            raise ValueError("Empty response from Gemini API")

        # Strategy 1: Direct JSON parse
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.debug("Direct JSON parse failed, trying markdown extraction...")

        # Strategy 2: Extract from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            try:
                content = json_match.group(1).strip()
                return json.loads(content)
            except json.JSONDecodeError:
                logger.debug("Markdown extraction failed, trying object extraction...")

        # Strategy 3: Extract first JSON object
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            try:
                content = json_match.group(0)
                return json.loads(content)
            except json.JSONDecodeError:
                logger.debug("Object extraction failed, all strategies exhausted")

        # All strategies failed
        raise ValueError(
            f"Could not extract valid JSON from Gemini response. "
            f"Response (first 300 chars): {response_text[:300]}"
        )

    async def _extract_with_retry(self, pdf_base64: str) -> str:
        """Call Gemini API with retry logic and exponential backoff.
        
        Args:
            pdf_base64: Base64 encoded PDF content
            
        Returns:
            Raw JSON response from Gemini
            
        Raises:
            RuntimeError: If all retries fail
        """
        system_prompt = """You are an expert financial document analyzer. Extract financial data from the PDF.

CRITICAL: RESPOND WITH ONLY VALID JSON. NO MARKDOWN, NO EXPLANATIONS, NO TEXT.

Your response must be valid JSON with this exact structure:
{
    "extraction_confidence": 0.95,
    "bank_accounts": [
        {
            "account_number": "NL12ABNA0123456789",
            "bank_name": "ABN AMRO",
            "balance_eur": 50000.0,
            "currency": "EUR"
        }
    ],
    "mortgages": [
        {
            "principal_eur": 300000.0,
            "current_balance_eur": 250000.0,
            "interest_rate_pct": 2.5,
            "monthly_payment_eur": 1200.0,
            "loan_type": "hypotheek"
        }
    ],
    "business_income": null,
    "real_estate": [
        {
            "address": "Straat 1, Amsterdam",
            "woz_value_eur": 500000.0,
            "year_valued": 2024,
            "ownership_pct": 100.0
        }
    ],
    "other_assets_eur": 0.0,
    "deductible_items_eur": 5000.0,
    "kia_profit_eur": 0.0,
    "document_type": "bank_statement"
}

RULES:
1. ALL numbers must be floats/integers (not strings)
2. Dates must be YYYY-MM-DD format
3. Currency is ALWAYS EUR
4. If data not found: use 0 for amounts, empty [] for lists, null for objects
5. confidence must be 0-1
6. ownership_pct must be 1-100
"""

        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"Gemini API call (attempt {attempt+1}/{self.MAX_RETRIES})")
                
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    [
                        system_prompt,
                        {
                            "mime_type": "application/pdf",
                            "data": pdf_base64,
                        },
                    ],
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.0,  # Deterministic output
                        top_p=1.0,
                        max_output_tokens=4096,
                    ),
                )
                
                if not response or not response.text:
                    raise ValueError("Empty response from Gemini")
                
                logger.debug(f"Received response ({len(response.text)} chars)")
                return response.text

            except asyncio.TimeoutError:
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = self.RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Gemini timeout. Retrying in {wait_time}s "
                        f"({attempt+1}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise RuntimeError("Gemini API timeout after all retries")

            except Exception as e:
                error_msg = str(e)
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = self.RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Gemini error: {error_msg}. "
                        f"Retrying in {wait_time}s ({attempt+1}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise RuntimeError(f"Gemini API error: {error_msg}")

    async def extract_from_pdf_async(self, pdf_path: str) -> ExtractedFinancialData:
        """Asynchronously extract financial data from PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            ExtractedFinancialData with fully validated fields
            
        Raises:
            ValueError: If PDF is invalid
            RuntimeError: If extraction fails after retries
            ValidationError: If extracted data fails Pydantic validation
        """
        try:
            logger.info(f"Starting extraction from: {pdf_path}")
            
            # Step 1: Validate and encode PDF
            pdf_base64 = self._pdf_to_base64(pdf_path)
            logger.debug(f"PDF encoded ({len(pdf_base64)} bytes base64)")

            # Step 2: Call Gemini API with retries
            response_text = await self._extract_with_retry(pdf_base64)

            # Step 3: Parse JSON response
            response_data = self._parse_gemini_response(response_text)

            # Step 4: Strict Pydantic validation
            extracted = ExtractedFinancialData(**response_data)

            logger.info(
                f"✓ Extraction successful. Confidence: {extracted.extraction_confidence*100:.0f}%. "
                f"Accounts: {len(extracted.bank_accounts)}, "
                f"Mortgages: {len(extracted.mortgages)}, "
                f"Properties: {len(extracted.real_estate)}"
            )
            
            return extracted

        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            raise

        except ValidationError as e:
            logger.error(f"Pydantic validation error: {e.error_count()} errors")
            for error in e.errors():
                logger.error(f"  - {error['loc']}: {error['msg']}")
            raise RuntimeError(f"Data validation failed: {str(e)}")

        except RuntimeError as e:
            logger.error(f"Extraction failed: {str(e)}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {str(e)}")
            raise RuntimeError(f"PDF extraction failed: {str(e)}")

    def extract_from_pdf(self, pdf_path: str) -> ExtractedFinancialData:
        """Synchronous wrapper for extract_from_pdf_async.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            ExtractedFinancialData
            
        Raises:
            ValueError: If PDF is invalid
            RuntimeError: If extraction fails
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.extract_from_pdf_async(pdf_path))
        except Exception as e:
            logger.error(f"Sync extraction failed: {str(e)}")
            raise
        finally:
            try:
                loop.close()
            except Exception as close_err:
                logger.debug(f"Error closing event loop: {close_err}")

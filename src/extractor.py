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


from .llm_json import extract_json_object


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
        description=(
            "Account balance in EUR. No lower bound: a balance of 0.00 is normal "
            "for an emptied savings account, and a negative balance means the "
            "account is overdrawn (rood staan). A gt=0 constraint here rejected "
            "both cases and failed the entire extraction."
        ),
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
        if abs(v) > 1e10:  # > EUR 10 billion is unrealistic either way
            raise ValueError(f"Balance exceeds maximum reasonable value: EUR {v:,.2f}")
        # No lower bound. A zero balance is a normal emptied savings account and
        # a negative balance means overdrawn; rejecting either failed the whole
        # extraction on otherwise perfectly readable statements.
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
    
    # Een echte hypotheekjaaropgave vermeldt de oorspronkelijke hoofdsom, het
    # rentepercentage en de maandtermijn vaak niet. Ze stonden hier als
    # verplicht veld, waardoor het uitlezen van zo'n opgave volledig faalde op
    # validatie. Wat er altijd op staat is de restschuld en de betaalde rente.
    principal_eur: Optional[float] = Field(
        default=None, gt=0, description="Original loan amount, if stated"
    )
    current_balance_eur: float = Field(..., ge=0, description="Current outstanding balance")
    interest_rate_pct: Optional[float] = Field(
        default=None, ge=0, le=20, description="Annual interest rate, if stated"
    )
    monthly_payment_eur: Optional[float] = Field(
        default=None,
        ge=0,
        description="Monthly payment, if stated. Zero during a payment holiday.",
    )
    loan_type: str = Field(default="hypotheek", description="Type of loan (hypotheek, persoonlijk, etc.)")
    annual_interest_paid_eur: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Interest actually paid during the year, as stated on the annual "
            "mortgage statement (jaaropgave). Left as None when the document "
            "does not state it; the matcher then approximates from balance and "
            "rate, which overstates for annuity loans."
        ),
    )

    @field_validator('current_balance_eur')
    @classmethod
    def validate_balance_vs_principal(cls, v: float, info) -> float:
        """Validate current balance doesn't exceed principal (with 10% tolerance)."""
        data = info.data
        # 'is not None' en niet 'in data': het veld is optioneel geworden en
        # staat dan als None in data, waarop de vermenigvuldiging hieronder
        # een TypeError geeft.
        if data.get('principal_eur') is not None:
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
    
    gross_income_eur: float = Field(
        ...,
        ge=0,
        description=(
            "Total business income. Zero is valid for a dormant entity; a "
            "gt=0 constraint rejected those annual statements outright."
        ),
    )
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


class EmploymentIncome(BaseModel):
    """Jaaropgave van loon of uitkering.

    Een dossier heeft er vaak meer dan een: twee werkgevers, of loon plus een
    uitkering. Daarom een lijst en geen enkel veld.
    """

    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    employer_name: str = Field(..., min_length=2, description="Werkgever of uitkerende instantie")
    gross_salary_eur: float = Field(..., ge=0, description="Bruto loon or benefit over the year")
    payroll_tax_eur: float = Field(default=0, ge=0, description="Ingehouden loonheffing")
    health_insurance_contribution_eur: Optional[float] = Field(
        default=None, ge=0, description="Ingehouden bijdrage Zvw, if stated"
    )
    is_benefit: bool = Field(
        default=False,
        description="True for a benefit (uitkering) rather than employment income",
    )
    year: Optional[int] = Field(
        default=None,
        ge=2000,
        description="Year the statement covers, needed for the period check",
    )


class InsurancePremium(BaseModel):
    """Betaalde premie voor een verzekering, zoals een AOV.

    De premie voor een arbeidsongeschiktheidsverzekering is een aftrekpost die
    in de praktijk regelmatig wordt vergeten. Daarom apart gemodelleerd en niet
    weggestopt in een algemeen bedrag aan aftrekposten.
    """

    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    insurer_name: str = Field(..., min_length=2, description="Verzekeraar")
    policy_kind: str = Field(
        default="AOV",
        description="Type: AOV, lijfrente, overlijdensrisico, anders",
    )
    annual_premium_eur: float = Field(..., ge=0, description="Premie over het jaar")
    policy_number: Optional[str] = Field(default=None, description="Polisnummer")
    year: Optional[int] = Field(default=None, ge=2000, description="Year the premium covers")
    started_this_year: bool = Field(
        default=False,
        description="True if the policy started in this year; triggers a full check",
    )


class AnnuityInfo(BaseModel):
    """Lijfrente: betaalde premie of ontvangen uitkering."""

    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    provider_name: str = Field(..., min_length=2, description="Aanbieder")
    premium_paid_eur: Optional[float] = Field(
        default=None, ge=0, description="Betaalde premie of inleg"
    )
    benefit_received_eur: Optional[float] = Field(
        default=None, ge=0, description="Ontvangen uitkering"
    )
    payroll_tax_eur: float = Field(default=0, ge=0, description="Ingehouden loonheffing")
    year: Optional[int] = Field(default=None, ge=2000, description="Year concerned")


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
    # None means "the document does not substantiate this figure", which the
    # matcher reports as MISSING_PROOF. 0.0 means "substantiated as nil".
    # Collapsing the two into a default of 0 hid missing source documents.
    other_assets_eur: Optional[float] = Field(
        default=None,
        ge=0,
        description="Other assets/investments value; None if not in the document"
    )
    deductible_items_eur: Optional[float] = Field(
        default=None,
        ge=0,
        description="Tax deductible items; None if not in the document"
    )
    employment_income: list[EmploymentIncome] = Field(
        default_factory=list,
        description="All jaaropgaven for salary and benefits"
    )
    insurance_premiums: list[InsurancePremium] = Field(
        default_factory=list,
        description="Paid insurance premiums, notably AOV"
    )
    annuities: list[AnnuityInfo] = Field(
        default_factory=list,
        description="Lijfrente premiums paid and benefits received"
    )
    kia_profit_eur: Optional[float] = Field(
        default=None,
        ge=0,
        description="Claimed KIA deduction; None if not in the document"
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
        """Haal het JSON-object uit het antwoord van Gemini.

        Gebruikt de gedeelde parser in llm_json.py, zodat de documentlezer en
        de adviseur dezelfde strategieen volgen. Er stonden hiervoor twee
        implementaties met verschillende degelijkheid; de zwakkere liet de
        adviseur omvallen op antwoorden die hier wel doorkwamen.
        """
        return extract_json_object(response_text, context="Gemini-antwoord")


    async def _extract_with_retry(self, pdf_base64: str) -> str:
        """Call Gemini API with retry logic and exponential backoff.
        
        Args:
            pdf_base64: Base64 encoded PDF content
            
        Returns:
            Raw JSON response from Gemini
            
        Raises:
            RuntimeError: If all retries fail
        """
        system_prompt = """You extract financial data from DUTCH tax and financial documents
(jaaropgave loon or uitkering, AOV-premieoverzicht, bankjaaropgave,
WOZ-beschikking, hypotheek jaaropgave, nota van afrekening, jaarrekening,
lijfrente-opgave).

Report every figure the document states, also when you doubt whether it belongs
in the return. A deduction that is present in the source but absent from the
return is exactly what this review is meant to surface, so omitting it here
defeats the purpose. Judging deductibility is not your task.

CRITICAL: RESPOND WITH ONLY VALID JSON. NO MARKDOWN, NO EXPLANATIONS, NO TEXT.

DUTCH NUMBER FORMAT - THIS IS THE MOST COMMON SOURCE OF ERRORS:
Dutch documents use a period as thousands separator and a comma as decimal
separator, the opposite of English. You must convert to JSON floats.
    "EUR 250.000,00"  -> 250000.00      (NOT 250.0)
    "EUR 1.234,56"    -> 1234.56        (NOT 1.23456)
    "EUR 8.500"       -> 8500.00        (NOT 8.5)
    "EUR 0,00"        -> 0.00
Negative amounts may appear as "1.000,00-" or "(1.000,00)" or "-1.000,00";
all three mean -1000.00. A credit balance on a debt is not negative.

MISSING VERSUS ZERO - DO NOT CONFUSE THESE:
    Document does not mention the item at all -> null
    Document explicitly states a zero amount  -> 0.0
This distinction matters: null means "not substantiated, needs a source
document", while 0.0 means "substantiated as nil". Never write 0.0 to fill a
gap, and never write null for an amount the document actually states as zero.

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
            "loan_type": "hypotheek",
            "annual_interest_paid_eur": 6250.0
        }
    ],
    "employment_income": [
        {
            "employer_name": "Voorbeeld BV",
            "gross_salary_eur": 62000.0,
            "payroll_tax_eur": 21500.0,
            "health_insurance_contribution_eur": null,
            "is_benefit": false,
            "year": 2024
        }
    ],
    "insurance_premiums": [
        {
            "insurer_name": "Voorbeeld Verzekeringen",
            "policy_kind": "AOV",
            "annual_premium_eur": 2400.0,
            "policy_number": "12345678",
            "year": 2024,
            "started_this_year": false
        }
    ],
    "annuities": [],
    "business_income": null,
    "real_estate": [
        {
            "address": "Straat 1, Amsterdam",
            "woz_value_eur": 500000.0,
            "year_valued": 2024,
            "ownership_pct": 100.0
        }
    ],
    "other_assets_eur": null,
    "deductible_items_eur": 5000.0,
    "kia_profit_eur": null,
    "document_type": "bankjaaropgave"
}

FIELD NOTES:
- annual_interest_paid_eur: the interest ACTUALLY PAID during the year, as
  stated on the jaaropgave (often labelled "betaalde rente",
  "rente hypothecaire lening" or "renteaftrek"). This is NOT the outstanding
  balance and NOT the monthly payment. Use null if the document does not state
  a paid-interest figure. Do not compute it yourself.
- current_balance_eur: outstanding debt ("restschuld", "saldo per 31-12").
- balance_eur: account balance. For box 3 the reference date (peildatum) is
  1 January, which equals the 31 December balance of the preceding year.
- woz_value_eur: the WOZ value ("vastgestelde waarde") from the beschikking.
- ownership_pct: share of ownership. If the beschikking lists two owners or
  says "50% eigendom", use 50.0. Default to 100.0 only when the document gives
  no indication of shared ownership.
- year_valued: the "waardepeildatum" year, not the year the letter was sent.
- gross_salary_eur: "loon", "loon uit tegenwoordige dienstbetrekking" or
  "bruto loon" on the jaaropgave. Not the net amount and not the taxable amount
  after deductions.
- payroll_tax_eur: "ingehouden loonheffing" or "loonbelasting/premie
  volksverzekeringen".
- is_benefit: true for a payment from UWV, a pension fund or an insurer;
  false for salary from an employer.
- annual_premium_eur: the premium paid during the year. For an AOV this is a
  deduction that is often overlooked, so report it whenever the document shows
  it, even when you are unsure it is deductible. Deciding that is not your task.
- started_this_year: true when the document states a start date, commencement
  or first premium falling within the year covered.
- year: the year the document covers, on every item that has the field. This
  is used to check the document belongs to the tax year being reviewed, so
  never guess it; use null when the document does not state it.
- document_type: one of WOZ_beschikking, bankjaaropgave, hypotheek_jaaropgave,
  jaaropgave_loon, jaaropgave_uitkering, aov_premie, lijfrente,
  nota_van_afrekening, jaarrekening, aangifterapport, overig.

RULES:
1. All amounts are JSON numbers, never strings, never with separators
2. Currency is always EUR; convert other currencies and lower the confidence
3. Lists are [] only when the document type could contain such items but has none
4. extraction_confidence is 0-1 and reflects legibility and completeness;
   use below 0.7 for scans that are partly unreadable
5. ownership_pct is 1-100
6. Never invent a figure that is not in the document
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

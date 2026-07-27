"""
FiscAudit AI - Audit Matcher Engine (PRODUCTION-READY)

Pure Python deterministic matching of AG-codes vs extracted financial data.
NO AI involvement - 100% reproducible and auditable.

AG-codes are Dutch tax authorities' standardized codes for reporting financial data.
This module performs:
1. Field extraction from Gemini output
2. Direct comparison (€0 tolerance)
3. Status classification (MATCH/MISMATCH/MISSING)
4. Audit trail logging
"""

import logging
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from .extractor import ExtractedFinancialData


logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class AuditStatus(str, Enum):
    """Status of AG-code match."""
    MATCH = "MATCH"                      # Values match exactly (€0 difference)
    MISMATCH = "MISMATCH"                # Values differ by >€100 or >2%
    MINOR_VARIANCE = "MINOR_VARIANCE"    # Difference €1-100 (rounding/timing)
    MISSING_PROOF = "MISSING_PROOF"      # No proof/data found in document
    ERROR = "ERROR"                      # Error during comparison
    PENDING = "PENDING"                  # Not yet processed


class RiskLevel(str, Enum):
    """Risk level for a finding."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ============================================================================
# AG-CODE MAPPING (Dutch Tax Authority Standard Codes)
# ============================================================================

AG_CODE_MAPPING = {
    # ========== BOX 1: SALARY & BUSINESS INCOME ==========
    
    "AG1010": {
        "name": "Salary income",
        "field": "business_income.gross_income_eur",
        "description": "Gross salary from employment (Box 1)",
        "category": "Income"
    },
    
    # ========== BOX 2: SUBSTANTIAL INTEREST ==========
    # (Not often used, skipped for brevity)
    
    # ========== BOX 3: WEALTH/ASSETS ==========
    
    "AG3020": {
        "name": "Bank & savings accounts",
        "field": "bank_accounts",
        "description": "Total of all bank saldi on Dec 31 (Box 3)",
        "category": "Assets",
        "aggregation": "sum"
    },
    
    "AG3030": {
        "name": "WOZ property value",
        "field": "real_estate",
        "description": "WOZ valuation of own residence (Box 3)",
        "category": "Assets",
        "aggregation": "sum"
    },
    
    "AG3050": {
        "name": "Other investments (Box 3)",
        "field": "other_assets_eur",
        "description": "Stocks, bonds, other securities",
        "category": "Assets"
    },
    
    # ========== BUSINESS DEDUCTIONS ==========
    
    "AG4010": {
        "name": "Business expenses",
        "field": "business_income.deductible_expenses_eur",
        "description": "Total deductible business expenses",
        "category": "Deductions"
    },
    
    "AG4020": {
        "name": "KIA profit",
        "field": "kia_profit_eur",
        "description": "Young entrepreneur deduction (KIA)",
        "category": "Deductions"
    },
    
    # ========== MORTGAGE & INTEREST DEDUCTIONS ==========
    
    "AG5010": {
        "name": "Mortgage interest",
        "field": "mortgages",
        "description": "Deductible mortgage interest (Box 1)",
        "category": "Deductions",
        "aggregation": "sum"
    },
    
    "AG5020": {
        "name": "Student loan interest",
        "field": "deductible_items_eur",
        "description": "Deductible student loan interest",
        "category": "Deductions"
    },
}


# ============================================================================
# PYDANTIC MODELS (STRICT VALIDATION)
# ============================================================================

class MatchResult(BaseModel):
    """Result of single AG-code comparison."""
    
    model_config = ConfigDict(strict=True, str_strip_whitespace=True)
    
    ag_code: str = Field(..., description="AG-code (e.g., AG3020)")
    ag_name: str = Field(..., description="Description of AG-code")
    reported_amount_eur: float = Field(..., description="Amount user reported")
    extracted_amount_eur: float = Field(..., description="Amount found in documents")
    difference_eur: float = Field(..., description="Difference (reported - extracted)")
    difference_pct: float = Field(default=0, description="Percentage difference")
    status: AuditStatus = Field(..., description="Match status")
    confidence: float = Field(default=0.95, ge=0, le=1, description="Confidence in match")
    notes: str = Field(default="", description="Additional notes/explanations")
    audit_timestamp: datetime = Field(default_factory=datetime.now)

    def risk_level(self) -> RiskLevel:
        """Determine risk level based on status and difference."""
        if self.status == AuditStatus.MATCH:
            return RiskLevel.LOW
        elif self.status == AuditStatus.MINOR_VARIANCE:
            return RiskLevel.LOW if abs(self.difference_eur) < 100 else RiskLevel.MEDIUM
        elif self.status == AuditStatus.MISMATCH:
            if abs(self.difference_eur) > 50000:
                return RiskLevel.CRITICAL
            elif abs(self.difference_eur) > 10000:
                return RiskLevel.HIGH
            else:
                return RiskLevel.MEDIUM
        elif self.status == AuditStatus.MISSING_PROOF:
            return RiskLevel.HIGH
        else:
            return RiskLevel.MEDIUM


class AuditSummary(BaseModel):
    """Summary of complete audit."""
    
    model_config = ConfigDict(strict=True)
    
    total_ag_codes_checked: int = Field(..., description="Total AG-codes processed")
    matched: int = Field(..., description="Number of matches (€0 difference)")
    minor_variance: int = Field(..., description="Minor variances (€1-100)")
    mismatched: int = Field(..., description="Significant mismatches")
    missing_proof: int = Field(..., description="Missing documentation")
    errors: int = Field(..., description="Processing errors")
    total_difference_eur: float = Field(..., description="Sum of all differences")
    overall_risk_level: RiskLevel = Field(..., description="Overall risk assessment")
    audit_timestamp: datetime = Field(default_factory=datetime.now)
    duration_seconds: float = Field(default=0, description="Audit duration in seconds")

    @property
    def match_rate(self) -> float:
        """Calculate percentage of matched codes."""
        if self.total_ag_codes_checked == 0:
            return 0
        return (self.matched / self.total_ag_codes_checked) * 100


# ============================================================================
# AUDIT MATCHER
# ============================================================================

class AuditMatcher:
    """Pure Python audit matching engine.
    
    Compares user-reported AG-codes with extracted financial data.
    Features:
    - Deterministic matching (reproducible)
    - Zero tolerance for amounts (€0.00 equality)
    - Audit trail logging
    - Risk classification
    
    Example:
        >>> matcher = AuditMatcher()
        >>> results = matcher.match_ag_codes(
        ...     extracted_data=data,
        ...     reported_amounts={"AG3020": 50000}
        ... )
    """
    
    # Tolerances
    EXACT_MATCH_TOLERANCE_EUR = 0.01  # €0.01
    MINOR_VARIANCE_THRESHOLD_EUR = 100  # €100
    VARIANCE_THRESHOLD_PCT = 2  # 2%

    def __init__(self):
        """Initialize AuditMatcher."""
        logger.info("AuditMatcher initialized (pure Python, zero AI)")

    def _extract_field_value(
        self,
        data: ExtractedFinancialData,
        field_path: str
    ) -> Optional[float]:
        """Extract value from ExtractedFinancialData using dot notation.
        
        Supports:
        - Simple fields: "bank_accounts" → sums all account balances
        - Nested fields: "business_income.gross_income_eur"
        - List aggregation: "mortgages" → sums current_balance_eur
        
        Args:
            data: Extracted financial data
            field_path: Field path (e.g., "business_income.gross_income_eur")
            
        Returns:
            Float value or None if not found
        """
        try:
            parts = field_path.split('.')
            current = data
            
            for i, part in enumerate(parts):
                if hasattr(current, part):
                    current = getattr(current, part)
                else:
                    logger.debug(f"Field not found: {field_path}")
                    return None
            
            # If we have a list, aggregate values
            if isinstance(current, list):
                total = 0
                for item in current:
                    if hasattr(item, 'balance_eur'):
                        total += item.balance_eur
                    elif hasattr(item, 'woz_value_eur'):
                        total += item.woz_value_eur
                    elif hasattr(item, 'current_balance_eur'):
                        total += item.current_balance_eur
                return total if total > 0 else None
            
            # If float or int, return as float
            if isinstance(current, (int, float)):
                return float(current)
            
            logger.debug(f"Cannot extract numeric value from {field_path}: {type(current)}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting {field_path}: {str(e)}")
            return None

    def _calculate_difference(
        self,
        reported: float,
        extracted: float
    ) -> Tuple[float, float]:
        """Calculate absolute and percentage difference.
        
        Args:
            reported: Reported amount
            extracted: Extracted amount
            
        Returns:
            Tuple of (abs_diff, pct_diff)
        """
        abs_diff = abs(reported - extracted)
        
        # Avoid division by zero
        if extracted == 0:
            pct_diff = 100.0 if reported > 0 else 0.0
        else:
            pct_diff = (abs_diff / abs(extracted)) * 100
        
        return abs_diff, pct_diff

    def _determine_status(
        self,
        abs_diff: float,
        pct_diff: float,
        extracted_value: Optional[float]
    ) -> AuditStatus:
        """Determine match status based on differences.
        
        Logic:
        - €0.00 difference → MATCH
        - €0.01-€100 difference → MINOR_VARIANCE
        - >€100 or >2% difference → MISMATCH
        - No extracted value → MISSING_PROOF
        
        Args:
            abs_diff: Absolute difference in EUR
            pct_diff: Percentage difference
            extracted_value: Extracted value (or None if missing)
            
        Returns:
            AuditStatus
        """
        if extracted_value is None:
            return AuditStatus.MISSING_PROOF
        
        if abs_diff <= self.EXACT_MATCH_TOLERANCE_EUR:
            return AuditStatus.MATCH
        
        if abs_diff <= self.MINOR_VARIANCE_THRESHOLD_EUR and pct_diff <= self.VARIANCE_THRESHOLD_PCT:
            return AuditStatus.MINOR_VARIANCE
        
        return AuditStatus.MISMATCH

    def match_single_ag_code(
        self,
        ag_code: str,
        reported_amount_eur: float,
        extracted_data: ExtractedFinancialData
    ) -> MatchResult:
        """Compare single AG-code against extracted data.
        
        Args:
            ag_code: Code to match (e.g., "AG3020")
            reported_amount_eur: Amount user reported
            extracted_data: Data extracted from documents
            
        Returns:
            MatchResult with status and details
        """
        try:
            # Validate AG-code exists
            if ag_code not in AG_CODE_MAPPING:
                return MatchResult(
                    ag_code=ag_code,
                    ag_name="Unknown",
                    reported_amount_eur=reported_amount_eur,
                    extracted_amount_eur=0,
                    difference_eur=reported_amount_eur,
                    status=AuditStatus.ERROR,
                    notes=f"Unknown AG-code: {ag_code}"
                )
            
            mapping = AG_CODE_MAPPING[ag_code]
            
            # Extract value from data
            extracted_value = self._extract_field_value(
                extracted_data,
                mapping['field']
            )
            
            # If no data found
            if extracted_value is None:
                return MatchResult(
                    ag_code=ag_code,
                    ag_name=mapping['name'],
                    reported_amount_eur=reported_amount_eur,
                    extracted_amount_eur=0,
                    difference_eur=reported_amount_eur,
                    status=AuditStatus.MISSING_PROOF,
                    notes=f"No {mapping['description']} found in documents",
                    confidence=0.0
                )
            
            # Calculate differences
            abs_diff, pct_diff = self._calculate_difference(
                reported_amount_eur,
                extracted_value
            )
            
            # Determine status
            status = self._determine_status(abs_diff, pct_diff, extracted_value)
            
            # Build result
            result = MatchResult(
                ag_code=ag_code,
                ag_name=mapping['name'],
                reported_amount_eur=reported_amount_eur,
                extracted_amount_eur=extracted_value,
                difference_eur=reported_amount_eur - extracted_value,
                difference_pct=pct_diff,
                status=status,
                notes=mapping['description'],
                confidence=0.95 if status == AuditStatus.MATCH else 0.85
            )
            
            logger.info(
                f"{ag_code}: {status.value} "
                f"(reported €{reported_amount_eur:,.2f}, "
                f"extracted €{extracted_value:,.2f}, "
                f"diff €{abs_diff:,.2f})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error matching {ag_code}: {str(e)}")
            return MatchResult(
                ag_code=ag_code,
                ag_name="Error",
                reported_amount_eur=reported_amount_eur,
                extracted_amount_eur=0,
                difference_eur=reported_amount_eur,
                status=AuditStatus.ERROR,
                notes=f"Error during matching: {str(e)}",
                confidence=0.0
            )

    def match_ag_codes(
        self,
        extracted_data: ExtractedFinancialData,
        reported_amounts: dict[str, float]
    ) -> Tuple[List[MatchResult], AuditSummary]:
        """Match multiple AG-codes against extracted data.
        
        Args:
            extracted_data: Financial data extracted from documents
            reported_amounts: Dict of {AG_code: amount_eur}
            
        Returns:
            Tuple of (match_results, audit_summary)
        """
        import time
        start_time = time.time()
        
        logger.info(f"Starting audit matching for {len(reported_amounts)} AG-codes")
        
        results = []
        for ag_code, amount in reported_amounts.items():
            result = self.match_single_ag_code(ag_code, amount, extracted_data)
            results.append(result)
        
        # Compile summary
        summary = AuditSummary(
            total_ag_codes_checked=len(results),
            matched=sum(1 for r in results if r.status == AuditStatus.MATCH),
            minor_variance=sum(1 for r in results if r.status == AuditStatus.MINOR_VARIANCE),
            mismatched=sum(1 for r in results if r.status == AuditStatus.MISMATCH),
            missing_proof=sum(1 for r in results if r.status == AuditStatus.MISSING_PROOF),
            errors=sum(1 for r in results if r.status == AuditStatus.ERROR),
            total_difference_eur=sum(r.difference_eur for r in results),
            overall_risk_level=self._determine_overall_risk(results),
            duration_seconds=time.time() - start_time
        )
        
        logger.info(
            f"✓ Audit complete. {summary.matched}/{summary.total_ag_codes_checked} matched. "
            f"Total diff: €{summary.total_difference_eur:,.2f}. "
            f"Risk: {summary.overall_risk_level.value}. "
            f"Duration: {summary.duration_seconds:.2f}s"
        )
        
        return results, summary

    @staticmethod
    def _determine_overall_risk(results: List[MatchResult]) -> RiskLevel:
        """Determine overall risk level from individual results."""
        # Count by risk level
        risk_counts = {level: 0 for level in RiskLevel}
        
        for result in results:
            risk = result.risk_level()
            risk_counts[risk] += 1
        
        # Highest risk determines overall
        if risk_counts[RiskLevel.CRITICAL] > 0:
            return RiskLevel.CRITICAL
        elif risk_counts[RiskLevel.HIGH] > 0:
            return RiskLevel.HIGH
        elif risk_counts[RiskLevel.MEDIUM] > 0:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

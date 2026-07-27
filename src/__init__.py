"""
FiscAudit AI - Automated Fiscal Audit & Reconciliation Platform
Main package initializer
"""

__version__ = "1.0.0"
__author__ = "FiscAudit AI Team"
__description__ = "An Automated AI-Driven Fiscal Audit & Reconciliation Platform for Dutch Tax Returns"

# ============================================================================
# PACKAGE EXPORTS
# ============================================================================

from .anonymizer import DataAnonymizer
from .extractor import DocumentExtractor, ExtractedFinancialData
from .matcher import AuditMatcher, MatchResult, AuditStatus
from .advisor import FiscalAdvisor, RiskAssessment
from .db import SupabaseClient

__all__ = [
    "DataAnonymizer",
    "DocumentExtractor",
    "ExtractedFinancialData",
    "AuditMatcher",
    "MatchResult",
    "AuditStatus",
    "FiscalAdvisor",
    "RiskAssessment",
    "SupabaseClient",
]

# ============================================================================
# VERSION INFO
# ============================================================================

def get_version():
    """Get the current version of FiscAudit AI"""
    return __version__

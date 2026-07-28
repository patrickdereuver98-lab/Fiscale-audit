"""
FiscAudit AI - Geautomatiseerde fiscale aansluitcontrole

Laagindeling, van binnen naar buiten:

    domain.py        gedeelde begrippen (AuditStatus, RiskLevel)
    llm_json.py      JSON uit een modelantwoord halen
    anonymizer.py    persoonsgegevens maskeren voor externe aanroepen
    extractor.py     brondocumenten uitlezen (Gemini)
    matcher.py       cijfermatige aansluiting (zuiver Python, deterministisch)
    advisor.py       inhoudelijke weging (Claude)
    db.py            opslag (Supabase)
    ui_components.py presentatie (Streamlit)

De afhankelijkheden lopen één kant op: domain kent niemand, matcher kent
extractor, advisor kent matcher. Zo blijft de cijfermatige kern testbaar
zonder API-sleutels.
"""

__version__ = "2.0.0"
__description__ = (
    "Geautomatiseerde controle van Nederlandse belastingaangiften tegen "
    "de onderliggende brondocumenten"
)

from .domain import AuditStatus, RiskLevel
from .llm_json import extract_json_object, JsonExtractionError
from .anonymizer import DataAnonymizer
from .extractor import DocumentExtractor, ExtractedFinancialData
from .matcher import AuditMatcher, MatchResult, AuditSummary, AG_CODE_MAPPING
from .advisor import (
    FiscalAdvisor, RiskAssessment, RiskPoint,
    build_client_email, build_document_request_email,
)
from .db import SupabaseClient

__all__ = [
    "AuditStatus",
    "RiskLevel",
    "extract_json_object",
    "JsonExtractionError",
    "DataAnonymizer",
    "DocumentExtractor",
    "ExtractedFinancialData",
    "AuditMatcher",
    "MatchResult",
    "AuditSummary",
    "AG_CODE_MAPPING",
    "FiscalAdvisor",
    "RiskAssessment",
    "RiskPoint",
    "build_client_email",
    "build_document_request_email",
    "SupabaseClient",
]

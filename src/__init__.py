"""
FiscAudit AI - Geautomatiseerde controle van een aangifte tegen de brondocumenten

Laagindeling, van binnen naar buiten:

    domain.py        gedeelde begrippen (status, risico, documentsoort)
    peildatum.py     periodecontrole per documentsoort
    triggers.py      wanneer is een volledige fiscale toets nodig
    posten.py        aangifteposten, gemapt op de labels uit het rapport
    fiscale_kern.py  tarieven en drempels per jaar, met verificatiestatus
    omissions.py     wat in de bron staat en niet in de aangifte
    llm_json.py      JSON uit een modelantwoord halen
    anonymizer.py    persoonsgegevens maskeren voor externe aanroepen
    extractor.py     brondocumenten uitlezen (Gemini)
    matcher.py       cijfermatige aansluiting (zuiver Python, deterministisch)
    advisor.py       inhoudelijke weging (Claude)
    db.py            opslag (Supabase)
    ui_components.py presentatie (Streamlit)

De afhankelijkheden lopen een kant op: domain kent niemand, matcher kent
extractor, advisor kent matcher.

De import is lui. Dat is geen stijlkeuze maar noodzaak: de bovenste vier
modules zijn zuivere logica zonder externe afhankelijkheden en moeten te
importeren en te testen zijn zonder dat google-generativeai, anthropic of
supabase is geinstalleerd. Met gretige imports in dit bestand trok
`from src.domain import RiskLevel` de hele Gemini-client mee, waardoor de
deterministische kern niet los te gebruiken was.
"""

from typing import TYPE_CHECKING, Any

__version__ = "2.1.0"
__description__ = (
    "Controleert een ingevulde aangifte inkomstenbelasting tegen de "
    "onderliggende brondocumenten"
)

# Zuivere logica, veilig om direct te importeren.
from .domain import (
    AuditStatus, RiskLevel, ReviewStatus, FindingKind, DocumentKind,
)
from .llm_json import extract_json_object, JsonExtractionError
from .peildatum import (
    PeriodCheck, check_document_period, check_all_documents,
    expected_document_year, expected_reference_date,
)
from .triggers import (
    TriggerKind, Trigger, TriggerReport, TRIGGER_DEFINITIES, missing_documents,
)
from .posten import POSTEN, Post, PostSoort, post_voor_label, normaliseer_label
from .fiscale_kern import (
    Kernwaarde, Kernwaarden, Voorstel, KernwaardeOntbreekt,
    laad_kernwaarden, lege_kernwaarden, bewaar_in_json,
    maak_voorstellen, pas_voorstellen_toe,
)

# Modules met een externe afhankelijkheid, pas geladen bij gebruik.
_LAZY = {
    "DataAnonymizer": "anonymizer",
    "DocumentExtractor": "extractor",
    "ExtractedFinancialData": "extractor",
    "check_omissies": "omissions",
    "check_omissies_op_labels": "omissions",
    "Omissie": "omissions",
    "OmissieRapport": "omissions",
    "AuditMatcher": "matcher",
    "MatchResult": "matcher",
    "AuditSummary": "matcher",
    "AG_CODE_MAPPING": "matcher",
    "FiscalAdvisor": "advisor",
    "RiskAssessment": "advisor",
    "RiskPoint": "advisor",
    "build_client_email": "advisor",
    "build_document_request_email": "advisor",
    "SupabaseClient": "db",
}

if TYPE_CHECKING:  # alleen voor typecheckers, niet bij het uitvoeren
    from .anonymizer import DataAnonymizer
    from .extractor import DocumentExtractor, ExtractedFinancialData
    from .matcher import AuditMatcher, MatchResult, AuditSummary, AG_CODE_MAPPING
    from .advisor import (
        FiscalAdvisor, RiskAssessment, RiskPoint,
        build_client_email, build_document_request_email,
    )
    from .db import SupabaseClient


def __getattr__(name: str) -> Any:
    """Laad een module pas wanneer er iets uit wordt opgevraagd (PEP 562)."""
    module_naam = _LAZY.get(name)
    if module_naam is None:
        raise AttributeError(f"module {__name__!r} heeft geen attribuut {name!r}")

    from importlib import import_module
    module = import_module(f".{module_naam}", __name__)
    waarde = getattr(module, name)
    globals()[name] = waarde  # tweede keer direct raak
    return waarde


__all__ = [
    "AuditStatus", "RiskLevel", "ReviewStatus", "FindingKind", "DocumentKind",
    "extract_json_object", "JsonExtractionError",
    "PeriodCheck", "check_document_period", "check_all_documents",
    "expected_document_year", "expected_reference_date",
    "TriggerKind", "Trigger", "TriggerReport", "TRIGGER_DEFINITIES",
    "missing_documents",
    "POSTEN", "Post", "PostSoort", "post_voor_label", "normaliseer_label",
    "Kernwaarde", "Kernwaarden", "Voorstel", "KernwaardeOntbreekt",
    "laad_kernwaarden", "lege_kernwaarden", "bewaar_in_json",
    "maak_voorstellen", "pas_voorstellen_toe",
    *_LAZY.keys(),
]

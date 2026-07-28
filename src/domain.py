"""
FiscAudit AI - Gedeelde begrippen

Eén plek voor de begrippen die door meerdere lagen worden gebruikt. RiskLevel
stond eerder zowel in matcher.py als in advisor.py: twee enums met dezelfde
naam en dezelfde waarden, maar niet dezelfde klasse. Daardoor was
matcher.RiskLevel.HIGH != advisor.RiskLevel.HIGH, en zou een vergelijking
tussen beide stil op False uitkomen.

Deze module bevat uitsluitend vocabulaire. Geen logica, geen imports uit de
rest van het project, zodat er geen kringverwijzingen kunnen ontstaan.

Laagindeling:
    domain.py      begrippen
    extractor.py   uitlezen van documenten (Gemini)
    matcher.py     cijfermatige aansluiting (zuiver Python)
    advisor.py     inhoudelijke weging (Claude)
    db.py          opslag
    ui_components  presentatie
"""

from enum import Enum


class AuditStatus(str, Enum):
    """Uitkomst van een aansluiting op een AG-code."""

    MATCH = "MATCH"                      # sluit aan binnen de afrondingsmarge
    MINOR_VARIANCE = "MINOR_VARIANCE"    # klein verschil, vermoedelijk afronding
    MISMATCH = "MISMATCH"                # echte afwijking, uitzoeken
    MISSING_PROOF = "MISSING_PROOF"      # geen onderbouwing in de documenten
    ERROR = "ERROR"                      # fout tijdens verwerken
    PENDING = "PENDING"                  # nog niet verwerkt

    @property
    def label(self) -> str:
        """Nederlandse omschrijving voor de interface."""
        return _STATUS_LABELS[self.value]

    @property
    def needs_attention(self) -> bool:
        """Of deze status handmatig uitzoekwerk vraagt."""
        return self in (
            AuditStatus.MISMATCH,
            AuditStatus.MISSING_PROOF,
            AuditStatus.ERROR,
        )


_STATUS_LABELS = {
    "MATCH": "Akkoord",
    "MINOR_VARIANCE": "Klein verschil",
    "MISMATCH": "Afwijking",
    "MISSING_PROOF": "Geen bewijs",
    "ERROR": "Fout",
    "PENDING": "In wachtrij",
}


class RiskLevel(str, Enum):
    """Zwaarte van een bevinding."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def label(self) -> str:
        """Nederlandse omschrijving voor de interface."""
        return _RISK_LABELS[self.value]

    @property
    def rank(self) -> int:
        """Numerieke zwaarte, zodat niveaus te vergelijken en te sorteren zijn."""
        return _RISK_RANK[self.value]

    @classmethod
    def highest(cls, levels) -> "RiskLevel":
        """Het zwaarste niveau uit een reeks, of LOW als de reeks leeg is."""
        niveaus = list(levels)
        if not niveaus:
            return cls.LOW
        return max(niveaus, key=lambda niveau: niveau.rank)


_RISK_LABELS = {
    "LOW": "Laag",
    "MEDIUM": "Middel",
    "HIGH": "Hoog",
    "CRITICAL": "Kritiek",
}

_RISK_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

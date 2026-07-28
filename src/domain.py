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


class ReviewStatus(str, Enum):
    """Behandelstatus van een bevinding door de reviewer.

    Zonder deze status komt elke terechte uitzondering bij iedere nieuwe run
    opnieuw als rood vlaggetje naar boven. Na twee weken kijkt niemand er dan
    nog naar. De status wordt per dossier en per bevinding opgeslagen, zodat
    een geaccordeerd punt bij een volgende run gedempt wordt weergegeven in
    plaats van opnieuw als actiepunt.
    """

    OPEN = "OPEN"                            # nog niet bekeken
    SEEN = "SEEN"                            # bekeken, nog geen conclusie
    ACCEPTED = "ACCEPTED"                    # akkoord, met onderbouwing
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"  # aangifte moet worden aangepast

    @property
    def label(self) -> str:
        """Nederlandse omschrijving voor de interface."""
        return _REVIEW_LABELS[self.value]

    @property
    def is_resolved(self) -> bool:
        """Of deze bevinding is afgehandeld en niet opnieuw hoeft op te vallen."""
        return self in (ReviewStatus.ACCEPTED, ReviewStatus.CORRECTION_REQUIRED)


_REVIEW_LABELS = {
    "OPEN": "Open",
    "SEEN": "Gezien",
    "ACCEPTED": "Akkoord",
    "CORRECTION_REQUIRED": "Correctie vereist",
}


class FindingKind(str, Enum):
    """Aard van een bevinding.

    Bepaalt de vervolgactie en of er een inhoudelijke weging nodig is. Een
    verkeerd overgenomen getal vraagt geen fiscale analyse, alleen een
    correctie. Een gemiste aftrekpost of een bijzondere situatie wel.
    """

    TRANSFER_ERROR = "TRANSFER_ERROR"    # bron en aangifte wijken af
    OMISSION = "OMISSION"                # staat in de bron, niet in de aangifte
    UNSUPPORTED = "UNSUPPORTED"          # staat in de aangifte, geen bron
    PERIOD_MISMATCH = "PERIOD_MISMATCH"  # brondocument hoort bij een ander jaar
    SPECIAL_SITUATION = "SPECIAL_SITUATION"  # vraagt volledige fiscale toets
    READ_UNCERTAIN = "READ_UNCERTAIN"    # het uitlezen zelf is onzeker

    @property
    def label(self) -> str:
        """Nederlandse omschrijving voor de interface."""
        return _FINDING_LABELS[self.value]

    @property
    def needs_fiscal_analysis(self) -> bool:
        """Of hier een inhoudelijke weging bij hoort.

        Een afwijkend getal en een ontbrekend document zijn feitelijk vast te
        stellen en kosten geen modelaanroep. Een omissie of een bijzondere
        situatie vraagt fiscale beoordeling.
        """
        return self in (
            FindingKind.OMISSION,
            FindingKind.SPECIAL_SITUATION,
        )


_FINDING_LABELS = {
    "TRANSFER_ERROR": "Onjuist overgenomen",
    "OMISSION": "Niet verwerkt in de aangifte",
    "UNSUPPORTED": "Geen onderbouwing",
    "PERIOD_MISMATCH": "Verkeerde periode",
    "SPECIAL_SITUATION": "Bijzondere situatie",
    "READ_UNCERTAIN": "Uitlezen onzeker",
}


class DocumentKind(str, Enum):
    """Soort brondocument, met de periode waarop het betrokken moet worden."""

    JAAROPGAVE_LOON = "JAAROPGAVE_LOON"
    JAAROPGAVE_UITKERING = "JAAROPGAVE_UITKERING"
    AOV_PREMIE = "AOV_PREMIE"
    BANKOVERZICHT = "BANKOVERZICHT"
    WOZ_BESCHIKKING = "WOZ_BESCHIKKING"
    HYPOTHEEK_JAAROPGAVE = "HYPOTHEEK_JAAROPGAVE"
    NOTA_VAN_AFREKENING = "NOTA_VAN_AFREKENING"
    JAARREKENING = "JAARREKENING"
    LIJFRENTE = "LIJFRENTE"
    AANGIFTERAPPORT = "AANGIFTERAPPORT"
    OVERIG = "OVERIG"

    @property
    def label(self) -> str:
        """Nederlandse omschrijving voor de interface."""
        return _DOCUMENT_LABELS[self.value]


_DOCUMENT_LABELS = {
    "JAAROPGAVE_LOON": "Jaaropgave loon",
    "JAAROPGAVE_UITKERING": "Jaaropgave uitkering",
    "AOV_PREMIE": "AOV-premieoverzicht",
    "BANKOVERZICHT": "Bank- of spaaroverzicht",
    "WOZ_BESCHIKKING": "WOZ-beschikking",
    "HYPOTHEEK_JAAROPGAVE": "Hypotheekjaaropgave",
    "NOTA_VAN_AFREKENING": "Nota van afrekening notaris",
    "JAARREKENING": "Jaarrekening",
    "LIJFRENTE": "Lijfrente-opgave",
    "AANGIFTERAPPORT": "Aangifterapport",
    "OVERIG": "Overig document",
}

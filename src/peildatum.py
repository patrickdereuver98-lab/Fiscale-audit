"""
FiscAudit AI - Peildatum- en periodecontrole

Controleert of een aangeleverd brondocument bij het aangiftejaar hoort. Zonder
deze controle levert de aansluiting systematische fouten op die er als echte
afwijkingen uitzien: een bankoverzicht per 31-12-2024 naast een aangifte 2024
geeft over de hele box 3 een verschil, terwijl er niets mis is met de aangifte.
Alleen het verkeerde document is aangeleverd.

Box 3 gaat over de peildatum 1 januari van het aangiftejaar. Het saldo per
1-1-2024 is hetzelfde bedrag als het eindsaldo per 31-12-2023. Voor aangifte
2024 hoort dus het overzicht van boekjaar 2023, terwijl inkomensstukken over
het kalenderjaar 2024 gaan. Die twee lopen een jaar uit elkaar en dat is de
meest voorkomende verwisseling.

TE BEVESTIGEN
De verwachte periode per documentsoort staat in PERIOD_RULES. De regels voor
loon, uitkering, AOV en bank zijn eenduidig. Bij de WOZ-beschikking en de
hypotheekjaaropgave staat een vraagteken in het commentaar: die moeten tegen
de praktijk worden gecontroleerd voordat ze op echte dossiers gaan. Ze staan
apart zodat aanpassen een regel in een tabel is en geen zoektocht door de code.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from .domain import DocumentKind


logger = logging.getLogger(__name__)


# ============================================================================
# VERWACHTE PERIODE PER DOCUMENTSOORT
# ============================================================================

@dataclass(frozen=True)
class PeriodRule:
    """Op welk jaar een documentsoort betrokken moet worden.

    Attributes:
        year_offset: Verschuiving ten opzichte van het aangiftejaar. 0 betekent
            het aangiftejaar zelf, -1 het jaar ervoor.
        is_point_in_time: True bij een stand op een moment (banksaldo,
            restschuld), False bij een bedrag over een periode (loon, premie).
        toelichting: Waarom deze verschuiving geldt. Komt in de waarschuwing
            terecht, zodat de reviewer de reden ziet en niet alleen de melding.
        confirmed: False wanneer de regel nog tegen de praktijk moet worden
            gecontroleerd. Onbevestigde regels geven een zachtere melding.
    """

    year_offset: int
    is_point_in_time: bool
    toelichting: str
    confirmed: bool = True


PERIOD_RULES: Dict[DocumentKind, PeriodRule] = {

    # ---------------- inkomen: het aangiftejaar zelf ----------------

    DocumentKind.JAAROPGAVE_LOON: PeriodRule(
        year_offset=0,
        is_point_in_time=False,
        toelichting="Loon wordt aangegeven over het kalenderjaar van de aangifte",
    ),
    DocumentKind.JAAROPGAVE_UITKERING: PeriodRule(
        year_offset=0,
        is_point_in_time=False,
        toelichting="Een uitkering wordt aangegeven over het kalenderjaar van de aangifte",
    ),
    DocumentKind.AOV_PREMIE: PeriodRule(
        year_offset=0,
        is_point_in_time=False,
        toelichting="Premie is aftrekbaar in het jaar waarin die is betaald",
    ),
    DocumentKind.JAARREKENING: PeriodRule(
        year_offset=0,
        is_point_in_time=False,
        toelichting="De winst uit onderneming betreft het boekjaar van de aangifte",
    ),

    # ---------------- box 3: peildatum 1 januari van het aangiftejaar ----------------
    # Dat is dezelfde stand als het eindsaldo per 31 december van het jaar
    # ervoor, dus offset -1 op het boekjaar van het overzicht.

    DocumentKind.BANKOVERZICHT: PeriodRule(
        year_offset=-1,
        is_point_in_time=True,
        toelichting=(
            "Box 3 gaat over de peildatum 1 januari van het aangiftejaar, "
            "wat gelijk is aan het eindsaldo per 31 december van het jaar ervoor"
        ),
    ),

    # ---------------- nog te bevestigen ----------------

    DocumentKind.WOZ_BESCHIKKING: PeriodRule(
        year_offset=0,
        is_point_in_time=True,
        toelichting=(
            "De beschikking van het aangiftejaar hoort bij de aangifte; let op "
            "het verschil tussen het beschikkingsjaar en de waardepeildatum, "
            "die een jaar eerder ligt"
        ),
        confirmed=False,
    ),
    DocumentKind.HYPOTHEEK_JAAROPGAVE: PeriodRule(
        year_offset=0,
        is_point_in_time=False,
        toelichting=(
            "De betaalde rente betreft het aangiftejaar; de restschuld op "
            "dezelfde opgave hoort bij de peildatum en kan een ander jaar betreffen"
        ),
        confirmed=False,
    ),

    # ---------------- documenten zonder vaste periode ----------------

    DocumentKind.NOTA_VAN_AFREKENING: PeriodRule(
        year_offset=0,
        is_point_in_time=True,
        toelichting="De transportdatum moet in het aangiftejaar liggen",
    ),
    DocumentKind.LIJFRENTE: PeriodRule(
        year_offset=0,
        is_point_in_time=False,
        toelichting="De betaalde of ontvangen bedragen betreffen het aangiftejaar",
    ),
    DocumentKind.AANGIFTERAPPORT: PeriodRule(
        year_offset=0,
        is_point_in_time=False,
        toelichting="Het aangifterapport betreft het aangiftejaar",
    ),
}


# ============================================================================
# UITKOMST
# ============================================================================

@dataclass
class PeriodCheck:
    """Uitkomst van de periodecontrole op een document."""

    document_kind: DocumentKind
    aangiftejaar: int
    expected_year: int
    found_year: Optional[int]
    is_correct: bool
    is_certain: bool
    message: str

    @property
    def needs_attention(self) -> bool:
        """Of dit als bevinding op het dashboard hoort."""
        return not self.is_correct


# ============================================================================
# CONTROLE
# ============================================================================

def expected_document_year(document_kind: DocumentKind, aangiftejaar: int) -> int:
    """Het boekjaar waar dit document over hoort te gaan.

    Args:
        document_kind: Soort brondocument.
        aangiftejaar: Jaar waarover de aangifte gaat.

    Returns:
        Het verwachte jaar van het document.

    Voorbeeld:
        >>> expected_document_year(DocumentKind.BANKOVERZICHT, 2024)
        2023
        >>> expected_document_year(DocumentKind.JAAROPGAVE_LOON, 2024)
        2024
    """
    regel = PERIOD_RULES.get(document_kind)
    if regel is None:
        return aangiftejaar
    return aangiftejaar + regel.year_offset


def expected_reference_date(document_kind: DocumentKind, aangiftejaar: int) -> Optional[date]:
    """De datum waarop een standdocument betrokken moet zijn.

    Alleen zinvol bij documenten die een stand op een moment geven. Bij een
    bedrag over een periode is er geen enkele datum en wordt None teruggegeven.

    Voorbeeld:
        >>> expected_reference_date(DocumentKind.BANKOVERZICHT, 2024)
        datetime.date(2023, 12, 31)
    """
    regel = PERIOD_RULES.get(document_kind)
    if regel is None or not regel.is_point_in_time:
        return None
    return date(expected_document_year(document_kind, aangiftejaar), 12, 31)


def check_document_period(
    document_kind: DocumentKind,
    aangiftejaar: int,
    found_year: Optional[int],
) -> PeriodCheck:
    """Controleer of een document bij het aangiftejaar hoort.

    Args:
        document_kind: Soort brondocument.
        aangiftejaar: Jaar waarover de aangifte gaat.
        found_year: Het jaar dat in het document is aangetroffen, of None
            wanneer dat niet is vastgesteld.

    Returns:
        PeriodCheck met een Nederlandse melding die rechtstreeks in de
        reviewnote kan worden opgenomen.
    """
    regel = PERIOD_RULES.get(document_kind)
    verwacht = expected_document_year(document_kind, aangiftejaar)
    zeker = regel.confirmed if regel else False

    if found_year is None:
        return PeriodCheck(
            document_kind=document_kind,
            aangiftejaar=aangiftejaar,
            expected_year=verwacht,
            found_year=None,
            is_correct=False,
            is_certain=False,
            message=(
                f"Van dit document ({document_kind.label.lower()}) is geen jaar "
                f"vastgesteld. Verwacht wordt {verwacht}. Controleer of het "
                f"juiste document is aangeleverd."
            ),
        )

    if found_year == verwacht:
        return PeriodCheck(
            document_kind=document_kind,
            aangiftejaar=aangiftejaar,
            expected_year=verwacht,
            found_year=found_year,
            is_correct=True,
            is_certain=zeker,
            message=f"Periode klopt: {document_kind.label.lower()} over {found_year}.",
        )

    verschil = found_year - verwacht
    richting = "later" if verschil > 0 else "eerder"
    melding = (
        f"Let op: dit is een {document_kind.label.lower()} over {found_year}, "
        f"terwijl voor aangiftejaar {aangiftejaar} het jaar {verwacht} hoort. "
        f"Dat is {abs(verschil)} jaar {richting}."
    )
    if regel is not None:
        melding += f" {regel.toelichting}."
    if not zeker:
        melding += (
            " Deze perioderegel is nog niet tegen de praktijk bevestigd; "
            "controleer hem voordat je hierop afgaat."
        )

    return PeriodCheck(
        document_kind=document_kind,
        aangiftejaar=aangiftejaar,
        expected_year=verwacht,
        found_year=found_year,
        is_correct=False,
        is_certain=zeker,
        message=melding,
    )


def check_all_documents(
    documenten: List[tuple],
    aangiftejaar: int,
) -> List[PeriodCheck]:
    """Controleer een reeks documenten in één keer.

    Args:
        documenten: Reeks van (DocumentKind, jaar of None).
        aangiftejaar: Jaar waarover de aangifte gaat.

    Returns:
        Een PeriodCheck per document, in dezelfde volgorde.
    """
    uitkomsten = [
        check_document_period(soort, aangiftejaar, jaar)
        for soort, jaar in documenten
    ]

    afwijkend = [u for u in uitkomsten if u.needs_attention]
    if afwijkend:
        logger.warning(
            "%d van %d documenten horen niet bij aangiftejaar %d",
            len(afwijkend), len(uitkomsten), aangiftejaar,
        )
    return uitkomsten

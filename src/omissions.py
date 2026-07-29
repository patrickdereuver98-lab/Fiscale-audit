"""
FiscAudit AI - Omissiecontrole

De aansluiting loopt over de posten die in de aangifte staan en controleert of
die kloppen. Dat vindt geen vergeten aftrekpost: staat een post niet in de
aangifte, dan is er niets om te controleren.

Deze module loopt de andere kant op. Voor elk feit dat in de brondocumenten
staat wordt nagegaan of het in de aangifte terugkomt. Zo komt een AOV-premie
van 2.400 euro die wel op het premieoverzicht staat maar niet in de aangifte,
wel naar boven.

Afspraak: dit is altijd een opmerking. Er wordt niet zelf beoordeeld of de post
terecht is weggelaten, bijvoorbeeld omdat de aftrekruimte al vol zat. Die
afweging is aan de reviewer, die de bevinding kan afdoen met een onderbouwing.
De database eist die onderbouwing bij het accorderen, zodat de reden wordt
vastgelegd en de bevinding bij een volgende run niet opnieuw opvalt.

Drie soorten uitkomst:
    OMISSIE       staat in de bron, niet in de aangifte
    NULWAARDE     staat in de aangifte op nul, terwijl de bron een bedrag geeft
    ONBEKEND_LABEL  staat in de aangifte, maar de tool kent de post niet
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .domain import FindingKind, RiskLevel
from .posten import POSTEN, Post, PostSoort, post_voor_label


logger = logging.getLogger(__name__)


# Onder dit bedrag levert een omissie geen bevinding op. Een aangifte gaat in
# hele euro's en een post van een paar euro is geen gesprek waard; die zou het
# overzicht juist onbruikbaar maken. Bewust laag gehouden, want het doel is
# ruis wegnemen en niet posten verbergen.
OMISSIE_DREMPEL_EUR = 25.00


# ============================================================================
# UITKOMST
# ============================================================================

@dataclass
class Omissie:
    """Een post die in de brondocumenten staat maar niet in de aangifte."""

    post_key: str
    naam: str
    soort: PostSoort
    bedrag_uit_bron_eur: float
    bedrag_in_aangifte_eur: Optional[float]
    kind: FindingKind = FindingKind.OMISSION
    toelichting: str = ""

    @property
    def post(self) -> Post:
        """De bijbehorende postdefinitie."""
        return POSTEN[self.post_key]

    @property
    def bevinding_sleutel(self) -> str:
        """Vaste sleutel voor de behandelstatus in de database.

        Op de postsleutel en niet op het bedrag, zodat een accordering een
        volgende run overleeft. Het bedrag wordt apart bewaard, zodat een
        gewijzigd bedrag de bevinding weer opent.
        """
        return f"omissie:{self.post_key}"

    @property
    def risico(self) -> RiskLevel:
        """Zwaarte, naar het bedrag en de aard van de post.

        Een vergeten aftrekpost kost de klant geld maar levert geen naheffing
        op. Een vergeten bezitting of inkomen kan tot een correctie met rente
        leiden en weegt bij hetzelfde bedrag daarom zwaarder.
        """
        bedrag = abs(self.bedrag_uit_bron_eur)
        te_laag_aangegeven = self.soort in (PostSoort.INKOMEN, PostSoort.BEZITTING)

        if te_laag_aangegeven:
            if bedrag > 25_000:
                return RiskLevel.CRITICAL
            if bedrag > 2_500:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        if bedrag > 25_000:
            return RiskLevel.HIGH
        if bedrag > 1_000:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @property
    def melding(self) -> str:
        """Nederlandse melding voor de reviewnote."""
        bedrag = _bedrag(self.bedrag_uit_bron_eur)

        if self.kind == FindingKind.OMISSION:
            kern = (
                f"{self.naam} van {bedrag} staat in de brondocumenten, maar komt "
                f"niet terug in de aangifte."
            )
        else:
            kern = (
                f"{self.naam} staat in de aangifte op "
                f"{_bedrag(self.bedrag_in_aangifte_eur or 0)}, terwijl de "
                f"brondocumenten {bedrag} laten zien."
            )

        return f"{kern} Gevolg: {self.soort.omissie_gevolg}."


@dataclass
class OmissieRapport:
    """Uitkomst van de volledige omissiecontrole."""

    omissies: List[Omissie] = field(default_factory=list)
    onbekende_labels: List[Tuple[str, float]] = field(default_factory=list)
    gecontroleerde_posten: int = 0

    @property
    def needs_attention(self) -> bool:
        """Of er iets op het dashboard hoort."""
        return bool(self.omissies) or bool(self.onbekende_labels)

    @property
    def risico(self) -> RiskLevel:
        """Zwaarste risico onder de omissies."""
        return RiskLevel.highest(o.risico for o in self.omissies)

    @property
    def gemiste_aftrek_eur(self) -> float:
        """Aftrek die in de bron staat en niet in de aangifte.

        Dit is het bedrag dat de klant onbenut laat. Apart van de rest, omdat
        het de andere kant op werkt dan een te lage aangifte.
        """
        return round(sum(
            o.bedrag_uit_bron_eur for o in self.omissies
            if o.soort == PostSoort.AFTREK
        ), 2)

    @property
    def te_laag_aangegeven_eur(self) -> float:
        """Inkomen en bezittingen die niet in de aangifte staan."""
        return round(sum(
            o.bedrag_uit_bron_eur for o in self.omissies
            if o.soort in (PostSoort.INKOMEN, PostSoort.BEZITTING)
        ), 2)


# ============================================================================
# CONTROLE
# ============================================================================

def _bedrag(waarde: float) -> str:
    """Bedrag in Nederlandse notatie."""
    getal = f"{abs(waarde):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{'-' if waarde < 0 else ''}€ {getal}"


def check_omissies(
    extracted_data: Any,
    aangifte_bedragen: Dict[str, float],
    drempel_eur: float = OMISSIE_DREMPEL_EUR,
) -> OmissieRapport:
    """Zoek posten die in de brondocumenten staan maar niet in de aangifte.

    Args:
        extracted_data: De uitgelezen brondocumenten.
        aangifte_bedragen: De aangifte, als afbeelding van postsleutel naar
            bedrag. Wat het aangifterapport onder een onbekend label vermeldt,
            hoort hier niet in maar in `onbekende_labels` van het rapport; zie
            `check_omissies_op_labels` voor de variant die labels aanneemt.
        drempel_eur: Bedragen hieronder leveren geen bevinding op.

    Returns:
        OmissieRapport met alles wat ontbreekt.
    """
    rapport = OmissieRapport()

    for sleutel, post in POSTEN.items():
        if not post.omissie_melden:
            continue

        try:
            uit_bron = post.herleiden(extracted_data)
        except Exception as exc:
            logger.error("Herleiden van %s mislukt: %s", sleutel, exc)
            continue

        # Geen onderbouwing in de documenten: dan valt er niets te missen.
        # Dat is het omgekeerde geval en hoort bij de aansluiting.
        if uit_bron is None:
            continue

        rapport.gecontroleerde_posten += 1

        if abs(uit_bron) < drempel_eur:
            continue

        in_aangifte = aangifte_bedragen.get(sleutel)

        if in_aangifte is None:
            rapport.omissies.append(Omissie(
                post_key=sleutel,
                naam=post.naam,
                soort=post.soort,
                bedrag_uit_bron_eur=round(uit_bron, 2),
                bedrag_in_aangifte_eur=None,
                kind=FindingKind.OMISSION,
                toelichting=post.toelichting,
            ))
            continue

        # De post staat er wel, maar op nul terwijl de bron een bedrag geeft.
        # Feitelijk hetzelfde gemis, alleen anders ingevuld.
        if abs(in_aangifte) < 0.01 and abs(uit_bron) >= drempel_eur:
            rapport.omissies.append(Omissie(
                post_key=sleutel,
                naam=post.naam,
                soort=post.soort,
                bedrag_uit_bron_eur=round(uit_bron, 2),
                bedrag_in_aangifte_eur=0.0,
                kind=FindingKind.OMISSION,
                toelichting=post.toelichting,
            ))

    if rapport.omissies:
        logger.info(
            "%d omissies gevonden. Gemiste aftrek %s, te laag aangegeven %s",
            len(rapport.omissies),
            _bedrag(rapport.gemiste_aftrek_eur),
            _bedrag(rapport.te_laag_aangegeven_eur),
        )

    return rapport


def map_aangifte_labels(
    regels: Dict[str, float],
    eindstanden: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, float], List[Tuple[str, float]]]:
    """Zet labels uit het aangifterapport om naar postsleutels.

    Args:
        regels: Wat er in het rapport staat, als label naar bedrag.

    Returns:
        (bedragen per postsleutel, lijst van onbekende labels met hun bedrag)

    Een rapport noemt hetzelfde bedrag meestal meerdere keren: in de
    samenvatting, in de specificatie en als totaal. Die tellen niet bij elkaar
    op. Een eerdere versie deed dat wel en maakte van een AOV-premie van 7.502
    een bedrag van 22.506, en van een eigenwoningschuld van 421.719 het
    dubbele. Daarom wordt per post een van de gevonden regels gekozen en niet
    gesommeerd.

    De keuze volgt de volgorde van `aangifte_labels` in posten.py: de eerst
    genoemde schrijfwijze die in het rapport voorkomt wint. Zo staat de
    voorkeur in de postdefinitie en niet in een vuistregel hier.

    Aftrekposten en schulden staan in een rapport vaak negatief, omdat ze het
    inkomen verlagen. Dat is een presentatiekeuze, dus voor die soorten wordt
    de absolute waarde genomen; anders levert elke aftrekpost een verschil op
    met het positieve bedrag uit het brondocument.

    Onbekende labels worden apart teruggegeven en niet weggegooid. Een label
    dat de tool niet kent betekent dat POSTEN moet worden aangevuld; stil
    negeren zou een post ongemerkt buiten de controle houden, en dat is precies
    de fout die deze tool moet vinden.
    """
    # Per post alle gevonden regels, met de rangorde van het label erbij.
    kandidaten: Dict[str, List[Tuple[int, str, float]]] = {}
    onbekend: List[Tuple[str, float]] = []

    for label, bedrag in regels.items():
        post = post_voor_label(label)
        if post is None:
            onbekend.append((label, bedrag))
            logger.warning("Onbekend label in het aangifterapport: %r", label)
            continue

        rang = _label_rangorde(post, label)
        kandidaten.setdefault(post.key, []).append((rang, label, float(bedrag)))

    per_post: Dict[str, float] = {}
    for sleutel, gevonden in kandidaten.items():
        gevonden.sort(key=lambda item: item[0])
        _, gekozen_label, bedrag = gevonden[0]

        post = POSTEN[sleutel]

        # Sommige posten horen bij de eindstand en niet bij de peildatum.
        if post.gebruik_eindstand and eindstanden:
            eind = eindstanden.get(gekozen_label)
            if eind is not None:
                bedrag = eind

        if post.soort in (PostSoort.AFTREK, PostSoort.SCHULD):
            bedrag = abs(bedrag)

        per_post[sleutel] = bedrag

        if len(gevonden) > 1:
            afwijkend = {round(abs(b), 2) for _, _, b in gevonden}
            if len(afwijkend) > 1:
                logger.info(
                    "Post %s komt in het rapport voor met verschillende bedragen "
                    "%s; %r is gebruikt",
                    sleutel, sorted(afwijkend), gekozen_label,
                )

    return per_post, onbekend


def _label_rangorde(post: Post, label: str) -> int:
    """Waar dit label staat in de voorkeurslijst van de post.

    Een lager getal is een sterkere voorkeur. Labels die niet letterlijk in de
    lijst staan maar via normalisatie zijn gekoppeld, komen achteraan.
    """
    from .posten import normaliseer_label

    genormaliseerd = normaliseer_label(label)
    for index, kandidaat in enumerate(post.aangifte_labels):
        if normaliseer_label(kandidaat) == genormaliseerd:
            return index
    return len(post.aangifte_labels)


def check_omissies_op_labels(
    extracted_data: Any,
    aangifte_regels: Dict[str, float],
    drempel_eur: float = OMISSIE_DREMPEL_EUR,
) -> OmissieRapport:
    """Omissiecontrole rechtstreeks op de labels uit het aangifterapport.

    Args:
        extracted_data: De uitgelezen brondocumenten.
        aangifte_regels: Wat er in het rapport staat, als label naar bedrag.
        drempel_eur: Bedragen hieronder leveren geen bevinding op.

    Returns:
        OmissieRapport, met de onbekende labels erin opgenomen.
    """
    per_post, onbekend = map_aangifte_labels(aangifte_regels)
    rapport = check_omissies(extracted_data, per_post, drempel_eur)
    rapport.onbekende_labels = onbekend
    return rapport

"""
FiscAudit AI - Aangifteposten

Vervangt de eerdere AG-codetabel. Die tabel bestond uit codes die ik zelf had
bedacht en die niet tegen de aangiftesoftware te controleren waren. Nu wordt er
gemapt op de omschrijvingen zoals die in het AFAS-aangifterapport staan, met
per post een aantal schrijfwijzen omdat rapportlabels niet exact voorspelbaar
zijn.

Elke post koppelt drie dingen aan elkaar:
  1. de omschrijvingen waaronder de post in het aangifterapport kan staan
  2. hoe het bedrag uit de brondocumenten wordt herleid
  3. wat de aard van de post is, want dat bepaalt wat een omissie betekent

De aard is niet cosmetisch. Een vergeten aftrekpost betekent dat de klant te
veel betaalt. Een vergeten bezitting betekent een te lage aangifte met risico
op correctie. Beide moeten worden gemeld, maar de reviewnote hoort het verschil
te benoemen.

TE BEVESTIGEN
De labels in AANGIFTE_LABELS zijn een eerste opzet. Ze moeten tegen een echt
AFAS-rapport worden nagelopen. Onbekende labels in het rapport worden niet
stilzwijgend genegeerd maar apart teruggegeven, zodat het aanvullen van deze
tabel een aanwijsbare stap is en niet iets dat je pas na maanden opvalt.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


logger = logging.getLogger(__name__)


# ============================================================================
# AARD VAN EEN POST
# ============================================================================

class PostSoort(str, Enum):
    """Aard van een aangiftepost.

    Bepaalt wat een afwijking of omissie betekent voor de klant, en dus hoe de
    bevinding in de reviewnote wordt verwoord.
    """

    INKOMEN = "INKOMEN"
    AFTREK = "AFTREK"
    BEZITTING = "BEZITTING"
    SCHULD = "SCHULD"

    @property
    def label(self) -> str:
        """Nederlandse omschrijving."""
        return _SOORT_LABELS[self.value]

    @property
    def omissie_gevolg(self) -> str:
        """Wat het betekent wanneer deze post ontbreekt in de aangifte.

        Gebruikt in de reviewnote, zodat er niet alleen staat dat iets ontbreekt
        maar ook welke kant het op werkt.
        """
        return _OMISSIE_GEVOLG[self.value]


_SOORT_LABELS = {
    "INKOMEN": "Inkomen",
    "AFTREK": "Aftrekpost",
    "BEZITTING": "Bezitting",
    "SCHULD": "Schuld",
}

_OMISSIE_GEVOLG = {
    "INKOMEN": "de aangifte is te laag; risico op een correctie met rente",
    "AFTREK": "de klant betaalt te veel belasting; aftrek is niet benut",
    "BEZITTING": "de aangifte is te laag; risico op een correctie met rente",
    "SCHULD": "de aangifte is te hoog; de klant betaalt mogelijk te veel",
}


# ============================================================================
# HERLEIDING UIT DE BRONDOCUMENTEN
# ============================================================================

def _som_loon(data: Any) -> Optional[float]:
    """Bruto loon over alle jaaropgaven, uitkeringen uitgezonderd."""
    posten = [p for p in getattr(data, "employment_income", []) if not p.is_benefit]
    return float(sum(p.gross_salary_eur for p in posten)) if posten else None


def _som_uitkering(data: Any) -> Optional[float]:
    """Bruto uitkering over alle jaaropgaven."""
    posten = [p for p in getattr(data, "employment_income", []) if p.is_benefit]
    return float(sum(p.gross_salary_eur for p in posten)) if posten else None


def _som_loonheffing(data: Any) -> Optional[float]:
    """Ingehouden loonheffing over alle jaaropgaven."""
    posten = getattr(data, "employment_income", [])
    return float(sum(p.payroll_tax_eur for p in posten)) if posten else None


def _som_aov_premie(data: Any) -> Optional[float]:
    """Premie voor arbeidsongeschiktheidsverzekeringen."""
    posten = [
        p for p in getattr(data, "insurance_premiums", [])
        if p.policy_kind.upper() == "AOV"
    ]
    return float(sum(p.annual_premium_eur for p in posten)) if posten else None


def _som_lijfrente_premie(data: Any) -> Optional[float]:
    """Betaalde lijfrentepremie."""
    posten = [
        p for p in getattr(data, "annuities", []) if p.premium_paid_eur is not None
    ]
    return float(sum(p.premium_paid_eur for p in posten)) if posten else None


def _som_lijfrente_uitkering(data: Any) -> Optional[float]:
    """Ontvangen lijfrente-uitkering."""
    posten = [
        p for p in getattr(data, "annuities", []) if p.benefit_received_eur is not None
    ]
    return float(sum(p.benefit_received_eur for p in posten)) if posten else None


def _som_banksaldo(data: Any) -> Optional[float]:
    """Saldo van alle rekeningen.

    Een lege lijst geeft None (geen bewijs), een aangetroffen rekening met saldo
    nul geeft 0.0 (bewijs van een nulstand). Dat onderscheid bepaalt of iets als
    ontbrekend of als aansluitend wordt gemeld.
    """
    rekeningen = getattr(data, "bank_accounts", [])
    return float(sum(r.balance_eur for r in rekeningen)) if rekeningen else None


def _som_woz(data: Any) -> Optional[float]:
    """WOZ-waarde naar eigendomsdeel.

    Bij gedeeld eigendom hoort alleen het eigen aandeel in de aangifte; de volle
    waarde nemen levert bij 50 procent eigendom een factor twee fout op.
    """
    panden = getattr(data, "real_estate", [])
    if not panden:
        return None
    return float(sum(
        p.woz_value_eur * getattr(p, "ownership_pct", 100.0) / 100.0 for p in panden
    ))


def _som_hypotheekrente(data: Any) -> Optional[float]:
    """Betaalde hypotheekrente.

    Voorkeur voor het bedrag dat de jaaropgave zelf noemt. Ontbreekt dat, dan
    benaderd als restschuld maal rentepercentage. Die benadering overschat bij
    een annuitaire lening omdat de schuld tijdens het jaar daalt, en de post
    wordt daarom als benadering gemarkeerd.
    """
    leningen = getattr(data, "mortgages", [])
    if not leningen:
        return None
    totaal = 0.0
    for lening in leningen:
        gerapporteerd = getattr(lening, "annual_interest_paid_eur", None)
        if gerapporteerd is not None:
            totaal += float(gerapporteerd)
        else:
            totaal += (
                float(getattr(lening, "current_balance_eur", 0.0))
                * float(getattr(lening, "interest_rate_pct", 0.0)) / 100.0
            )
    return totaal


def _som_hypotheekschuld(data: Any) -> Optional[float]:
    """Restschuld van alle leningen."""
    leningen = getattr(data, "mortgages", [])
    return float(sum(l.current_balance_eur for l in leningen)) if leningen else None


def _winst(data: Any) -> Optional[float]:
    """Bruto ondernemingsresultaat."""
    inkomen = getattr(data, "business_income", None)
    return float(inkomen.gross_income_eur) if inkomen else None


def _ondernemingskosten(data: Any) -> Optional[float]:
    """Aftrekbare ondernemingskosten."""
    inkomen = getattr(data, "business_income", None)
    return float(inkomen.deductible_expenses_eur) if inkomen else None


def _direct(veld: str) -> Callable[[Any], Optional[float]]:
    """Herleider voor een enkel getalveld op het hoofdmodel."""
    def herleid(data: Any) -> Optional[float]:
        waarde = getattr(data, veld, None)
        return float(waarde) if waarde is not None else None
    return herleid


# ============================================================================
# POSTEN
# ============================================================================

@dataclass(frozen=True)
class Post:
    """Een post in de aangifte, met de herleiding uit de brondocumenten.

    Attributes:
        key: Vaste sleutel, gebruikt in de database en in de bevindingsleutel.
            Wijzigt niet, ook niet wanneer het label in het rapport wijzigt.
        naam: Nederlandse omschrijving voor de reviewnote.
        soort: Aard van de post.
        aangifte_labels: Schrijfwijzen waaronder de post in het aangifterapport
            kan staan. De vergelijking negeert hoofdletters en leestekens.
        herleiden: Functie die het bedrag uit de brondocumenten haalt, of None
            wanneer er geen onderbouwing in de documenten te vinden is.
        toelichting: Uitleg voor de reviewnote.
        is_benadering: True wanneer het herleide bedrag een schatting is.
        omissie_melden: True wanneer het ontbreken van deze post in de aangifte
            altijd een bevinding is. Per afspraak staat dit overal op True: als
            een brondocument een post laat zien en de aangifte niet, is dat
            altijd een opmerking. De reviewer kan hem afdoen met onderbouwing.
    """

    key: str
    naam: str
    soort: PostSoort
    aangifte_labels: List[str]
    herleiden: Callable[[Any], Optional[float]]
    toelichting: str = ""
    is_benadering: bool = False
    omissie_melden: bool = True
    # Welke kolom van het rapport bij deze post hoort wanneer er twee staan.
    # Box 3 gaat over 1 januari, dus daar de beginstand. Maar de
    # hypotheekjaaropgave geeft de schuld per 31 december, dus daar moet tegen
    # de eindstand worden vergeleken; anders levert een kloppend dossier een
    # verschil op ter grootte van de aflossing over het jaar.
    gebruik_eindstand: bool = False


POSTEN: Dict[str, Post] = {

    # ---------------- box 1: inkomen ----------------

    "loon": Post(
        key="loon",
        naam="Loon uit dienstbetrekking",
        soort=PostSoort.INKOMEN,
        aangifte_labels=[
            "Bruto loon", "Loon", "Loon uit tegenwoordige dienstbetrekking",
            "Loon en salaris",
        ],
        herleiden=_som_loon,
        toelichting="Bruto loon volgens de jaaropgaven van de werkgevers",
    ),

    "uitkering": Post(
        key="uitkering",
        naam="Uitkering",
        soort=PostSoort.INKOMEN,
        aangifte_labels=[
            "Uitkering", "Loon uit vroegere dienstbetrekking", "Pensioen",
            "AOW-uitkering", "Bruto uitkering",
        ],
        herleiden=_som_uitkering,
        toelichting="Bruto uitkering volgens de jaaropgave van de uitkerende instantie",
    ),

    "loonheffing": Post(
        key="loonheffing",
        naam="Ingehouden loonheffing",
        soort=PostSoort.AFTREK,
        aangifte_labels=[
            "Ingehouden loonheffing", "Loonheffing", "Loonbelasting",
            "Ingehouden loonbelasting",
        ],
        herleiden=_som_loonheffing,
        toelichting="Loonheffing volgens de jaaropgaven; wordt verrekend met de aanslag",
    ),

    "winst_onderneming": Post(
        key="winst_onderneming",
        naam="Bruto ondernemingsresultaat",
        soort=PostSoort.INKOMEN,
        # Volgorde is voorkeur. "Winst volgens jaarrekening" staat vooraan
        # omdat dat het getal is dat tegen de jaarrekening wordt gecontroleerd.
        # De belastbare winst staat verderop in het rapport en is die na
        # ondernemersaftrek en winstvrijstelling, dus een ander bedrag dat niet
        # met de jaarrekening hoort aan te sluiten.
        aangifte_labels=[
            "Winst volgens jaarrekening",
            "Winst uit ondernemerschap",
            "Winst uit onderneming", "Bruto winst", "Omzet",
            "Netto omzet", "Resultaat onderneming",
        ],
        herleiden=_winst,
        toelichting="Omzet of bruto resultaat volgens de jaarrekening",
    ),

    "lijfrente_uitkering": Post(
        key="lijfrente_uitkering",
        naam="Lijfrente-uitkering",
        soort=PostSoort.INKOMEN,
        aangifte_labels=[
            "Lijfrente-uitkering", "Lijfrente uitkering", "Periodieke uitkering",
        ],
        herleiden=_som_lijfrente_uitkering,
        toelichting="Ontvangen lijfrente volgens de opgave van de aanbieder",
    ),

    # ---------------- box 1: aftrekposten ----------------

    "aov_premie": Post(
        key="aov_premie",
        naam="Premie arbeidsongeschiktheidsverzekering",
        soort=PostSoort.AFTREK,
        aangifte_labels=[
            "Betaalde AOV-premie", "AOV-premie", "Premie AOV",
            "Premie arbeidsongeschiktheidsverzekering",
            "Betaalde premie arbeidsongeschiktheidsverzekering",
            # Zoals het in een echt rapport staat, in het meervoud. De
            # specifieke regel gaat voor de bredere container: onder
            # inkomensvoorzieningen kan ook een lijfrente vallen.
            "Premies arbeidsongeschiktheidsverzekeringen "
            "(geen Zorgverzekeringswet)",
            "Premies arbeidsongeschiktheidsverzekeringen",
            "Totaal uitgaven voor inkomensvoorzieningen",
            "Premies voor inkomensvoorzieningen",
        ],
        herleiden=_som_aov_premie,
        toelichting=(
            "Premie volgens het premieoverzicht van de verzekeraar. Deze post "
            "wordt in de praktijk regelmatig vergeten"
        ),
    ),

    "lijfrente_premie": Post(
        key="lijfrente_premie",
        naam="Betaalde lijfrentepremie",
        soort=PostSoort.AFTREK,
        aangifte_labels=[
            "Betaalde lijfrentepremie", "Lijfrentepremie", "Premie lijfrente",
            "Inleg lijfrente",
        ],
        herleiden=_som_lijfrente_premie,
        toelichting=(
            "Inleg volgens de opgave van de aanbieder. Aftrek is begrensd door "
            "de beschikbare ruimte; die berekening hoort bij de inhoudelijke toets"
        ),
    ),

    "hypotheekrente": Post(
        key="hypotheekrente",
        naam="Betaalde hypotheekrente",
        soort=PostSoort.AFTREK,
        aangifte_labels=[
            "Betaalde hypotheekrente", "Hypotheekrente", "Rente eigenwoningschuld",
            "Betaalde rente eigen woning", "Rente en kosten eigenwoningschuld",
            # Zoals het in een echt rapport staat, onder de eigen woning.
            "Totaal aftrekposten van de eigen woning",
            "Aftrekbaar bedrag betaalde rente",
        ],
        herleiden=_som_hypotheekrente,
        toelichting="Betaalde rente volgens de hypotheekjaaropgave",
        is_benadering=True,
    ),

    "ondernemingskosten": Post(
        key="ondernemingskosten",
        naam="Aftrekbare ondernemingskosten",
        soort=PostSoort.AFTREK,
        aangifte_labels=[
            "Kosten onderneming", "Bedrijfskosten", "Aftrekbare kosten",
            "Totaal kosten",
        ],
        herleiden=_ondernemingskosten,
        toelichting="Kosten volgens de jaarrekening",
    ),

    "kia": Post(
        key="kia",
        naam="Kleinschaligheidsinvesteringsaftrek",
        soort=PostSoort.AFTREK,
        aangifte_labels=[
            "Kleinschaligheidsinvesteringsaftrek", "KIA",
            "Investeringsaftrek", "Kleinschaligheidsaftrek",
        ],
        herleiden=_direct("kia_profit_eur"),
        toelichting=(
            "Geclaimde investeringsaftrek. De schijven en de drempel horen bij "
            "de inhoudelijke toets en staan niet in deze code"
        ),
    ),

    "overige_aftrek": Post(
        key="overige_aftrek",
        naam="Overige persoonsgebonden aftrek",
        soort=PostSoort.AFTREK,
        aangifte_labels=[
            "Persoonsgebonden aftrek", "Overige aftrekposten",
            "Giften", "Specifieke zorgkosten",
        ],
        herleiden=_direct("deductible_items_eur"),
        toelichting="Overige aftrek volgens de aangeleverde stukken",
    ),

    # ---------------- box 1: eigen woning ----------------

    "woz_eigen_woning": Post(
        key="woz_eigen_woning",
        naam="WOZ-waarde eigen woning",
        soort=PostSoort.BEZITTING,
        aangifte_labels=[
            "WOZ-waarde woning", "WOZ-waarde eigen woning", "WOZ-waarde",
            "Vastgestelde waarde woning",
            "Waarde van de woning (WOZ-waarde)",
        ],
        herleiden=_som_woz,
        toelichting=(
            "WOZ-waarde naar eigendomsdeel volgens de beschikking. Het "
            "eigenwoningforfait wordt hiervan afgeleid en niet hier berekend"
        ),
    ),

    "eigenwoningforfait": Post(
        key="eigenwoningforfait",
        naam="Eigenwoningforfait",
        soort=PostSoort.INKOMEN,
        aangifte_labels=[
            "Eigenwoningforfait",
            "Totaal inkomsten uit de eigen woning",
        ],
        # Volgt uit de WOZ-waarde via een schijventabel die per jaar wijzigt en
        # die in de kernwaarden staat, niet hier. Zonder geverifieerde tabel is
        # deze post niet na te rekenen en levert hij geen bevinding op.
        herleiden=lambda data: None,
        toelichting=(
            "Wordt berekend uit de WOZ-waarde. Narekenen vraagt de "
            "forfaittabel van het aangiftejaar uit de kernwaarden"
        ),
    ),

    "eigenwoningschuld": Post(
        key="eigenwoningschuld",
        naam="Eigenwoningschuld",
        soort=PostSoort.SCHULD,
        gebruik_eindstand=True,
        aangifte_labels=[
            "Eigenwoningschuld van aftrekbare geldleningen",
            "Totaal eigenwoningschulden",
            "Eigenwoningschuld", "Hypotheekschuld eigen woning",
            "Restschuld eigen woning", "Schuld eigen woning",
        ],
        herleiden=_som_hypotheekschuld,
        toelichting="Restschuld volgens de hypotheekjaaropgave",
    ),

    # ---------------- box 3 ----------------

    "bank_spaartegoeden": Post(
        key="bank_spaartegoeden",
        naam="Bank- en spaartegoeden",
        soort=PostSoort.BEZITTING,
        aangifte_labels=[
            "Bank- en spaartegoeden", "Banktegoeden", "Spaartegoeden",
            "Bankrekeningen", "Saldo bank- en spaarrekeningen",
            # Zoals het in een echt rapport staat. Premiedepots vallen onder
            # dezelfde post, dus een verschil met de bankoverzichten kan een
            # premiedepot zijn waarvoor het stuk nog ontbreekt.
            "Totaal premiedepots, bank- en spaartegoeden in Nederland "
            "(excl. groene beleggingen)",
            "Premiedepots, bank- en spaartegoeden in Nederland",
        ],
        herleiden=_som_banksaldo,
        toelichting=(
            "Saldo op de peildatum 1 januari van het aangiftejaar, wat gelijk "
            "is aan het eindsaldo per 31 december van het jaar ervoor"
        ),
    ),

    "overige_bezittingen": Post(
        key="overige_bezittingen",
        naam="Overige bezittingen en beleggingen",
        soort=PostSoort.BEZITTING,
        aangifte_labels=[
            "Overige bezittingen", "Beleggingen", "Effecten",
            "Aandelen en obligaties", "Overige vorderingen",
        ],
        herleiden=_direct("other_assets_eur"),
        toelichting="Effecten en overige bezittingen op de peildatum",
    ),

    "schulden_box3": Post(
        key="schulden_box3",
        naam="Schulden box 3",
        soort=PostSoort.SCHULD,
        aangifte_labels=[
            "Schulden", "Overige schulden", "Schulden box 3",
        ],
        herleiden=_som_hypotheekschuld,
        toelichting="Restschuld van leningen op de peildatum",
    ),
}


# ============================================================================
# LABELS OPZOEKEN
# ============================================================================

_VULWOORDEN = frozenset({"de", "het", "een", "en", "van", "uit", "in", "op", "totaal"})


def normaliseer_label(label: str) -> str:
    """Breng een label terug tot vergelijkbare vorm.

    Verwijdert hoofdletters, leestekens en vulwoorden, zodat "Betaalde
    AOV-premie", "betaalde aov premie" en "Premie AOV" op hetzelfde uitkomen.
    Zonder deze stap mist de koppeling op een streepje of een lidwoord.
    """
    woorden = re.split(r"[^0-9a-z]+", label.lower())
    kern = [w for w in woorden if w and w not in _VULWOORDEN]
    return " ".join(sorted(kern))


# Opzoektabel van genormaliseerd label naar postsleutel, eenmalig opgebouwd.
_LABEL_INDEX: Dict[str, str] = {}
for _post in POSTEN.values():
    for _label in _post.aangifte_labels:
        _genormaliseerd = normaliseer_label(_label)
        if _genormaliseerd in _LABEL_INDEX and _LABEL_INDEX[_genormaliseerd] != _post.key:
            logger.warning(
                "Label %r hoort bij zowel %s als %s; de eerste blijft gelden",
                _label, _LABEL_INDEX[_genormaliseerd], _post.key,
            )
        else:
            _LABEL_INDEX[_genormaliseerd] = _post.key


def post_voor_label(label: str) -> Optional[Post]:
    """Zoek de post die bij een label uit het aangifterapport hoort.

    Args:
        label: De omschrijving zoals die in het rapport staat.

    Returns:
        De bijbehorende Post, of None wanneer het label niet bekend is.
        Onbekende labels horen niet stilzwijgend te verdwijnen; de aanroeper
        moet ze apart melden zodat POSTEN kan worden aangevuld.
    """
    return POSTEN.get(_LABEL_INDEX.get(normaliseer_label(label), ""), None)


def alle_labels() -> Set[str]:
    """Alle genormaliseerde labels die de tool herkent."""
    return set(_LABEL_INDEX)

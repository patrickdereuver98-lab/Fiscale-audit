"""
FiscAudit AI - Controles op de uitlezing zelf

De aansluiting vergelijkt de aangifte met de brondocumenten. Maar die
vergelijking is alleen zinvol als de brondocumenten goed zijn gelezen. Deze
module controleert dat.

WAAROM DIT STERKER IS DAN EEN TWEEDE MODEL

Een tweede taalmodel dat hetzelfde document opnieuw leest, geeft een tweede
mening. Bij een slecht leesbare scan geven twee modellen vaak hetzelfde
plausibele maar verkeerde getal, omdat ze dezelfde faalmodus hebben. Twee
bevestigingen van één fout voelen veiliger dan een enkele lezing, en zijn dat
niet.

Een cross-foot geeft geen mening maar een bewijs. Een hypotheekjaaropgave noemt
de delen en het totaal:

    leningdeel 1    334.322
    leningdeel 2     87.397
    totaal          421.719

Tellen de delen op tot het genoemde totaal, dan is elk deel goed gelezen. Er is
geen scenario waarin twee verkeerd gelezen bedragen precies uitkomen op een
derde verkeerd gelezen bedrag, anders dan bij toeval. Dat is zekerheid.

DAAROM DE VOLGORDE
    1. cross-foot waar het document een totaal noemt        bewijs
    2. tweede lezing waar dat totaal ontbreekt              aanwijzing
    3. alles wat niet te controleren is wordt een bevinding  geen stille aanname

Punt 3 is het belangrijkst. Een controle die bij twijfel doorgaat is geen
controle.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .domain import RiskLevel


logger = logging.getLogger(__name__)


# Een aangifte gaat in hele euro's en documenten ronden af, dus een cross-foot
# mag een paar euro afwijken door afronding per regel. Ruimer dan dit betekent
# dat er een bedrag mist of verkeerd is gelezen.
CROSSFOOT_MARGE_EUR = 2.00


class ControleSoort(str, Enum):
    """Wat een controle aantoont."""

    CROSSFOOT = "CROSSFOOT"          # bewijs: delen tellen op tot het genoemde totaal
    TWEEDE_LEZING = "TWEEDE_LEZING"  # aanwijzing: twee modellen lazen hetzelfde
    DEKKING = "DEKKING"              # elke aangegeven post heeft een brondocument
    PLAUSIBILITEIT = "PLAUSIBILITEIT"  # het getal kan niet kloppen

    @property
    def label(self) -> str:
        """Nederlandse omschrijving."""
        return _SOORT_LABELS[self.value]

    @property
    def geeft_zekerheid(self) -> bool:
        """Of deze controle bewijst dat de uitlezing goed is.

        Alleen de cross-foot doet dat. De rest is een aanwijzing, en dat
        onderscheid hoort in de reviewnote te staan zodat niemand een
        aanwijzing voor een bewijs aanziet.
        """
        return self == ControleSoort.CROSSFOOT


_SOORT_LABELS = {
    "CROSSFOOT": "Telling sluit",
    "TWEEDE_LEZING": "Tweede lezing",
    "DEKKING": "Onderbouwing aanwezig",
    "PLAUSIBILITEIT": "Aannemelijkheid",
}


@dataclass
class Controle:
    """Uitkomst van één controle op de uitlezing."""

    soort: ControleSoort
    onderwerp: str
    geslaagd: bool
    som_onderdelen: Optional[float] = None
    genoemd_totaal: Optional[float] = None
    toelichting: str = ""

    @property
    def verschil(self) -> Optional[float]:
        """Verschil tussen de som en het genoemde totaal."""
        if self.som_onderdelen is None or self.genoemd_totaal is None:
            return None
        return round(self.som_onderdelen - self.genoemd_totaal, 2)

    @property
    def risico(self) -> RiskLevel:
        """Zwaarte wanneer deze controle niet slaagt.

        Een mislukte cross-foot weegt zwaar: dan is er een bedrag verkeerd
        gelezen en is de hele aansluiting op dat onderdeel onbetrouwbaar. Er
        valt dan niets te concluderen over de aangifte, en dat is erger dan een
        gevonden afwijking.
        """
        if self.geslaagd:
            return RiskLevel.LOW
        if self.soort == ControleSoort.CROSSFOOT:
            return RiskLevel.CRITICAL
        if self.soort == ControleSoort.PLAUSIBILITEIT:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM

    @property
    def melding(self) -> str:
        """Nederlandse melding voor de reviewnote."""
        if self.geslaagd:
            return f"{self.onderwerp}: {self.soort.label.lower()}."

        if self.soort == ControleSoort.CROSSFOOT:
            return (
                f"{self.onderwerp}: de losse bedragen tellen op tot "
                f"{_bedrag(self.som_onderdelen)}, terwijl het document zelf "
                f"{_bedrag(self.genoemd_totaal)} noemt. Verschil "
                f"{_bedrag(self.verschil)}. Er is een bedrag verkeerd gelezen of "
                f"er mist een regel; de aansluiting op dit onderdeel is niet "
                f"betrouwbaar tot dit is uitgezocht."
            )

        return f"{self.onderwerp}: {self.toelichting}"


@dataclass
class ControleRapport:
    """Alle controles op de uitlezing van een dossier."""

    controles: List[Controle] = field(default_factory=list)

    @property
    def gefaald(self) -> List[Controle]:
        """De controles die niet slagen."""
        return [c for c in self.controles if not c.geslaagd]

    @property
    def uitlezing_is_bewezen(self) -> bool:
        """Of elke uitgevoerde cross-foot slaagt.

        Is dit False, dan is er iets verkeerd gelezen en heeft het geen zin om
        conclusies over de aangifte te trekken. De reviewnote hoort dat bovenaan
        te zetten en niet ergens tussen de andere bevindingen.
        """
        crossfoots = [
            c for c in self.controles if c.soort == ControleSoort.CROSSFOOT
        ]
        return all(c.geslaagd for c in crossfoots)

    @property
    def aantal_bewezen(self) -> int:
        """Aantal geslaagde cross-foots."""
        return sum(
            1 for c in self.controles
            if c.soort == ControleSoort.CROSSFOOT and c.geslaagd
        )

    @property
    def risico(self) -> RiskLevel:
        """Zwaarste risico onder de mislukte controles."""
        return RiskLevel.highest(c.risico for c in self.gefaald)


def _bedrag(waarde: Optional[float]) -> str:
    """Bedrag in Nederlandse notatie."""
    if waarde is None:
        return "onbekend"
    getal = f"{abs(waarde):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{'-' if waarde < 0 else ''}€ {getal}"


# ============================================================================
# CROSS-FOOT
# ============================================================================

def crossfoot(
    onderwerp: str,
    onderdelen: List[float],
    genoemd_totaal: Optional[float],
    marge_eur: float = CROSSFOOT_MARGE_EUR,
) -> Optional[Controle]:
    """Controleer of de losse bedragen optellen tot het genoemde totaal.

    Args:
        onderwerp: Wat er wordt geteld, voor de melding.
        onderdelen: De losse bedragen uit het document.
        genoemd_totaal: Het totaal zoals het document het zelf noemt. None
            betekent dat het document geen totaal geeft; dan is er niets te
            controleren en komt er None terug in plaats van een geslaagde
            controle. Doen alsof er is gecontroleerd is erger dan niet
            controleren.
        marge_eur: Toegestane afwijking door afronding per regel.

    Returns:
        Een Controle, of None wanneer er niets te controleren was.
    """
    if genoemd_totaal is None or not onderdelen:
        return None

    som = round(sum(onderdelen), 2)
    sluit = abs(som - genoemd_totaal) <= marge_eur

    if not sluit:
        logger.warning(
            "Cross-foot %s sluit niet: som %s, genoemd totaal %s",
            onderwerp, som, genoemd_totaal,
        )

    return Controle(
        soort=ControleSoort.CROSSFOOT,
        onderwerp=onderwerp,
        geslaagd=sluit,
        som_onderdelen=som,
        genoemd_totaal=genoemd_totaal,
        toelichting=f"{len(onderdelen)} bedragen geteld",
    )


def controleer_uitlezing(extracted_data: Any) -> ControleRapport:
    """Voer alle mogelijke controles op de uitgelezen gegevens uit.

    Args:
        extracted_data: De uitgelezen brondocumenten.

    Returns:
        ControleRapport met per controle of die slaagt.
    """
    rapport = ControleRapport()
    totalen: Dict[str, float] = getattr(extracted_data, "stated_totals", {}) or {}

    # ---- hypotheek: delen tegen het genoemde totaal ----
    leningen = getattr(extracted_data, "mortgages", []) or []
    if leningen:
        schulden = [
            float(l.current_balance_eur) for l in leningen
            if getattr(l, "current_balance_eur", None) is not None
        ]
        controle = crossfoot(
            "Hypotheekschuld per leningdeel",
            schulden,
            totalen.get("mortgage_debt_total"),
        )
        if controle:
            rapport.controles.append(controle)

        rentes = [
            float(l.annual_interest_paid_eur) for l in leningen
            if getattr(l, "annual_interest_paid_eur", None) is not None
        ]
        controle = crossfoot(
            "Hypotheekrente per leningdeel",
            rentes,
            totalen.get("mortgage_interest_total"),
        )
        if controle:
            rapport.controles.append(controle)

    # ---- bank: rekeningen tegen het genoemde totaal ----
    rekeningen = getattr(extracted_data, "bank_accounts", []) or []
    if rekeningen:
        saldi = [float(r.balance_eur) for r in rekeningen]
        controle = crossfoot(
            "Banksaldi per rekening",
            saldi,
            totalen.get("bank_balance_total_peildatum"),
        )
        if controle:
            rapport.controles.append(controle)

    # ---- loon: jaaropgaven tegen het genoemde totaal ----
    loonposten = getattr(extracted_data, "employment_income", []) or []
    if loonposten:
        lonen = [float(p.gross_salary_eur) for p in loonposten]
        controle = crossfoot(
            "Loon per jaaropgave",
            lonen,
            totalen.get("employment_income_total"),
        )
        if controle:
            rapport.controles.append(controle)

    rapport.controles.extend(_plausibiliteit(extracted_data))
    return rapport


# ============================================================================
# PLAUSIBILITEIT
# ============================================================================

def _plausibiliteit(extracted_data: Any) -> List[Controle]:
    """Controles die niet van een genoemd totaal afhangen.

    Deze vangen leesfouten die een cross-foot mist omdat het document geen
    totaal noemt. Ze bewijzen niets, maar ze sluiten uit wat niet kan.
    """
    controles: List[Controle] = []

    for lening in getattr(extracted_data, "mortgages", []) or []:
        schuld = getattr(lening, "current_balance_eur", None)
        rente = getattr(lening, "annual_interest_paid_eur", None)
        if schuld is None or rente is None or schuld <= 0:
            continue

        # Rente boven 20 procent van de schuld kan bij een woninghypotheek niet.
        # Zo'n verhouding wijst op een verwisseling van schuld en rente, of op
        # een verschoven decimaalteken.
        verhouding = rente / schuld * 100
        klopt = verhouding <= 20

        controles.append(Controle(
            soort=ControleSoort.PLAUSIBILITEIT,
            onderwerp=f"Verhouding rente en schuld ({_bedrag(schuld)})",
            geslaagd=klopt,
            toelichting=(
                f"de rente is {verhouding:.1f} procent van de schuld, wat voor "
                f"een woninghypotheek niet kan. Waarschijnlijk zijn schuld en "
                f"rente verwisseld of staat er een decimaalteken verkeerd"
                if not klopt else
                f"de rente is {verhouding:.1f} procent van de schuld"
            ),
        ))

    for pand in getattr(extracted_data, "real_estate", []) or []:
        deel = getattr(pand, "ownership_pct", 100.0)
        # 100 procent is de standaardwaarde van het model. Staat er een ander
        # percentage, dan is dat uit het document gehaald en verdient het een
        # expliciete bevestiging: bij gedeeld eigendom hoort maar een deel in de
        # aangifte en dat is een factorfout als het misgaat.
        if deel != 100.0:
            controles.append(Controle(
                soort=ControleSoort.PLAUSIBILITEIT,
                onderwerp=f"Eigendomsdeel {pand.address[:40]}",
                geslaagd=True,
                toelichting=(
                    f"het document vermeldt {deel:.0f} procent eigendom; alleen "
                    f"dat deel van de WOZ-waarde hoort in de aangifte. "
                    f"Controleer dit tegen de beschikking"
                ),
            ))

    return controles


# ============================================================================
# TWEEDE LEZING
# ============================================================================

def vergelijk_lezingen(
    eerste: Dict[str, Any],
    tweede: Dict[str, Any],
    marge_eur: float = 1.00,
) -> List[Controle]:
    """Vergelijk twee onafhankelijke uitlezingen van hetzelfde document.

    Bedoeld voor documenten die geen totaal noemen, want daar kan een cross-foot
    niets. Dit is een aanwijzing en geen bewijs: twee modellen kunnen dezelfde
    leesfout maken, vooral bij een slecht leesbare scan. Wijken ze af, dan is er
    zeker iets mis; komen ze overeen, dan is dat geen garantie.

    Args:
        eerste: Uitlezing van het eerste model, als platte afbeelding van veld
            naar getal.
        tweede: Uitlezing van het tweede model, in dezelfde vorm.
        marge_eur: Toegestane afwijking.

    Returns:
        Een Controle per veld dat in beide voorkomt, plus een per veld dat maar
        in een van de twee zit.
    """
    controles: List[Controle] = []

    for veld in sorted(set(eerste) | set(tweede)):
        a, b = eerste.get(veld), tweede.get(veld)

        if a is None or b is None:
            welke = "het eerste" if b is None else "het tweede"
            controles.append(Controle(
                soort=ControleSoort.TWEEDE_LEZING,
                onderwerp=veld,
                geslaagd=False,
                toelichting=(
                    f"alleen {welke} model heeft dit bedrag gevonden. Een van "
                    f"beide heeft iets gemist of iets verzonnen; controleer het "
                    f"document"
                ),
            ))
            continue

        gelijk = abs(float(a) - float(b)) <= marge_eur
        controles.append(Controle(
            soort=ControleSoort.TWEEDE_LEZING,
            onderwerp=veld,
            geslaagd=gelijk,
            som_onderdelen=float(a),
            genoemd_totaal=float(b),
            toelichting=(
                "beide lezingen komen overeen" if gelijk else
                f"de lezingen wijken af: {_bedrag(float(a))} tegenover "
                f"{_bedrag(float(b))}. Lees het bedrag zelf na in het document"
            ),
        ))

    return controles


def platte_bedragen(extracted_data: Any) -> Dict[str, float]:
    """Zet een uitlezing om naar veld-naar-bedrag, voor de vergelijking.

    Gebruikt een aanduiding per regel die niet van de volgorde afhangt, zodat
    twee modellen die de rekeningen in een andere volgorde teruggeven toch te
    vergelijken zijn.
    """
    plat: Dict[str, float] = {}

    for rekening in getattr(extracted_data, "bank_accounts", []) or []:
        nummer = str(getattr(rekening, "account_number", "")).replace(" ", "")
        plat[f"saldo {nummer[-6:]}"] = float(rekening.balance_eur)

    for index, lening in enumerate(getattr(extracted_data, "mortgages", []) or []):
        schuld = getattr(lening, "current_balance_eur", None)
        if schuld is not None:
            plat[f"schuld lening {round(float(schuld))}"] = float(schuld)
        rente = getattr(lening, "annual_interest_paid_eur", None)
        if rente is not None:
            plat[f"rente lening {index + 1}"] = float(rente)

    for pand in getattr(extracted_data, "real_estate", []) or []:
        adres = str(getattr(pand, "address", ""))[:20]
        plat[f"WOZ {adres}"] = float(pand.woz_value_eur)

    for post in getattr(extracted_data, "employment_income", []) or []:
        werkgever = str(getattr(post, "employer_name", ""))[:20]
        plat[f"loon {werkgever}"] = float(post.gross_salary_eur)

    for premie in getattr(extracted_data, "insurance_premiums", []) or []:
        verzekeraar = str(getattr(premie, "insurer_name", ""))[:20]
        plat[f"premie {verzekeraar}"] = float(premie.annual_premium_eur)

    return plat

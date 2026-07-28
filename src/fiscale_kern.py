"""
FiscAudit AI - Fiscale kernwaarden

Eén centrale bron voor tarieven, drempels en grenzen per belastingjaar. De
deterministische controles lezen hier rechtstreeks uit: geen modelaanroep per
berekening, dus snel en zonder kosten. Alleen bij het verversen komt er een
model aan te pas, en dan uitsluitend om voorstellen te doen.

Twee dingen die vaak door elkaar worden gehaald en hier bewust gescheiden zijn:

    kernwaarden (deze module)   getallen: schijven, drempels, percentages.
                                Machinaal te gebruiken in een berekening.
    kennisregels (schema.sql,   tekst: hoe werkt de bijleenregeling, welke
    tabel fiscale_kennis)       kosten zijn financieringskosten. Bedoeld voor
                                de inhoudelijke toets, niet voor rekenwerk.

DE BELANGRIJKSTE EIGENSCHAP
Een waarde die nooit is nagekeken wordt niet stilzwijgend gebruikt. `waarde()`
geeft dan None en de aanroeper moet daarop reageren. Dat is met opzet
onhandig: een verouderd of verzonnen tarief dat er als een gewoon getal uitkomt
is de gevaarlijkste fout die deze tool kan maken, want die is aan de uitkomst
niet te zien.

WERKWIJZE BIJ VERVERSEN
Verversen levert voorstellen op, nooit wijzigingen. Elk voorstel heeft een bron
met verwijzing. De adviseur keurt per stuk goed. Pas daarna wordt de waarde
opgeslagen, met naam en datum van wie het heeft nagekeken. Zonder die stap zou
een model zijn eigen invoer valideren, en bevestigt een fout zichzelf.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


# Terugvalbestand wanneer Supabase niet bereikbaar of niet ingesteld is.
KERN_BESTAND = Path(__file__).resolve().parent.parent / "data" / "fiscale_kern.json"


# ============================================================================
# EEN ENKELE WAARDE
# ============================================================================

@dataclass
class Kernwaarde:
    """Eén fiscaal getal voor één belastingjaar.

    Attributes:
        sleutel: Vaste aanduiding, gebruikt in de code. Wijzigt niet.
        naam: Nederlandse omschrijving voor de monitor.
        belastingjaar: Jaar waarvoor de waarde geldt.
        waarde: Het getal, of een structuur bij een schijventabel. None
            betekent dat de waarde nog niet is vastgesteld.
        eenheid: "EUR", "procent" of "tabel".
        bron_naam: Waar de waarde is nagekeken.
        bron_url: Verwijzing naar die bron.
        laatst_geverifieerd: Datum waarop een mens dit heeft nagekeken.
        geverifieerd_door: Wie dat heeft gedaan.
        toelichting: Waar de waarde voor dient.
    """

    sleutel: str
    naam: str
    belastingjaar: int
    waarde: Optional[Any] = None
    eenheid: str = "EUR"
    bron_naam: str = ""
    bron_url: str = ""
    laatst_geverifieerd: Optional[str] = None
    geverifieerd_door: str = ""
    toelichting: str = ""

    @property
    def is_bruikbaar(self) -> bool:
        """Of deze waarde in een berekening mag worden gebruikt.

        Vereist zowel een waarde als een verificatie door een mens. Een getal
        zonder verificatie is een aanname, en een aanname hoort niet in een
        fiscale conclusie terecht te komen zonder dat iemand dat weet.
        """
        return self.waarde is not None and bool(self.laatst_geverifieerd)

    @property
    def status(self) -> str:
        """Korte status voor de monitor."""
        if self.waarde is None:
            return "Niet vastgesteld"
        if not self.laatst_geverifieerd:
            return "Niet geverifieerd"
        return "Geverifieerd"

    @property
    def dagen_oud(self) -> Optional[int]:
        """Aantal dagen sinds de laatste verificatie."""
        if not self.laatst_geverifieerd:
            return None
        try:
            gecontroleerd = date.fromisoformat(self.laatst_geverifieerd)
        except ValueError:
            return None
        return (date.today() - gecontroleerd).days


# ============================================================================
# VOORSTEL TOT WIJZIGING
# ============================================================================

@dataclass
class Voorstel:
    """Een voorgestelde wijziging, nog niet doorgevoerd."""

    sleutel: str
    naam: str
    belastingjaar: int
    huidige_waarde: Optional[Any]
    nieuwe_waarde: Optional[Any]
    bron_naam: str = ""
    bron_url: str = ""
    toelichting: str = ""
    fout: str = ""

    @property
    def is_afwijkend(self) -> bool:
        """Of dit voorstel iets verandert."""
        return not self.fout and self.nieuwe_waarde != self.huidige_waarde

    @property
    def is_mislukt(self) -> bool:
        """Of het nakijken van deze waarde is mislukt."""
        return bool(self.fout)

    @property
    def heeft_bron(self) -> bool:
        """Of er een verwijzing bij zit.

        Een voorstel zonder bron mag niet worden goedgekeurd: dan is er niets
        om tegen na te kijken en komt het getal alleen uit het model.
        """
        return bool(self.bron_url.strip())


# ============================================================================
# VERZAMELING
# ============================================================================

@dataclass
class Kernwaarden:
    """Alle kernwaarden voor één belastingjaar."""

    belastingjaar: int
    waarden: Dict[str, Kernwaarde] = field(default_factory=dict)
    bron: str = "onbekend"  # "supabase" of "json"

    def waarde(self, sleutel: str) -> Optional[Any]:
        """Het getal achter een sleutel, of None.

        Geeft None wanneer de sleutel niet bestaat, wanneer er geen waarde is,
        of wanneer de waarde niet is nagekeken. De aanroeper moet daar iets mee
        doen; stil doorrekenen met een aanname is precies wat hier wordt
        voorkomen.
        """
        kern = self.waarden.get(sleutel)
        if kern is None:
            logger.warning("Onbekende kernwaarde %r voor %d", sleutel, self.belastingjaar)
            return None
        if not kern.is_bruikbaar:
            logger.warning(
                "Kernwaarde %r voor %d is %s en wordt niet gebruikt",
                sleutel, self.belastingjaar, kern.status.lower(),
            )
            return None
        return kern.waarde

    def vereist(self, sleutel: str) -> Any:
        """Als `waarde`, maar werpt een fout in plaats van None terug te geven.

        Voor berekeningen die zonder deze waarde geen zinnige uitkomst hebben.
        Beter een duidelijke fout dan een getal dat op een aanname rust.

        Raises:
            KernwaardeOntbreekt: Wanneer de waarde niet bruikbaar is.
        """
        uitkomst = self.waarde(sleutel)
        if uitkomst is None:
            kern = self.waarden.get(sleutel)
            reden = kern.status.lower() if kern else "niet aanwezig"
            raise KernwaardeOntbreekt(
                f"Kernwaarde {sleutel!r} voor belastingjaar "
                f"{self.belastingjaar} is {reden}. Verifieer de waarde in de "
                f"Data Monitor voordat deze controle kan worden uitgevoerd."
            )
        return uitkomst

    @property
    def aantal_bruikbaar(self) -> int:
        """Aantal waarden dat gebruikt mag worden."""
        return sum(1 for k in self.waarden.values() if k.is_bruikbaar)

    @property
    def aantal_ontbreekt(self) -> int:
        """Aantal waarden dat nog nagekeken moet worden."""
        return sum(1 for k in self.waarden.values() if not k.is_bruikbaar)

    @property
    def is_volledig(self) -> bool:
        """Of alle waarden zijn nagekeken."""
        return bool(self.waarden) and self.aantal_ontbreekt == 0

    def status_overzicht(self) -> List[Dict[str, Any]]:
        """Tabel voor de Data Monitor, ontbrekende waarden bovenaan."""
        rijen = [
            {
                "Sleutel": k.sleutel,
                "Waarde": _toon_waarde(k),
                "Eenheid": k.eenheid,
                "Status": k.status,
                "Laatst geverifieerd": k.laatst_geverifieerd or "nooit",
                "Door": k.geverifieerd_door or "",
                "Bron": k.bron_naam or "",
                "Omschrijving": k.naam,
            }
            for k in self.waarden.values()
        ]
        rangorde = {"Niet vastgesteld": 0, "Niet geverifieerd": 1, "Geverifieerd": 2}
        return sorted(rijen, key=lambda r: (rangorde.get(r["Status"], 9), r["Sleutel"]))


class KernwaardeOntbreekt(RuntimeError):
    """Een berekening vraagt een kernwaarde die niet is nagekeken."""


def _toon_waarde(kern: Kernwaarde) -> str:
    """Waarde als tekst voor de monitor."""
    if kern.waarde is None:
        return "—"
    if kern.eenheid == "tabel":
        aantal = len(kern.waarde) if isinstance(kern.waarde, (list, dict)) else 1
        return f"{aantal} regels"
    if kern.eenheid == "procent":
        return f"{kern.waarde}".replace(".", ",") + "%"
    if isinstance(kern.waarde, (int, float)):
        getal = f"{kern.waarde:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
        return f"€ {getal}"
    return str(kern.waarde)


# ============================================================================
# WELKE WAARDEN DE TOOL NODIG HEEFT
# ============================================================================
# Alleen de structuur. De getallen worden hier met opzet niet ingevuld: die
# wijzigen per jaar en een gok zou als vastgesteld getal uit de tool komen.
# Elke waarde begint op "niet vastgesteld" en moet via de Data Monitor worden
# nagekeken en goedgekeurd.

BENODIGDE_WAARDEN: List[Dict[str, str]] = [
    {
        "sleutel": "box3_heffingvrij_vermogen",
        "naam": "Heffingvrij vermogen box 3",
        "eenheid": "EUR",
        "toelichting": "Drempel waaronder box 3 niet tot heffing leidt",
    },
    {
        "sleutel": "box3_forfait_spaargeld",
        "naam": "Forfaitair rendement bank- en spaartegoeden",
        "eenheid": "procent",
        "toelichting": "Percentage over spaargeld in box 3",
    },
    {
        "sleutel": "box3_forfait_beleggingen",
        "naam": "Forfaitair rendement overige bezittingen",
        "eenheid": "procent",
        "toelichting": "Percentage over beleggingen en overige bezittingen",
    },
    {
        "sleutel": "box3_forfait_schulden",
        "naam": "Forfaitair rendement schulden",
        "eenheid": "procent",
        "toelichting": "Percentage over schulden in box 3",
    },
    {
        "sleutel": "box3_drempel_schulden",
        "naam": "Drempel schulden box 3",
        "eenheid": "EUR",
        "toelichting": "Bedrag waarboven schulden meetellen",
    },
    {
        "sleutel": "eigenwoningforfait_tabel",
        "naam": "Eigenwoningforfait, schijven naar WOZ-waarde",
        "eenheid": "tabel",
        "toelichting": "Percentages per WOZ-schijf voor het eigenwoningforfait",
    },
    {
        "sleutel": "kia_tabel",
        "naam": "Kleinschaligheidsinvesteringsaftrek, schijven",
        "eenheid": "tabel",
        "toelichting": "Investeringsbedragen en bijbehorende aftrek",
    },
    {
        "sleutel": "zelfstandigenaftrek",
        "naam": "Zelfstandigenaftrek",
        "eenheid": "EUR",
        "toelichting": "Bedrag van de zelfstandigenaftrek",
    },
    {
        "sleutel": "startersaftrek",
        "naam": "Startersaftrek",
        "eenheid": "EUR",
        "toelichting": "Verhoging van de zelfstandigenaftrek voor starters",
    },
    {
        "sleutel": "mkb_winstvrijstelling",
        "naam": "MKB-winstvrijstelling",
        "eenheid": "procent",
        "toelichting": "Percentage van de winst dat is vrijgesteld",
    },
    {
        "sleutel": "urencriterium",
        "naam": "Urencriterium",
        "eenheid": "uren",
        "toelichting": "Aantal uren voor de ondernemersaftrek",
    },
    {
        "sleutel": "giftenaftrek_drempel_pct",
        "naam": "Drempel giftenaftrek, percentage van het drempelinkomen",
        "eenheid": "procent",
        "toelichting": "Percentage waarboven gewone giften aftrekbaar zijn",
    },
    {
        "sleutel": "giftenaftrek_drempel_min",
        "naam": "Minimumdrempel giftenaftrek",
        "eenheid": "EUR",
        "toelichting": "Ondergrens van de drempel voor gewone giften",
    },
    {
        "sleutel": "ib_schijven",
        "naam": "Schijven inkomstenbelasting box 1",
        "eenheid": "tabel",
        "toelichting": "Grenzen en tarieven per schijf",
    },
]


def lege_kernwaarden(belastingjaar: int) -> Kernwaarden:
    """Alle benodigde waarden voor een jaar, nog niet vastgesteld."""
    return Kernwaarden(
        belastingjaar=belastingjaar,
        bron="leeg",
        waarden={
            beschrijving["sleutel"]: Kernwaarde(
                sleutel=beschrijving["sleutel"],
                naam=beschrijving["naam"],
                belastingjaar=belastingjaar,
                eenheid=beschrijving["eenheid"],
                toelichting=beschrijving["toelichting"],
            )
            for beschrijving in BENODIGDE_WAARDEN
        },
    )


# ============================================================================
# LADEN EN OPSLAAN
# ============================================================================

def laad_uit_json(belastingjaar: int, pad: Path = KERN_BESTAND) -> Optional[Kernwaarden]:
    """Lees de kernwaarden uit het terugvalbestand.

    Returns:
        Kernwaarden, of None wanneer het bestand er niet is of niet te lezen is.
    """
    if not pad.exists():
        logger.info("Terugvalbestand %s bestaat niet", pad)
        return None

    try:
        with open(pad, "r", encoding="utf-8") as bestand:
            inhoud = json.load(bestand)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Terugvalbestand niet te lezen: %s", exc)
        return None

    per_jaar = inhoud.get("jaren", {}).get(str(belastingjaar))
    if not per_jaar:
        logger.info("Geen kernwaarden voor %d in het terugvalbestand", belastingjaar)
        return None

    basis = lege_kernwaarden(belastingjaar)
    basis.bron = "json"
    for sleutel, gegevens in per_jaar.items():
        if sleutel not in basis.waarden:
            # Onbekende sleutel: opnemen en niet weggooien, zodat een
            # uitbreiding in de database niet stil verdwijnt.
            basis.waarden[sleutel] = Kernwaarde(
                sleutel=sleutel, naam=gegevens.get("naam", sleutel),
                belastingjaar=belastingjaar,
            )
        kern = basis.waarden[sleutel]
        kern.waarde = gegevens.get("waarde")
        kern.eenheid = gegevens.get("eenheid", kern.eenheid)
        kern.bron_naam = gegevens.get("bron_naam", "")
        kern.bron_url = gegevens.get("bron_url", "")
        kern.laatst_geverifieerd = gegevens.get("laatst_geverifieerd")
        kern.geverifieerd_door = gegevens.get("geverifieerd_door", "")

    return basis


def bewaar_in_json(kernwaarden: Kernwaarden, pad: Path = KERN_BESTAND) -> bool:
    """Schrijf de kernwaarden naar het terugvalbestand.

    Bestaande jaren blijven staan; alleen het betreffende jaar wordt vervangen.
    """
    inhoud: Dict[str, Any] = {"jaren": {}}
    if pad.exists():
        try:
            with open(pad, "r", encoding="utf-8") as bestand:
                inhoud = json.load(bestand)
        except (OSError, json.JSONDecodeError):
            logger.warning("Bestaand bestand niet te lezen, wordt overschreven")

    inhoud.setdefault("jaren", {})[str(kernwaarden.belastingjaar)] = {
        sleutel: {
            "naam": kern.naam,
            "waarde": kern.waarde,
            "eenheid": kern.eenheid,
            "bron_naam": kern.bron_naam,
            "bron_url": kern.bron_url,
            "laatst_geverifieerd": kern.laatst_geverifieerd,
            "geverifieerd_door": kern.geverifieerd_door,
        }
        for sleutel, kern in kernwaarden.waarden.items()
    }
    inhoud["_meta"] = {
        "laatst_gewijzigd": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        pad.parent.mkdir(parents=True, exist_ok=True)
        with open(pad, "w", encoding="utf-8") as bestand:
            json.dump(inhoud, bestand, indent=2, ensure_ascii=False)
        return True
    except OSError as exc:
        logger.error("Kernwaarden niet op te slaan: %s", exc)
        return False


def laad_kernwaarden(
    belastingjaar: int,
    supabase_lezer: Optional[Callable[[int], Optional[Kernwaarden]]] = None,
) -> Kernwaarden:
    """Laad de kernwaarden, Supabase eerst en anders het bestand.

    Args:
        belastingjaar: Jaar waarvoor de waarden gelden.
        supabase_lezer: Functie die de waarden uit de database haalt. Wordt
            meegegeven in plaats van hier geimporteerd, zodat deze module te
            gebruiken en te testen is zonder databaseverbinding.

    Returns:
        Kernwaarden. Nooit None: bij een lege bron komen alle benodigde
        waarden terug op "niet vastgesteld", zodat de monitor kan tonen wat er
        ontbreekt in plaats van een leeg scherm.
    """
    if supabase_lezer is not None:
        try:
            uit_database = supabase_lezer(belastingjaar)
            if uit_database is not None and uit_database.waarden:
                uit_database.bron = "supabase"
                return uit_database
        except Exception as exc:
            logger.error("Kernwaarden uit Supabase lezen mislukt: %s", exc)

    uit_bestand = laad_uit_json(belastingjaar)
    if uit_bestand is not None:
        return uit_bestand

    logger.warning(
        "Geen kernwaarden gevonden voor %d; alles staat op niet vastgesteld",
        belastingjaar,
    )
    return lege_kernwaarden(belastingjaar)


# ============================================================================
# VERVERSEN
# ============================================================================

def maak_voorstellen(
    kernwaarden: Kernwaarden,
    nakijker: Callable[[Kernwaarde], Dict[str, Any]],
    voortgang: Optional[Callable[[str], None]] = None,
) -> List[Voorstel]:
    """Kijk elke waarde na en lever voorstellen op.

    Voert niets door. De uitkomst is een lijst voorstellen die de adviseur per
    stuk goedkeurt.

    Args:
        kernwaarden: De huidige waarden.
        nakijker: Functie die één waarde nakijkt tegen een officiele bron en
            een afbeelding teruggeeft met de sleutels `waarde`, `bron_naam`,
            `bron_url` en `toelichting`. Meegegeven en niet hier ingebouwd,
            zodat de bron uitwisselbaar is en deze functie te testen is zonder
            netwerk of model.
        voortgang: Wordt aangeroepen met een korte melding per waarde.

    Returns:
        Een voorstel per waarde, ook wanneer er niets wijzigt.
    """
    voorstellen: List[Voorstel] = []

    for kern in kernwaarden.waarden.values():
        if voortgang:
            voortgang(f"{kern.naam} nakijken")

        try:
            uitkomst = nakijker(kern)
            voorstellen.append(Voorstel(
                sleutel=kern.sleutel,
                naam=kern.naam,
                belastingjaar=kern.belastingjaar,
                huidige_waarde=kern.waarde,
                nieuwe_waarde=uitkomst.get("waarde"),
                bron_naam=uitkomst.get("bron_naam", ""),
                bron_url=uitkomst.get("bron_url", ""),
                toelichting=uitkomst.get("toelichting", ""),
            ))
        except Exception as exc:
            logger.error("Nakijken van %s mislukt: %s", kern.sleutel, exc)
            voorstellen.append(Voorstel(
                sleutel=kern.sleutel,
                naam=kern.naam,
                belastingjaar=kern.belastingjaar,
                huidige_waarde=kern.waarde,
                nieuwe_waarde=None,
                fout=str(exc),
            ))

    return voorstellen


def pas_voorstellen_toe(
    kernwaarden: Kernwaarden,
    voorstellen: List[Voorstel],
    goedgekeurde_sleutels: List[str],
    geverifieerd_door: str,
    op_datum: Optional[date] = None,
) -> List[str]:
    """Voer de goedgekeurde voorstellen door.

    Args:
        kernwaarden: Wordt bijgewerkt.
        voorstellen: De uitkomst van `maak_voorstellen`.
        goedgekeurde_sleutels: Welke voorstellen zijn goedgekeurd.
        geverifieerd_door: Naam van degene die heeft nagekeken. Verplicht:
            zonder naam is de verificatie niet herleidbaar en is de status
            "geverifieerd" een lege mededeling.
        op_datum: Datum van verificatie, standaard vandaag.

    Returns:
        De sleutels die daadwerkelijk zijn bijgewerkt.

    Raises:
        ValueError: Wanneer er geen naam is meegegeven.
    """
    if not geverifieerd_door.strip():
        raise ValueError(
            "Geef de naam van degene die de waarden heeft nagekeken. Zonder "
            "naam is de verificatie niet herleidbaar."
        )

    datum = (op_datum or date.today()).isoformat()
    goedgekeurd = set(goedgekeurde_sleutels)
    bijgewerkt: List[str] = []

    for voorstel in voorstellen:
        if voorstel.sleutel not in goedgekeurd:
            continue
        if voorstel.is_mislukt:
            logger.warning(
                "Voorstel voor %s is mislukt en wordt niet doorgevoerd",
                voorstel.sleutel,
            )
            continue
        if not voorstel.heeft_bron:
            # Zonder verwijzing is er niets om tegen na te kijken; het getal
            # zou dan alleen op het model rusten.
            logger.warning(
                "Voorstel voor %s heeft geen bron en wordt niet doorgevoerd",
                voorstel.sleutel,
            )
            continue

        kern = kernwaarden.waarden.get(voorstel.sleutel)
        if kern is None:
            continue

        kern.waarde = voorstel.nieuwe_waarde
        kern.bron_naam = voorstel.bron_naam
        kern.bron_url = voorstel.bron_url
        kern.laatst_geverifieerd = datum
        kern.geverifieerd_door = geverifieerd_door.strip()
        bijgewerkt.append(voorstel.sleutel)

    logger.info(
        "%d van %d goedgekeurde waarden bijgewerkt voor %d",
        len(bijgewerkt), len(goedgekeurd), kernwaarden.belastingjaar,
    )
    return bijgewerkt

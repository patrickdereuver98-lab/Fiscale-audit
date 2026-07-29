"""
FiscAudit AI - Aangifterapport uitlezen

De aangiftekant van de controle. Het rapport heeft een vaste indeling: regels
van tabs gescheiden, met de omschrijving vooraan en de bedragen achteraan.

DRIE DINGEN DIE UIT ECHTE RAPPORTEN BLEKEN EN DIE FOUT GAAN ALS JE ZE NIET WEET

1. Sommige tabellen hebben twee bedragkolommen: de stand per 1 januari en die
   per 31 december. Box 3 gaat over 1 januari. Wie de laatste kolom pakt leest
   de eindstand, en dat verschil liep op een echt dossier op tot 25.000 euro
   zonder dat er een melding kwam. Welke kolom de juiste is staat in de
   kolomkop erboven ("01-01-2024 / 31-12-2024", of "Begin jaar / Einde jaar").

2. Een rekeningnummer is ook een getal. Op de renteregels staat het nummer
   vlak voor het bedrag, dus zonder kolomkop pak je het verkeerde veld. Daarom
   wordt de kolom uit de kop bepaald en niet uit de vorm van het getal.

3. Labels als "Bezittingen", "Schulden", "Aftrekbaar bedrag" en "Totaal rente"
   komen meerdere keren voor met verschillende betekenis. De sectiekop erboven
   geeft de betekenis, dus die wordt meegenomen.

Bij Word en RTF gebeurt dit deterministisch: zonder model en dus zonder
leesfout aan de aangiftekant. De vergelijking met de brondocumenten blijft
daarmee een harde check. Bij PDF is een modelaanroep nodig; dan wordt de
uitkomst gemarkeerd als modelgelezen.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# Een veld is een bedrag als het hele veld een getal is. Nederlandse notatie:
# punt als duizendscheiding, komma als decimaalteken. Rapporten geven hele
# euro's ("97.179"), specificaties soms met decimalen ("100,00").
_HEEL_VELD_BEDRAG = re.compile(r"^-?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?-?$|^-?\d+(?:,\d{1,2})?-?$")

# Kolomkoppen die aangeven welke kolom welk bedrag bevat.
_PEILDATUM_KOP = re.compile(r"01-01|1-1-|begin\s*jaar|beginstand", re.IGNORECASE)
_EINDSTAND_KOP = re.compile(r"31-12|einde\s*jaar|eindstand", re.IGNORECASE)
_BEDRAG_KOP = re.compile(r"^(rente|bedrag|waarde|saldo)$", re.IGNORECASE)
_KOP_WOORDEN = re.compile(
    r"omschrijving|begindatum|einddatum|hypotheek\s*/",
    re.IGNORECASE,
)
# Kolommen met een nummer dat geen bedrag is.
_NUMMERKOLOM = re.compile(r"rekeningnr|rekeningnummer|polis|nummer$", re.IGNORECASE)

# Regels die nooit een aangiftepost zijn.
_NEGEER_LABEL = re.compile(
    r"^(pagina|bladnummer|blad|datum|d\.d\.|kenmerk|dossier|bsn|beconnummer"
    r"|postcode|woonplaats|landcode|adres|activiteiten|rsin|boekjaar|periode"
    r"|percentage\s+eigendom|status|soort\s+lening|leningdeelnummer"
    r"|bankrekeningnr)\b",
    re.IGNORECASE,
)


@dataclass
class AangifteRegel:
    """Eén regel uit het aangifterapport."""

    label: str
    bedrag: float
    sectie: str = ""
    eindstand: Optional[float] = None
    is_modelgelezen: bool = False
    ruwe_regel: str = ""

    @property
    def volledige_aanduiding(self) -> str:
        """Label met de sectie erbij, voor regels die alleen niet eenduidig zijn."""
        return f"{self.sectie} · {self.label}" if self.sectie else self.label


@dataclass
class Aangifte:
    """De ingevulde aangifte, zoals uit het rapport gelezen."""

    aangiftejaar: Optional[int] = None
    bestandsnaam: str = ""
    is_modelgelezen: bool = False
    regels: List[AangifteRegel] = field(default_factory=list)
    niet_herkende_regels: List[str] = field(default_factory=list)

    def als_labels(self) -> Dict[str, float]:
        """De regels als afbeelding van label naar bedrag.

        Bij dubbele labels blijft de eerste staan. Rapporten herhalen een
        totaal vaak in de samenvatting en in de specificatie; de eerste
        vermelding is de samenvatting en dat is de post zoals aangegeven.
        """
        per_label: Dict[str, float] = {}
        for regel in self.regels:
            per_label.setdefault(regel.label, regel.bedrag)
        return per_label

    def bedrag_van(self, label_deel: str) -> Optional[float]:
        """Zoek een bedrag op een deel van het label, hoofdletterongevoelig."""
        zoek = label_deel.lower()
        for regel in self.regels:
            if zoek in regel.label.lower():
                return regel.bedrag
        return None

    @property
    def aantal_regels(self) -> int:
        """Aantal gelezen regels."""
        return len(self.regels)


def parse_bedrag(veld: str) -> Optional[float]:
    """Zet een veld om naar een getal, of geef None als het geen bedrag is.

    Het hele veld moet een getal zijn. Zo wordt "NL46 RABO 0341 7455 53" niet
    als bedrag gelezen en "9,32%" evenmin.

    Nederlandse notatie: de punt is duizendscheiding en de komma is het
    decimaalteken, omgekeerd aan het Engels. "97.179" is zevenennegentigduizend
    en niet zevenennegentig.
    """
    schoon = veld.strip().replace("\u00a0", " ").replace("€", "").strip()
    if not schoon or not _HEEL_VELD_BEDRAG.match(schoon):
        return None

    achterstaand_min = schoon.endswith("-")
    schoon = schoon.rstrip("-")

    try:
        waarde = float(schoon.replace(".", "").replace(",", "."))
    except ValueError:
        return None

    # "1.000,00-" betekent min duizend; het minteken staat achter het bedrag.
    return -abs(waarde) if achterstaand_min else waarde


@dataclass
class _Kolomkop:
    """Welke kolom welk bedrag bevat, uit de kop boven een tabel."""

    peildatum: Optional[int] = None
    eindstand: Optional[int] = None
    bedrag: Optional[int] = None
    # Kolommen met een nummer dat geen bedrag is. Een rekeningnummer of
    # polisnummer is ook een getal en staat vlak voor het bedrag; zonder deze
    # uitsluiting wordt zo'n nummer als bedrag gelezen.
    geen_bedrag: set = field(default_factory=set)
    # Aantal kolommen in de koprij. Een totaalregel heeft er minder,
    # waardoor de indexen verschuiven en de uitsluiting niet meer klopt.
    breedte: int = 0

    @property
    def is_bruikbaar(self) -> bool:
        """Of deze kop een kolom aanwijst."""
        return any(k is not None for k in (self.peildatum, self.eindstand, self.bedrag))


def _lees_kolomkop(velden: List[str]) -> Optional[_Kolomkop]:
    """Bepaal uit een koprij welke kolom welk bedrag bevat.

    Een koprij bevat geen bedragen maar wel kolomaanduidingen. Op basis daarvan
    weten we of de eerste of de tweede bedragkolom de peildatum is.
    """
    if any(parse_bedrag(v) is not None for v in velden):
        return None  # er staan bedragen in, dus dit is een datarij

    kop = _Kolomkop()
    heeft_aanduiding = False

    for index, veld in enumerate(velden):
        if _PEILDATUM_KOP.search(veld):
            kop.peildatum = index
            heeft_aanduiding = True
        elif _EINDSTAND_KOP.search(veld):
            kop.eindstand = index
            heeft_aanduiding = True
        elif _BEDRAG_KOP.match(veld.strip()):
            kop.bedrag = index
            heeft_aanduiding = True
        elif _NUMMERKOLOM.search(veld):
            kop.geen_bedrag.add(index)
            heeft_aanduiding = True
        elif _KOP_WOORDEN.search(veld):
            heeft_aanduiding = True

    # Lege velden aan het eind niet meetellen: een koprij eindigt vaak op een
    # tab, waardoor de kop een kolom breder lijkt dan de datarijen eronder.
    gevuld = [i for i, v in enumerate(velden) if v.strip()]
    kop.breedte = (gevuld[-1] + 1) if gevuld else len(velden)

    # Een nummerkolom telt alleen wanneer dezelfde koprij ook een bedragkolom
    # aanwijst. Een losse regel als "Bankrekeningnr." is een sublabel en geen
    # koprij die op de bedragkolommen is uitgelijnd; die als uitsluiting
    # gebruiken sloot juist de peildatumkolom uit.
    if kop.geen_bedrag and not any(
        k is not None for k in (kop.peildatum, kop.eindstand, kop.bedrag)
    ):
        kop.geen_bedrag = set()
        return None

    return kop if heeft_aanduiding else None


def _voeg_koppen_samen(
    bestaand: Optional[_Kolomkop], nieuw: _Kolomkop
) -> _Kolomkop:
    """Vul een bestaande kolomkop aan met een tweede koprij.

    Wat de nieuwe rij niet zegt blijft staan uit de vorige, zodat een tweede
    koprij de kolomindeling aanvult in plaats van uitwist.
    """
    if bestaand is None:
        return nieuw
    return _Kolomkop(
        peildatum=nieuw.peildatum if nieuw.peildatum is not None else bestaand.peildatum,
        eindstand=nieuw.eindstand if nieuw.eindstand is not None else bestaand.eindstand,
        bedrag=nieuw.bedrag if nieuw.bedrag is not None else bestaand.bedrag,
        geen_bedrag=bestaand.geen_bedrag | nieuw.geen_bedrag,
    )


def _bedragen_uit_rij(
    velden: List[str], kop: Optional[_Kolomkop]
) -> Tuple[Optional[float], Optional[float]]:
    """Haal het te gebruiken bedrag en de eventuele eindstand uit een rij.

    Returns:
        (bedrag voor de aangifte, eindstand of None)

    De kolomkop bepaalt de volgorde en niet het vaste kolomnummer. Dat is nodig
    omdat een totaalregel minder kolommen heeft dan de datarijen erboven: waar
    een datarij "naam, rekeningnummer, beginstand, eindstand" heeft, staat op de
    totaalregel alleen "omschrijving, beginstand, eindstand". Op een vast
    kolomnummer las die totaalregel de eindstand, en dat is precies de fout die
    deze functie moet voorkomen.
    """
    # De uitsluiting geldt alleen wanneer de rij even breed is als de koprij.
    # Bij een smallere totaalregel zijn de kolommen verschoven en zou de
    # uitsluiting het verkeerde veld raken.
    negeer: set = set()
    if kop and kop.geen_bedrag and len(velden) >= kop.breedte:
        negeer = kop.geen_bedrag
    bedragen = [
        b for i, v in enumerate(velden)
        if i not in negeer and (b := parse_bedrag(v)) is not None
    ]
    if not bedragen:
        return None, None

    if kop and kop.is_bruikbaar:
        heeft_beide = kop.peildatum is not None and kop.eindstand is not None

        if heeft_beide and kop.peildatum < kop.eindstand and len(bedragen) >= 2:
            # Beginstand staat links van de eindstand.
            return bedragen[0], bedragen[-1]

        if heeft_beide and kop.eindstand < kop.peildatum and len(bedragen) >= 2:
            return bedragen[-1], bedragen[0]

        if kop.bedrag is not None:
            # Een enkele bedragkolom, rechts van eventuele nummers. Het laatste
            # getal is het bedrag; een rekeningnummer staat ervoor.
            return bedragen[-1], None

        if kop.peildatum is not None:
            return bedragen[0], bedragen[-1] if len(bedragen) >= 2 else None

    if len(bedragen) >= 2:
        # Geen bruikbare kop. Twee bedragen naast elkaar zijn doorgaans begin en
        # eind; de beginstand is voor box 3 de juiste. Dat is een aanname, dus
        # de eindstand gaat mee zodat een melding beide kan tonen.
        return bedragen[0], bedragen[-1]

    return bedragen[-1], None


def _is_sectiekop(regel: str) -> bool:
    """Of een regel een sectiekop is: tekst zonder tab en zonder bedrag."""
    schoon = regel.strip()
    if not schoon or "\t" in regel:
        return False
    if parse_bedrag(schoon) is not None:
        return False
    # Volzinnen zijn proza en geen kop.
    return len(schoon) < 90 and not schoon.endswith(".")


def lees_aangifte_tekst(tekst: str, bestandsnaam: str = "") -> Aangifte:
    """Lees een aangifterapport uit platte tekst met tabs.

    Werkt voor de tekst uit een Word- of RTF-bestand. Deterministisch: geen
    model, dus geen leesfout aan de aangiftekant.

    Args:
        tekst: De inhoud van het rapport, tabs behouden.
        bestandsnaam: Voor de administratie.

    Returns:
        Aangifte met de gelezen regels.
    """
    aangifte = Aangifte(bestandsnaam=bestandsnaam, is_modelgelezen=False)
    sectie = ""
    kop: Optional[_Kolomkop] = None

    for ruwe_regel in tekst.splitlines():
        if not ruwe_regel.strip():
            continue

        if aangifte.aangiftejaar is None:
            jaar = re.search(
                r"(?:aangifte|belasting|boek)jaar\D{0,12}(20\d{2})",
                ruwe_regel, re.IGNORECASE,
            )
            if not jaar:
                jaar = re.search(r"inkomstenbelasting\s+(20\d{2})", ruwe_regel, re.IGNORECASE)
            if jaar:
                aangifte.aangiftejaar = int(jaar.group(1))

        if "\t" not in ruwe_regel:
            if _is_sectiekop(ruwe_regel):
                sectie = ruwe_regel.strip()
                kop = None  # een nieuwe sectie begint zonder kolomkop
            continue

        velden = [v.strip() for v in ruwe_regel.split("\t")]

        nieuwe_kop = _lees_kolomkop(velden)
        if nieuwe_kop is not None:
            # Samenvoegen en niet vervangen. Een tabel heeft soms twee koprijen:
            # eerst "01-01-2024 / 31-12-2024" en daaronder "Bankrekeningnr.".
            # Vervangen wiste daarmee de kennis over welke kolom de peildatum is.
            kop = _voeg_koppen_samen(kop, nieuwe_kop)
            continue

        label = velden[0].strip(" .:|")
        if len(label) < 3 or _NEGEER_LABEL.match(label):
            continue

        bedrag, eindstand = _bedragen_uit_rij(velden, kop)
        if bedrag is None:
            aangifte.niet_herkende_regels.append(ruwe_regel.strip())
            continue

        aangifte.regels.append(AangifteRegel(
            label=label,
            bedrag=bedrag,
            sectie=sectie,
            eindstand=eindstand,
            ruwe_regel=ruwe_regel.strip(),
        ))

    logger.info(
        "Aangifterapport %s gelezen: %d regels, aangiftejaar %s",
        bestandsnaam or "zonder naam", len(aangifte.regels), aangifte.aangiftejaar,
    )
    return aangifte


def lees_aangifte_docx(pad: str | Path) -> Aangifte:
    """Lees het aangifterapport uit een Word-bestand, zonder model.

    Zet de tabellen om naar tabgescheiden regels en gebruikt daarna dezelfde
    verwerking als een RTF, zodat de kolomkopdetectie voor beide geldt.

    Raises:
        ImportError: Wanneer python-docx niet is geinstalleerd.
        ValueError: Wanneer het bestand niet te openen is.
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise ImportError(
            "python-docx is nodig om een Word-rapport te lezen. "
            "Voeg python-docx toe aan requirements.txt."
        ) from exc

    pad = Path(pad)
    try:
        document = Document(str(pad))
    except Exception as exc:
        raise ValueError(f"Het Word-bestand is niet te openen: {exc}") from exc

    regels: List[str] = []
    # Alleen directe kinderen: iter() geeft ook de alinea's binnen
    # tabelcellen terug, waardoor elke cel er los nog een keer bij komt.
    for onderdeel in document.element.body:
        label = onderdeel.tag.split("}")[-1]
        if label == "p":
            tekst = "".join(onderdeel.itertext()).strip()
            if tekst:
                regels.append(tekst)
        elif label == "tbl":
            for rij in onderdeel.iter():
                if rij.tag.split("}")[-1] != "tr":
                    continue
                cellen = [
                    " ".join("".join(cel.itertext()).split())
                    for cel in rij.iter()
                    if cel.tag.split("}")[-1] == "tc"
                ]
                if cellen:
                    regels.append("\t".join(cellen))

    return lees_aangifte_tekst("\n".join(regels), bestandsnaam=pad.name)


def lees_aangifte_rtf(pad: str | Path) -> Aangifte:
    """Lees het aangifterapport uit een RTF-bestand, zonder model.

    Raises:
        ImportError: Wanneer striprtf niet is geinstalleerd.
        ValueError: Wanneer het bestand niet te lezen is.
    """
    try:
        from striprtf.striprtf import rtf_to_text
    except ImportError as exc:
        raise ImportError(
            "striprtf is nodig om een RTF-rapport te lezen. "
            "Voeg striprtf toe aan requirements.txt."
        ) from exc

    pad = Path(pad)
    try:
        # RTF is doorgaans latin-1; fouten negeren zodat een enkel afwijkend
        # teken niet het hele rapport onleesbaar maakt.
        ruw = pad.read_text(encoding="latin-1", errors="ignore")
    except OSError as exc:
        raise ValueError(f"Het RTF-bestand is niet te lezen: {exc}") from exc

    return lees_aangifte_tekst(rtf_to_text(ruw, errors="ignore"), bestandsnaam=pad.name)


def lees_aangifte(pad: str | Path) -> Aangifte:
    """Lees een aangifterapport, op basis van de bestandsextensie.

    Raises:
        ValueError: Bij een niet-ondersteunde extensie.
    """
    pad = Path(pad)
    extensie = pad.suffix.lower()

    if extensie == ".docx":
        return lees_aangifte_docx(pad)
    if extensie == ".rtf":
        return lees_aangifte_rtf(pad)
    raise ValueError(
        f"Bestandstype {extensie} wordt niet deterministisch gelezen. "
        "Exporteer het rapport als Word of RTF; bij een PDF is een "
        "modelaanroep nodig en ontstaat er leesonzekerheid aan de aangiftekant."
    )


def koppel_aan_posten(aangifte: Aangifte) -> Tuple[Dict[str, float], List[Tuple[str, float]]]:
    """Koppel de gelezen regels aan de bekende aangifteposten.

    Returns:
        (bedragen per postsleutel, niet te koppelen regels met hun bedrag)

        Niet te koppelen regels worden apart teruggegeven en niet weggegooid.
        Een regel die de tool niet kent zou anders ongemerkt buiten de controle
        vallen, en dat is precies de fout die deze tool moet vinden.
    """
    from .omissions import map_aangifte_labels

    eindstanden = {
        regel.label: regel.eindstand
        for regel in aangifte.regels
        if regel.eindstand is not None
    }
    return map_aangifte_labels(aangifte.als_labels(), eindstanden)

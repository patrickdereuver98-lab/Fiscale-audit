"""
FiscAudit AI - Aangifterapport uitlezen

De aangiftekant van de controle. Bij een Word-bestand gebeurt dit volledig
deterministisch: een docx is gestructureerde XML, dus de bedragen komen er
zonder model uit. Dan zit er aan de aangiftekant geen leesfout, en blijft de
vergelijking met de brondocumenten een harde check.

Bij een PDF kan dat niet en is een modelaanroep nodig. Die weg bestaat, maar de
uitkomst wordt gemarkeerd als modelgelezen, zodat een verschil niet ten onrechte
als fout van de adviseur wordt gepresenteerd terwijl het een leesfout kan zijn.

WAT DEZE MODULE NIET DOET
Er wordt niet geraden naar de precieze indeling van het AFAS-rapport. De
patronen hieronder zijn algemeen: een omschrijving met een bedrag erachter, in
een tabelcel of op een tekstregel. Wat er gevonden wordt gaat langs posten.py en
alles wat niet te koppelen is komt apart terug, zodat de reviewer het ziet en
kan aanvullen. Zodra er een voorbeeldrapport is, kan de herkenning strakker.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# Nederlandse bedragnotatie: 1.234,56 of 1234,56 of 1.234 of 52000
# Een los jaartal (2024) is geen bedrag; die worden er hieronder uitgefilterd.
_BEDRAG = re.compile(
    r"(?<![\d,.])"                       # niet midden in een ander getal
    r"(?:€\s*)?"                         # eventueel een euroteken
    r"(-?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"  # met duizendpunten
    r"|-?\d+,\d{1,2}"                    # of met decimaalkomma
    r"|-?\d{4,})"                        # of vier cijfers of meer zonder scheiding
    r"\s*(-)?"                           # bedrag met minteken erachter
    r"(?![\d,.])"
)

# Regels die nooit een aangiftepost zijn.
_NEGEER = re.compile(
    r"^(pagina|blad|datum|d\.d\.|kenmerk|dossier|bsn|burgerservicenummer"
    r"|aangiftejaar|belastingjaar|opgesteld|versie|totaal generaal)\b",
    re.IGNORECASE,
)


@dataclass
class AangifteRegel:
    """Eén regel uit het aangifterapport."""

    label: str
    bedrag: float
    is_modelgelezen: bool = False
    ruwe_regel: str = ""

    @property
    def is_betrouwbaar(self) -> bool:
        """Of het bedrag zonder leesonzekerheid is vastgesteld."""
        return not self.is_modelgelezen


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

        Regels met hetzelfde label worden opgeteld, bijvoorbeeld twee
        werkgevers onder dezelfde omschrijving.
        """
        per_label: Dict[str, float] = {}
        for regel in self.regels:
            per_label[regel.label] = per_label.get(regel.label, 0.0) + regel.bedrag
        return per_label

    @property
    def aantal_regels(self) -> int:
        """Aantal gelezen regels."""
        return len(self.regels)


def _parse_bedrag(tekst: str) -> Optional[float]:
    """Zet een Nederlands genoteerd bedrag om naar een getal.

    Nederlandse documenten gebruiken de punt als duizendscheiding en de komma
    als decimaalteken, omgekeerd aan het Engels. "250.000,00" is tweehonderd
    vijftigduizend en niet tweehonderdvijftig.
    """
    treffer = _BEDRAG.search(tekst)
    if not treffer:
        return None

    ruw, minteken_achter = treffer.group(1), treffer.group(2)
    genormaliseerd = ruw.replace(".", "").replace(",", ".")

    try:
        waarde = float(genormaliseerd)
    except ValueError:
        return None

    # "1.000,00-" betekent min duizend; het minteken staat achter het bedrag.
    if minteken_achter:
        waarde = -abs(waarde)

    return waarde


def _lijkt_op_jaartal(waarde: float, ruwe_regel: str) -> bool:
    """Of dit getal vermoedelijk een jaartal is en geen bedrag.

    Een kaal viercijferig getal tussen 1990 en 2100 op een regel die om een
    jaar vraagt, is geen bedrag. Zonder deze filter komt "Aangiftejaar 2024"
    als een post van 2.024 euro binnen.
    """
    if not (1990 <= waarde <= 2100) or waarde != int(waarde):
        return False
    return bool(re.search(r"jaar|periode|boekjaar|d\.d\.|datum", ruwe_regel, re.IGNORECASE))


def _splits_label_en_bedrag(tekst: str) -> Optional[Tuple[str, float]]:
    """Haal een omschrijving met bedrag uit een tekstregel."""
    schoon = " ".join(tekst.split())
    if len(schoon) < 4 or _NEGEER.match(schoon):
        return None

    treffer = _BEDRAG.search(schoon)
    if not treffer:
        return None

    bedrag = _parse_bedrag(schoon)
    if bedrag is None or _lijkt_op_jaartal(bedrag, schoon):
        return None

    label = schoon[:treffer.start()].strip(" .:\t|€-")
    if len(label) < 3:
        return None

    return label, bedrag


def lees_aangifte_docx(pad: str | Path) -> Aangifte:
    """Lees het aangifterapport uit een Word-bestand, zonder model.

    Kijkt zowel in de tabellen als in de alinea's, omdat AFAS-rapportages
    doorgaans tabellen gebruiken maar dat niet gegarandeerd is.

    Args:
        pad: Pad naar het .docx-bestand.

    Returns:
        Aangifte met de gelezen regels. `is_modelgelezen` staat op False: deze
        weg kent geen leesonzekerheid.

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

    aangifte = Aangifte(bestandsnaam=pad.name, is_modelgelezen=False)

    # Tabellen: omschrijving in de ene cel, bedrag in een andere.
    for tabel in document.tables:
        for rij in tabel.rows:
            cellen = [" ".join(cel.text.split()) for cel in rij.cells]
            cellen = [c for c in cellen if c]
            if len(cellen) < 2:
                continue

            label = cellen[0].strip(" .:|")
            if len(label) < 3 or _NEGEER.match(label):
                continue

            # Neem de laatste cel met een bedrag erin; in rapportages staat het
            # bedrag rechts en kunnen er kolommen met tekst tussen zitten.
            for cel in reversed(cellen[1:]):
                bedrag = _parse_bedrag(cel)
                if bedrag is not None and not _lijkt_op_jaartal(bedrag, label):
                    aangifte.regels.append(AangifteRegel(
                        label=label, bedrag=bedrag, ruwe_regel=" | ".join(cellen),
                    ))
                    break

    # Alinea's: omschrijving en bedrag op dezelfde regel.
    for alinea in document.paragraphs:
        tekst = alinea.text
        if not tekst.strip():
            continue

        jaar = re.search(r"(?:aangifte|belasting|boek)jaar\D{0,4}(20\d{2})", tekst, re.IGNORECASE)
        if jaar and aangifte.aangiftejaar is None:
            aangifte.aangiftejaar = int(jaar.group(1))

        uitkomst = _splits_label_en_bedrag(tekst)
        if uitkomst:
            label, bedrag = uitkomst
            aangifte.regels.append(AangifteRegel(
                label=label, bedrag=bedrag, ruwe_regel=tekst.strip(),
            ))

    logger.info(
        "Aangifterapport %s gelezen: %d regels, aangiftejaar %s",
        pad.name, len(aangifte.regels), aangifte.aangiftejaar,
    )
    return aangifte


def koppel_aan_posten(aangifte: Aangifte) -> Tuple[Dict[str, float], List[Tuple[str, float]]]:
    """Koppel de gelezen regels aan de bekende aangifteposten.

    Returns:
        (bedragen per postsleutel, niet te koppelen regels met hun bedrag)

        Niet te koppelen regels worden apart teruggegeven en niet weggegooid.
        Een regel die de tool niet kent zou anders ongemerkt buiten de controle
        vallen, en dat is precies de fout die deze tool moet vinden.
    """
    from .omissions import map_aangifte_labels

    return map_aangifte_labels(aangifte.als_labels())

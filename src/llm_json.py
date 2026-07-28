"""
FiscAudit AI - JSON uit een modelantwoord halen

Taalmodellen leveren regelmatig geldige JSON met wat eromheen: een codeblok,
een inleidende zin, of een afsluitende opmerking. Deze module haalt het object
eruit.

Er stonden hiervoor twee implementaties in het project, met verschillende
degelijkheid: extractor.py had drie strategieen, advisor.py knipte alleen
backticks van voor en achter. Daardoor viel de adviseur om op antwoorden die
de documentlezer wel aankon. Nu gebruiken beide dit.
"""

import json
import logging
import re
from typing import Any, Dict


logger = logging.getLogger(__name__)


class JsonExtractionError(ValueError):
    """Er zat geen bruikbaar JSON-object in het antwoord."""


_CODEBLOK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str, *, context: str = "modelantwoord") -> Dict[str, Any]:
    """Haal het eerste JSON-object uit een tekst.

    Probeert in volgorde:
      1. de hele tekst als JSON
      2. de inhoud van een markdown-codeblok
      3. het eerste gebalanceerde accolade-blok in de tekst

    Args:
        text: Het ruwe antwoord van het model.
        context: Naam voor de logregel en de foutmelding.

    Returns:
        Het JSON-object als dict.

    Raises:
        JsonExtractionError: Als geen van de strategieen een object oplevert.
    """
    if not text or not text.strip():
        raise JsonExtractionError(f"Leeg {context}")

    kandidaten = [text.strip()]

    for blok in _CODEBLOK.findall(text):
        if blok.strip():
            kandidaten.append(blok.strip())

    gebalanceerd = _eerste_gebalanceerde_object(text)
    if gebalanceerd:
        kandidaten.append(gebalanceerd)

    for poging, kandidaat in enumerate(kandidaten, start=1):
        try:
            geparsed = json.loads(kandidaat)
        except json.JSONDecodeError:
            continue

        if isinstance(geparsed, dict):
            if poging > 1:
                logger.debug("JSON uit %s gehaald via strategie %d", context, poging)
            return geparsed

        logger.debug("Strategie %d gaf %s in plaats van een object",
                     poging, type(geparsed).__name__)

    raise JsonExtractionError(
        f"Geen geldig JSON-object in {context}. Eerste 200 tekens: {text[:200]!r}"
    )


def _eerste_gebalanceerde_object(text: str) -> str:
    """Vind het eerste gebalanceerde blok tussen accolades.

    Telt accolades in plaats van een reguliere expressie te gebruiken, zodat
    geneste objecten heel blijven. Accolades binnen een string worden
    overgeslagen, inclusief ontsnapte aanhalingstekens.
    """
    start = text.find("{")
    if start == -1:
        return ""

    diepte = 0
    in_string = False
    ontsnapt = False

    for positie in range(start, len(text)):
        teken = text[positie]

        if ontsnapt:
            ontsnapt = False
            continue

        if teken == "\\":
            ontsnapt = True
            continue

        if teken == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if teken == "{":
            diepte += 1
        elif teken == "}":
            diepte -= 1
            if diepte == 0:
                return text[start:positie + 1]

    return ""

"""
FiscAudit AI - Kernwaarden nakijken

Vult de nakijkfunctie die fiscale_kern.maak_voorstellen verwacht. Zoekt per
waarde op wat er voor het betreffende belastingjaar geldt en levert een
voorstel met bron.

WAT DEZE MODULE NIET DOET
Niets doorvoeren. De uitkomst is een voorstel dat de adviseur per stuk
goedkeurt, en een voorstel zonder verwijzing naar een bron wordt door
pas_voorstellen_toe geweigerd. Reden: een model dat de kennisbank vult en daarna
uit die kennisbank leest is een gesloten kring zonder externe toets, waarin een
fout zichzelf bevestigt.

BEPERKING DIE JE MOET WETEN
De aanroep hieronder is niet tegen de echte API getest; in de omgeving waarin
deze code is geschreven zijn belastingdienst.nl en de Gemini-endpoint niet
bereikbaar. De verwerking van het antwoord is wel getest, met een nagebootst
model. Loop het eerste voorstel per waarde dus extra na, en let vooral op of de
bron werkelijk het jaar betreft dat je hebt opgevraagd.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

from .fiscale_kern import Kernwaarde
from .llm_json import extract_json_object, JsonExtractionError


logger = logging.getLogger(__name__)


SYSTEEM_PROMPT = """Je zoekt een Nederlands fiscaal getal op voor een specifiek
belastingjaar, ten behoeve van een controletool voor de inkomstenbelasting.

REGELS
1. Het jaar telt. Een tarief van 2023 in een aangifte 2024 is een fout, en die
   is aan de uitkomst niet te zien. Twijfel je over het jaar, geef dan null.
2. Geef alleen wat je met een bron kunt onderbouwen. Kun je geen verwijzing
   geven, geef dan null voor de waarde. Een getal zonder bron is voor deze tool
   waardeloos, want het wordt dan alsnog geweigerd.
3. Verzin geen verwijzing. Een plausibel uitziende maar onjuiste bron is
   schadelijker dan geen bron, omdat die het getal geloofwaardiger maakt dan het is.
4. Bij een schijventabel geef je de volledige tabel, niet een enkel getal.
5. Rond niet af en herformuleer niet: geef het bedrag of percentage zoals het
   in de regeling staat.

UITVOER
Uitsluitend een geldig JSON-object, zonder codeblok en zonder begeleidende tekst:
{
  "waarde": <getal, of een lijst bij een tabel, of null>,
  "bron_naam": "korte aanduiding van de bron",
  "bron_url": "volledige verwijzing, of leeg als je die niet hebt",
  "toelichting": "wat dit getal is en waarvoor het geldt",
  "zekerheid": "hoog" | "middel" | "laag"
}

Zet zekerheid op laag wanneer je twijfelt of het getal voor het gevraagde jaar
geldt. Dat wordt aan de adviseur getoond."""


def maak_gemini_nakijker(
    api_key: str,
    model_naam: str = "gemini-1.5-pro",
    gebruik_zoeken: bool = True,
) -> Callable[[Kernwaarde], Dict[str, Any]]:
    """Bouw een nakijkfunctie die Gemini gebruikt.

    Args:
        api_key: Google API-sleutel.
        model_naam: Modelnaam.
        gebruik_zoeken: Of het model mag zoeken. Zonder zoeken komt het getal
            uit het geheugen van het model en is het per definitie mogelijk
            verouderd; dan wordt de zekerheid verlaagd.

    Returns:
        Een functie die één Kernwaarde nakijkt en een voorstel teruggeeft in de
        vorm die fiscale_kern.maak_voorstellen verwacht.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)

    hulpmiddelen = "google_search_retrieval" if gebruik_zoeken else None
    try:
        model = genai.GenerativeModel(
            model_naam,
            system_instruction=SYSTEEM_PROMPT,
            tools=hulpmiddelen,
        )
    except TypeError:
        # Oudere versies van de bibliotheek kennen tools of system_instruction
        # niet. Dan zonder, met een lagere zekerheid als gevolg.
        logger.warning(
            "Model %s aangemaakt zonder zoekfunctie; de waarden komen dan uit "
            "het geheugen van het model en kunnen verouderd zijn",
            model_naam,
        )
        model = genai.GenerativeModel(model_naam)

    def kijk_na(kern: Kernwaarde) -> Dict[str, Any]:
        """Kijk één kernwaarde na en lever een voorstel.

        Raises:
            RuntimeError: Wanneer de aanroep of het antwoord onbruikbaar is.
                maak_voorstellen vangt dat en markeert het voorstel als mislukt.
        """
        vraag = "\n".join([
            f"Belastingjaar: {kern.belastingjaar}",
            f"Gevraagd getal: {kern.naam}",
            f"Eenheid: {kern.eenheid}",
            f"Waarvoor het dient: {kern.toelichting}",
            "",
            "Geef uitsluitend het JSON-object terug.",
        ])

        try:
            antwoord = model.generate_content(vraag)
            ruw = antwoord.text
        except Exception as exc:
            raise RuntimeError(f"aanroep mislukt: {exc}") from exc

        try:
            gegevens = extract_json_object(
                ruw, context=f"nakijken van {kern.sleutel}"
            )
        except JsonExtractionError as exc:
            raise RuntimeError(f"antwoord was geen JSON: {exc}") from exc

        return _normaliseer(gegevens, kern, gebruik_zoeken)

    return kijk_na


def _normaliseer(
    gegevens: Dict[str, Any],
    kern: Kernwaarde,
    kon_zoeken: bool,
) -> Dict[str, Any]:
    """Zet het antwoord om naar de vorm die maak_voorstellen verwacht.

    Laat de waarde op None staan wanneer de zekerheid laag is of wanneer er geen
    bron is. Zo komt zo'n voorstel niet als afwijkend in beeld en kan het niet
    per ongeluk worden goedgekeurd.
    """
    waarde = gegevens.get("waarde")
    bron_url = str(gegevens.get("bron_url", "")).strip()
    zekerheid = str(gegevens.get("zekerheid", "laag")).lower()
    toelichting = str(gegevens.get("toelichting", "")).strip()

    if not kon_zoeken:
        zekerheid = "laag"
        toelichting += (
            " Let op: dit getal komt uit het geheugen van het model en is niet "
            "bij een bron nagekeken."
        )

    if zekerheid == "laag" or not bron_url:
        reden = "geen bron opgegeven" if not bron_url else "de zekerheid is laag"
        logger.info(
            "Voorstel voor %s (%d) wordt leeg gelaten: %s",
            kern.sleutel, kern.belastingjaar, reden,
        )
        return {
            "waarde": None,
            "bron_naam": str(gegevens.get("bron_naam", "")).strip(),
            "bron_url": bron_url,
            "toelichting": (
                f"Niet overgenomen: {reden}. "
                f"{toelichting}"
            ).strip(),
        }

    if kern.eenheid != "tabel" and isinstance(waarde, (list, dict)):
        return {
            "waarde": None,
            "bron_naam": "",
            "bron_url": bron_url,
            "toelichting": (
                f"Niet overgenomen: er kwam een tabel terug terwijl "
                f"{kern.eenheid} werd verwacht. {toelichting}"
            ).strip(),
        }

    if kern.eenheid == "tabel" and not isinstance(waarde, (list, dict)):
        return {
            "waarde": None,
            "bron_naam": "",
            "bron_url": bron_url,
            "toelichting": (
                f"Niet overgenomen: er kwam een enkel getal terug terwijl een "
                f"schijventabel werd verwacht. {toelichting}"
            ).strip(),
        }

    return {
        "waarde": waarde,
        "bron_naam": str(gegevens.get("bron_naam", "")).strip(),
        "bron_url": bron_url,
        "toelichting": toelichting,
    }

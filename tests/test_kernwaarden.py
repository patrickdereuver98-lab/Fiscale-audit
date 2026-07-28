"""Tests voor de fiscale kernwaarden.

De belangrijkste eigenschap die hier wordt vastgelegd: een waarde die niet is
nagekeken komt nooit als gewoon getal uit de tool.
"""

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fiscale_kern import (
    Kernwaarde, Kernwaarden, Voorstel, KernwaardeOntbreekt,
    lege_kernwaarden, laad_kernwaarden, laad_uit_json, bewaar_in_json,
    maak_voorstellen, pas_voorstellen_toe, BENODIGDE_WAARDEN,
)

geslaagd, gefaald = [], []


def check(naam, voorwaarde, toelichting=""):
    (geslaagd if voorwaarde else gefaald).append(naam)
    print(f"  {'PASS' if voorwaarde else 'FAIL'}  {naam}")
    if toelichting and not voorwaarde:
        print(f"        {toelichting}")


print("=" * 72)
print("Een niet-nagekeken waarde wordt niet gebruikt")
print("=" * 72)
leeg = lege_kernwaarden(2024)
check("alle benodigde waarden staan klaar", len(leeg.waarden) == len(BENODIGDE_WAARDEN))
check("geen enkele is bruikbaar", leeg.aantal_bruikbaar == 0)
check("waarde() geeft None", leeg.waarde("box3_heffingvrij_vermogen") is None)
check("een onbekende sleutel geeft ook None", leeg.waarde("bestaat_niet") is None)
check("de verzameling is niet volledig", leeg.is_volledig is False)

try:
    leeg.vereist("box3_heffingvrij_vermogen")
    check("vereist() werpt een fout", False, "er kwam geen fout")
except KernwaardeOntbreekt as exc:
    check("vereist() werpt een fout", True)
    check("de fout vertelt wat te doen", "Data Monitor" in str(exc))
    print(f"        {exc}")

print()
print("=" * 72)
print("Een waarde zonder verificatie is niet bruikbaar")
print("=" * 72)
zonder = Kernwaarde(sleutel="test", naam="Test", belastingjaar=2024, waarde=57000.0)
check("waarde aanwezig, verificatie niet", zonder.is_bruikbaar is False)
check("de status zegt het ook", zonder.status == "Niet geverifieerd")

met = Kernwaarde(sleutel="test", naam="Test", belastingjaar=2024, waarde=57000.0,
                 laatst_geverifieerd="2026-01-15", geverifieerd_door="P. de Reuver")
check("met verificatie wel bruikbaar", met.is_bruikbaar is True)
check("de status is geverifieerd", met.status == "Geverifieerd")
check("de leeftijd wordt berekend", isinstance(met.dagen_oud, int))

verzameling = Kernwaarden(belastingjaar=2024, waarden={"test": met})
check("waarde() geeft nu het getal", verzameling.waarde("test") == 57000.0)
check("vereist() werkt nu ook", verzameling.vereist("test") == 57000.0)

print()
print("=" * 72)
print("Verversen levert voorstellen, geen wijzigingen")
print("=" * 72)


def nakijker(kern):
    """Nagebootste nakijker: geeft voor twee sleutels iets terug, faalt bij een."""
    if kern.sleutel == "box3_heffingvrij_vermogen":
        return {"waarde": 57684.0, "bron_naam": "Belastingdienst",
                "bron_url": "https://example.invalid/box3", "toelichting": "Bedrag 2024"}
    if kern.sleutel == "zelfstandigenaftrek":
        return {"waarde": 3750.0, "bron_naam": "Belastingdienst",
                "bron_url": "https://example.invalid/zelfstandigenaftrek"}
    if kern.sleutel == "urencriterium":
        raise RuntimeError("bron niet bereikbaar")
    return {"waarde": None}


kern = lege_kernwaarden(2024)
voorstellen = maak_voorstellen(kern, nakijker)

check("er is een voorstel per waarde", len(voorstellen) == len(BENODIGDE_WAARDEN))
check("de kernwaarden zijn nog niet gewijzigd", kern.aantal_bruikbaar == 0,
      "verversen mag niets doorvoeren")

afwijkend = [v for v in voorstellen if v.is_afwijkend]
mislukt = [v for v in voorstellen if v.is_mislukt]
check("twee voorstellen wijken af", len(afwijkend) == 2, f"kreeg {len(afwijkend)}")
check("een voorstel is mislukt", len(mislukt) == 1)
check("de mislukking noemt de reden", "niet bereikbaar" in mislukt[0].fout)

print()
print("=" * 72)
print("Goedkeuren vereist een naam")
print("=" * 72)
try:
    pas_voorstellen_toe(kern, voorstellen, ["box3_heffingvrij_vermogen"],
                        geverifieerd_door="")
    check("zonder naam wordt geweigerd", False, "er kwam geen fout")
except ValueError as exc:
    check("zonder naam wordt geweigerd", True)
    check("de fout legt uit waarom", "herleidbaar" in str(exc))

print()
print("=" * 72)
print("Alleen wat is goedgekeurd wordt doorgevoerd")
print("=" * 72)
bijgewerkt = pas_voorstellen_toe(
    kern, voorstellen,
    goedgekeurde_sleutels=["box3_heffingvrij_vermogen"],
    geverifieerd_door="P. de Reuver",
    op_datum=date(2026, 7, 28),
)
check("een waarde bijgewerkt", bijgewerkt == ["box3_heffingvrij_vermogen"])
check("die waarde is nu bruikbaar",
      kern.waarde("box3_heffingvrij_vermogen") == 57684.0)
check("de niet-goedgekeurde waarde blijft leeg",
      kern.waarde("zelfstandigenaftrek") is None)
check("de naam is vastgelegd",
      kern.waarden["box3_heffingvrij_vermogen"].geverifieerd_door == "P. de Reuver")
check("de datum is vastgelegd",
      kern.waarden["box3_heffingvrij_vermogen"].laatst_geverifieerd == "2026-07-28")
check("de bron is vastgelegd",
      "example.invalid" in kern.waarden["box3_heffingvrij_vermogen"].bron_url)

print()
print("=" * 72)
print("Een voorstel zonder bron wordt niet doorgevoerd")
print("=" * 72)
zonder_bron = Voorstel(sleutel="urencriterium", naam="Urencriterium",
                       belastingjaar=2024, huidige_waarde=None, nieuwe_waarde=1225)
check("het voorstel heeft geen bron", zonder_bron.heeft_bron is False)
resultaat = pas_voorstellen_toe(kern, [zonder_bron], ["urencriterium"],
                               geverifieerd_door="P. de Reuver")
check("er wordt niets bijgewerkt", resultaat == [])
check("de waarde blijft leeg", kern.waarde("urencriterium") is None,
      "een getal zonder verwijzing rust alleen op het model")

print()
print("=" * 72)
print("Een mislukt voorstel wordt niet doorgevoerd")
print("=" * 72)
mislukt_voorstel = Voorstel(sleutel="startersaftrek", naam="Startersaftrek",
                            belastingjaar=2024, huidige_waarde=None,
                            nieuwe_waarde=2123, bron_url="https://example.invalid/x",
                            fout="bron gaf een foutmelding")
pas_voorstellen_toe(kern, [mislukt_voorstel], ["startersaftrek"],
                    geverifieerd_door="P. de Reuver")
check("de waarde blijft leeg", kern.waarde("startersaftrek") is None)

print()
print("=" * 72)
print("Opslaan en teruglezen")
print("=" * 72)
with tempfile.TemporaryDirectory() as map_pad:
    pad = Path(map_pad) / "kern.json"
    check("opslaan lukt", bewaar_in_json(kern, pad) is True)
    terug = laad_uit_json(2024, pad)
    check("teruglezen lukt", terug is not None)
    check("de bron is het bestand", terug.bron == "json")
    check("de nagekeken waarde komt terug",
          terug.waarde("box3_heffingvrij_vermogen") == 57684.0)
    check("de lege waarde blijft leeg", terug.waarde("zelfstandigenaftrek") is None)
    check("de verificatiegegevens komen terug",
          terug.waarden["box3_heffingvrij_vermogen"].geverifieerd_door == "P. de Reuver")

    # een ander jaar in hetzelfde bestand mag het eerste niet overschrijven
    ander = lege_kernwaarden(2025)
    bewaar_in_json(ander, pad)
    nog_daar = laad_uit_json(2024, pad)
    check("een ander jaar overschrijft 2024 niet",
          nog_daar.waarde("box3_heffingvrij_vermogen") == 57684.0)
    check("het andere jaar is er ook", laad_uit_json(2025, pad) is not None)
    check("een onbekend jaar geeft None", laad_uit_json(2099, pad) is None)

print()
print("=" * 72)
print("Supabase eerst, dan het bestand")
print("=" * 72)
uit_db = lege_kernwaarden(2024)
uit_db.waarden["urencriterium"].waarde = 1225
uit_db.waarden["urencriterium"].laatst_geverifieerd = "2026-01-01"

geladen = laad_kernwaarden(2024, supabase_lezer=lambda jaar: uit_db)
check("de database heeft voorrang", geladen.bron == "supabase")
check("de waarde komt uit de database", geladen.waarde("urencriterium") == 1225)


def kapotte_lezer(jaar):
    raise RuntimeError("database niet bereikbaar")


terugval = laad_kernwaarden(2024, supabase_lezer=kapotte_lezer)
check("bij een fout wordt teruggevallen", terugval.bron in ("json", "leeg"))
check("er komt altijd iets terug", len(terugval.waarden) > 0,
      "een leeg scherm verbergt wat er ontbreekt")

print()
print("=" * 72)
print("Overzicht voor de monitor")
print("=" * 72)
overzicht = kern.status_overzicht()
check("elke waarde staat in het overzicht", len(overzicht) == len(kern.waarden))
check("ontbrekende waarden staan bovenaan",
      overzicht[0]["Status"] in ("Niet vastgesteld", "Niet geverifieerd"))
check("de geverifieerde waarde staat onderaan",
      overzicht[-1]["Status"] == "Geverifieerd")
check("bedragen staan in Nederlandse notatie",
      any("57.684,00" in r["Waarde"] for r in overzicht),
      f"kreeg {[r['Waarde'] for r in overzicht]}")

print()
print("=" * 72)
print(f"RESULTAAT: {len(geslaagd)} geslaagd, {len(gefaald)} gefaald")
for f in gefaald:
    print("  gefaald:", f)
print("=" * 72)
sys.exit(1 if gefaald else 0)

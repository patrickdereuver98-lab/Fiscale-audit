"""Tests voor de ontwerptokens.

De belangrijkste hiervan controleert of .streamlit/config.toml nog overeenkomt
met src/theme.py. Streamlit leest dat bestand voordat de app draait, dus het kan
niet vanuit Python worden gezet en kan daarmee stil uit de pas gaan lopen. Deze
test faalt zodra dat gebeurt.
"""

import os
import re
import sys
import tomllib
from pathlib import Path

WORTEL = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(WORTEL))

from src.theme import (
    KLEUR, RISICO_KLEUR, RUIMTE, RADIUS, SCHADUW,
    css_variabelen, streamlit_thema, FONT_SANS, FONT_MONO,
)

geslaagd, gefaald = [], []


def check(naam, voorwaarde, toelichting=""):
    (geslaagd if voorwaarde else gefaald).append(naam)
    print(f"  {'PASS' if voorwaarde else 'FAIL'}  {naam}")
    if toelichting and not voorwaarde:
        print(f"        {toelichting}")


print("=" * 72)
print("config.toml loopt niet uit de pas met theme.py")
print("=" * 72)
with open(WORTEL / ".streamlit" / "config.toml", "rb") as bestand:
    config = tomllib.load(bestand)

uit_bestand = config.get("theme", {})
uit_code = streamlit_thema()

for sleutel, verwacht in uit_code.items():
    werkelijk = uit_bestand.get(sleutel)
    check(
        f"config.toml {sleutel} = {verwacht}",
        werkelijk == verwacht,
        f"config.toml zegt {werkelijk!r}; werk .streamlit/config.toml bij of "
        f"pas src/theme.py aan",
    )

print()
print("=" * 72)
print("Elke kleur komt maar op een plek voor")
print("=" * 72)
css = (WORTEL / "assets" / "style.css").read_text(encoding="utf-8")

check("style.css bevat geen eigen :root-blok", ":root {" not in css,
      "de tokens horen uit theme.py te komen")

# Statuskleuren mogen niet als losse hex in het stijlblad staan; dan wijzigt een
# aanpassing in theme.py de opmaak niet mee.
losse_hexen = set(re.findall(r"#[0-9A-Fa-f]{6}", css))
statuskleuren = {
    KLEUR.achtergrond, KLEUR.vlak, KLEUR.primair, KLEUR.goed,
    KLEUR.fout, KLEUR.let_op, KLEUR.tekst,
}
dubbel = losse_hexen & {k.upper() for k in statuskleuren} | losse_hexen & statuskleuren
check("geen tokenkleuren hardgecodeerd in style.css", not dubbel,
      f"gevonden: {dubbel}")

for module in ("ui_components.py", "layout.py"):
    inhoud = (WORTEL / "src" / module).read_text(encoding="utf-8")
    hexen = re.findall(r"#[0-9A-Fa-f]{6}", inhoud)
    check(f"geen hardgecodeerde kleuren in {module}", not hexen,
          f"gevonden: {set(hexen)}")

print()
print("=" * 72)
print("De gegenereerde tokens zijn volledig")
print("=" * 72)
variabelen = css_variabelen()

check("het is een geldig :root-blok",
      variabelen.strip().endswith("}") and ":root {" in variabelen)

for naam in ("--dark-bg", "--primary", "--success", "--error", "--warning",
             "--high", "--text-primary", "--border", "--font-sans", "--font-mono"):
    check(f"{naam} staat erin", f"{naam}:" in variabelen)

for groep, prefix in ((RUIMTE, "--space-"), (RADIUS, "--radius-"),
                      (SCHADUW, "--shadow-")):
    ontbreekt = [n for n in groep if f"{prefix}{n}:" not in variabelen]
    check(f"alle {prefix}* staan erin", not ontbreekt, f"mist {ontbreekt}")

print()
print("=" * 72)
print("style.css gebruikt alleen bestaande variabelen")
print("=" * 72)
gebruikt = set(re.findall(r"var\((--[a-z0-9-]+)\)", css))
gedefinieerd = set(re.findall(r"(--[a-z0-9-]+):", variabelen))
onbekend = gebruikt - gedefinieerd
check("geen verwijzing naar een niet-bestaande variabele", not onbekend,
      f"style.css gebruikt {onbekend} maar theme.py definieert die niet")
print(f"        {len(gebruikt)} variabelen gebruikt, {len(gedefinieerd)} gedefinieerd")

ongebruikt = gedefinieerd - gebruikt
if ongebruikt:
    print(f"        niet gebruikt in style.css (mogelijk alleen in Python): "
          f"{sorted(ongebruikt)}")

print()
print("=" * 72)
print("Risicokleuren zijn onderscheidbaar")
print("=" * 72)
check("vier niveaus", set(RISICO_KLEUR) == {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
check("elk niveau een eigen kleur",
      len(set(RISICO_KLEUR.values())) == 4,
      f"kreeg {RISICO_KLEUR}")
check("hoog zit tussen let op en fout",
      RISICO_KLEUR["HIGH"] not in (RISICO_KLEUR["MEDIUM"], RISICO_KLEUR["CRITICAL"]))

print()
print("=" * 72)
print("rgba-omzetting")
print("=" * 72)
check("achtergrond met doorzicht",
      KLEUR.rgba(KLEUR.goed, 0.12) == "rgba(5, 150, 105, 0.12)",
      f"kreeg {KLEUR.rgba(KLEUR.goed, 0.12)}")
check("werkt ook zonder hekje",
      KLEUR.rgba("2563EB", 0.5) == "rgba(37, 99, 235, 0.5)")

print()
print("=" * 72)
print("Typografie")
print("=" * 72)
check("geen externe letter opgevraagd",
      "http" not in FONT_SANS and "http" not in FONT_MONO,
      "een externe letter geeft wachttijd en een verschuiving tijdens het laden")
check("monospace voor bedragen aanwezig", "mono" in FONT_MONO.lower())
check("tabellarische cijfers staan in het stijlblad",
      "tabular-nums" in css,
      "zonder dit staan duizenden niet onder elkaar en valt een "
      "ordegroottefout niet op")

print()
print("=" * 72)
print(f"RESULTAAT: {len(geslaagd)} geslaagd, {len(gefaald)} gefaald")
for f in gefaald:
    print("  gefaald:", f)
print("=" * 72)
sys.exit(1 if gefaald else 0)

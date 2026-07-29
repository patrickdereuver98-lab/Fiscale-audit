"""Tests voor het uitlezen van het aangifterapport.

Alle gegevens hieronder zijn verzonnen. De vorm is overgenomen van een echt
rapport, de namen en bedragen niet.

De belangrijkste controle hier is de kolomkeuze. Een rapport zet de stand per
1 januari en die per 31 december naast elkaar; box 3 gaat over 1 januari. Wie de
laatste kolom leest zit er op een gemiddeld dossier tienduizenden euro's naast,
zonder dat er een melding komt.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.aangifte_lezer import (
    lees_aangifte_tekst, koppel_aan_posten, parse_bedrag,
)

geslaagd, gefaald = [], []


def check(naam, voorwaarde, toelichting=""):
    (geslaagd if voorwaarde else gefaald).append(naam)
    print(f"  {'PASS' if voorwaarde else 'FAIL'}  {naam}")
    if toelichting and not voorwaarde:
        print(f"        {toelichting}")


# Nagebootst rapport met dezelfde indeling: tabgescheiden, hele euro's met een
# punt als duizendscheiding, kolomkoppen boven de tabellen.
RAPPORT = "\n".join([
    "Voorbeeld Belastingadviseurs B.V.",
    "Aangifte inkomstenbelasting 2024",
    "De heer A. Voorbeeld",
    "Postcode\t1234AB",
    "",
    "Opstelling van het belastbaar inkomen",
    "Belastbaar inkomen uit werk en woning (BOX 1)",
    "Winst uit onderneming\t50.000",
    "Saldo inkomsten en aftrekposten eigen woning\t-6.000",
    "Premies voor inkomensvoorzieningen\t3.000",
    "",
    "Belastbaar inkomen uit sparen en beleggen (BOX 3)",
    "Bezittingen\t40.000",
    "Af: schulden na drempel\t0",
    "",
    "Specificatie BOX 1: Inkomen uit werk en woning",
    "Fiscale winst onderneming",
    "Winst volgens jaarrekening\t62.000",
    "Belastbare winst uit onderneming\t50.000",
    "",
    "Woning Voorbeeldstraat 1, Testdorp",
    "Adres van de woning\tVoorbeeldstraat 1",
    "Percentage eigendom\t100,00",
    "Waarde van de woning (WOZ-waarde)\t400.000",
    "Eigenwoningforfait\t1.400",
    "Aftrekbaar bedrag betaalde rente",
    "Omschrijving\tBegindatum\tEinddatum\tRekeningnummer\tRente",
    "Voorbeeldbank\t\t\t9999001\t5.000",
    "Voorbeeldbank\t\t\t9999002\t2.400",
    "Aftrekbaar bedrag\t7.400",
    "Totaal aftrekposten van de eigen woning\t-7.400",
    "Eigenwoningschuld van aftrekbare geldleningen",
    "Hypotheek / Lening\tRekeningnummer\tBegin jaar\tEinde jaar\t",
    "Voorbeeldbank\t9999001\t210.000\t205.000",
    "Voorbeeldbank\t9999002\t95.000\t92.000",
    "Eigenwoningschuld van aftrekbare geldleningen\t305.000\t297.000",
    "Totaal eigenwoningschulden\t305.000\t297.000",
    "",
    "Inkomensvoorzieningen",
    "\tPolis-/rekeningnummer\tBedrag",
    "Voorbeeldverzekeraar\t00123456789\t3.000",
    "Premies arbeidsongeschiktheidsverzekeringen (geen Zorgverzekeringswet)\t3.000",
    "Totaal uitgaven voor inkomensvoorzieningen\t3.000",
    "",
    "Specificatie BOX 3: Inkomen uit sparen en beleggen",
    "Bezittingen",
    "\t\t01-01-2024\t31-12-2024",
    "Premiedepots, bank- en spaartegoeden in Nederland (excl. groene beleggingen)",
    "\t\tBankrekeningnr.",
    "Voorbeeldbank\tNL01VBLD0000000001\t15.000\t18.000",
    "Voorbeeldbank\tNL01VBLD0000000002\t25.000\t31.000",
    "Totaal premiedepots, bank- en spaartegoeden in Nederland "
    "(excl. groene beleggingen)\t40.000\t49.000",
    "",
    "Pagina 1/4",
])


print("=" * 72)
print("Bedragen in Nederlandse notatie")
print("=" * 72)
for invoer, verwacht in [
    ("97.179", 97179.0), ("-7.831", -7831.0), ("277", 277.0), ("0", 0.0),
    ("1", 1.0), ("100,00", 100.0), ("1.234,56", 1234.56), ("4.212,00-", -4212.0),
    ("€ 8.500", 8500.0),
]:
    check(f"{invoer!r} wordt {verwacht}", parse_bedrag(invoer) == verwacht,
          f"kreeg {parse_bedrag(invoer)}")

for invoer in ["9,32%", "NL01VBLD0000000001", "Ja", "01/01/2024", "1234AB", ""]:
    check(f"{invoer!r} is geen bedrag", parse_bedrag(invoer) is None,
          f"kreeg {parse_bedrag(invoer)}")

print()
print("=" * 72)
print("Het rapport wordt gelezen")
print("=" * 72)
aangifte = lees_aangifte_tekst(RAPPORT, bestandsnaam="voorbeeld.rtf")
check("aangiftejaar gevonden", aangifte.aangiftejaar == 2024,
      f"kreeg {aangifte.aangiftejaar}")
check("niet modelgelezen", aangifte.is_modelgelezen is False,
      "een rapport met tabs wordt zonder model gelezen")
check("er zijn regels gelezen", aangifte.aantal_regels > 10)

print()
print("=" * 72)
print("DE KRITIEKE CONTROLE: de peildatumkolom, niet de eindstand")
print("=" * 72)
bank = aangifte.bedrag_van("Totaal premiedepots")
check("banktegoeden komen uit de kolom van 1 januari", bank == 40000.0,
      f"kreeg {bank}; 49.000 betekent dat de eindstand is gelezen")

schuld = aangifte.bedrag_van("Totaal eigenwoningschulden")
check("de lezer geeft Begin jaar als hoofdbedrag", schuld == 305000.0,
      f"kreeg {schuld}")
schuldregel = next(r for r in aangifte.regels
                   if r.label == "Totaal eigenwoningschulden")
check("en Einde jaar als eindstand", schuldregel.eindstand == 297000.0,
      f"kreeg {schuldregel.eindstand}")

regel = next(r for r in aangifte.regels if "Totaal premiedepots" in r.label)
check("de eindstand blijft apart bewaard", regel.eindstand == 49000.0,
      f"kreeg {regel.eindstand}")

print()
print("=" * 72)
print("Een rekeningnummer wordt niet als bedrag gelezen")
print("=" * 72)
# "Voorbeeldbank \t\t\t 9999001 \t 5.000" onder de kop met kolom Rente
rente_regels = [r for r in aangifte.regels if r.label == "Voorbeeldbank"]
bedragen = {r.bedrag for r in rente_regels}
check("9999001 komt niet als bedrag terug", 9999001.0 not in bedragen,
      f"kreeg {bedragen}")
check("geen enkel bedrag boven een miljoen",
      all(abs(r.bedrag) < 1_000_000 for r in aangifte.regels),
      f"gevonden: {[r.label for r in aangifte.regels if abs(r.bedrag) >= 1_000_000]}")

print()
print("=" * 72)
print("Sectiekoppen worden bijgehouden")
print("=" * 72)
box3 = [r for r in aangifte.regels if "BOX 3" in r.sectie]
check("box 3 regels kennen hun sectie", bool(box3),
      "zonder sectie zijn labels als 'Bezittingen' niet eenduidig")
woz = next((r for r in aangifte.regels if "WOZ" in r.label), None)
check("de woningregel staat onder de woningsectie",
      woz is not None and "Woning" in woz.sectie,
      f"kreeg {woz.sectie if woz else None!r}")

print()
print("=" * 72)
print("Ruis wordt overgeslagen")
print("=" * 72)
labels = [r.label for r in aangifte.regels]
for ruis in ("Pagina 1/4", "Postcode", "Adres van de woning",
             "Percentage eigendom"):
    check(f"{ruis!r} is geen post", not any(ruis in l for l in labels))

print()
print("=" * 72)
print("Koppeling aan de posten, zonder dubbeltelling")
print("=" * 72)
per_post, onbekend = koppel_aan_posten(aangifte)

verwacht = {
    "bank_spaartegoeden": 40000.0,
    # De hypotheekjaaropgave geeft de schuld per 31 december, dus voor deze
    # post wordt tegen de eindstand vergeleken en niet tegen de peildatum.
    # Anders levert een kloppend dossier een verschil op ter grootte van de
    # aflossing over het jaar.
    "eigenwoningschuld": 297000.0,
    "hypotheekrente": 7400.0,
    "aov_premie": 3000.0,
    "winst_onderneming": 62000.0,
    "woz_eigen_woning": 400000.0,
    "eigenwoningforfait": 1400.0,
}
for sleutel, bedrag in verwacht.items():
    check(f"{sleutel} = {bedrag:,.0f}", per_post.get(sleutel) == bedrag,
          f"kreeg {per_post.get(sleutel)}")

check("de AOV-premie is niet drie keer geteld", per_post.get("aov_premie") == 3000.0,
      "het rapport noemt hem in de samenvatting, de specificatie en als totaal")
check("de schuld is niet twee keer geteld",
      per_post.get("eigenwoningschuld") == 297000.0)
check("de aftrekpost staat positief ondanks het minteken in het rapport",
      per_post.get("hypotheekrente", 0) > 0,
      "een rapport zet aftrek negatief; dat is presentatie")
check("de winst volgens jaarrekening gaat voor de belastbare winst",
      per_post.get("winst_onderneming") == 62000.0,
      "50.000 is de winst na aftrek en hoort niet met de jaarrekening aan te sluiten")

print()
print("=" * 72)
print("Onbekende labels verdwijnen niet")
print("=" * 72)
check("er zijn onbekende labels gemeld", len(onbekend) > 0,
      "een rapport bevat altijd regels die geen aangiftepost zijn")
check("ze hebben een bedrag bij zich",
      all(isinstance(b, (int, float)) for _, b in onbekend))
print(f"        {len(onbekend)} regels blijven buiten de controle")

print()
print("=" * 72)
print(f"RESULTAAT: {len(geslaagd)} geslaagd, {len(gefaald)} gefaald")
for f in gefaald:
    print("  gefaald:", f)
print("=" * 72)
sys.exit(1 if gefaald else 0)

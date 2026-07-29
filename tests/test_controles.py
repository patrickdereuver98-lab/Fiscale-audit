"""Tests voor de controles op de uitlezing.

Alle gegevens zijn verzonnen. De vorm komt overeen met een echte
hypotheekjaaropgave: twee leningdelen met een totaal dat het document zelf noemt.
"""

import os
import sys
import types

for naam in ("google", "google.generativeai", "anthropic", "supabase"):
    sys.modules.setdefault(naam, types.ModuleType(naam))
sys.modules["google.generativeai"].configure = lambda **k: None
sys.modules["google.generativeai"].GenerativeModel = lambda *a, **k: None
sys.modules["google.generativeai"].types = types.SimpleNamespace(GenerationConfig=object)
sys.modules["anthropic"].Anthropic = object
sys.modules["supabase"].create_client = lambda *a, **k: None
sys.modules["supabase"].Client = object
for mod, attr in [("supabase.lib", None), ("supabase.lib.client_options", "ClientOptions")]:
    m = types.ModuleType(mod)
    if attr:
        setattr(m, attr, object)
    sys.modules[mod] = m

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain import RiskLevel
from src.extractor import (
    ExtractedFinancialData, MortgageInfo, BankBalance, PropertyInfo,
    EmploymentIncome,
)
from src.controles import (
    crossfoot, controleer_uitlezing, vergelijk_lezingen, platte_bedragen,
    ControleSoort, CROSSFOOT_MARGE_EUR,
)

geslaagd, gefaald = [], []


def check(naam, voorwaarde, toelichting=""):
    (geslaagd if voorwaarde else gefaald).append(naam)
    print(f"  {'PASS' if voorwaarde else 'FAIL'}  {naam}")
    if toelichting and not voorwaarde:
        print(f"        {toelichting}")


print("=" * 72)
print("Cross-foot: het document controleert zijn eigen uitlezing")
print("=" * 72)
sluit = crossfoot("Twee leningdelen", [300000.0, 80000.0], 380000.0)
check("een sluitende telling slaagt", sluit.geslaagd)
check("dit geeft zekerheid en geen mening", sluit.soort.geeft_zekerheid)
check("het verschil is nul", sluit.verschil == 0.0)

mis = crossfoot("Twee leningdelen", [300000.0, 80000.0], 395000.0)
check("een niet-sluitende telling faalt", not mis.geslaagd)
check("het verschil wordt benoemd", mis.verschil == -15000.0)
check("dit is kritiek, want de aansluiting is onbetrouwbaar",
      mis.risico == RiskLevel.CRITICAL)
check("de melding zegt dat er niets te concluderen valt",
      "niet betrouwbaar" in mis.melding)
print(f"        {mis.melding[:100]}...")

print()
print("=" * 72)
print("Afronding per regel mag, een ontbrekend bedrag niet")
print("=" * 72)
check(f"tot EUR {CROSSFOOT_MARGE_EUR:.0f} afwijking is afronding",
      crossfoot("x", [100.40, 200.40], 301.0).geslaagd)
check("meer dan dat niet",
      not crossfoot("x", [100.0, 200.0], 350.0).geslaagd)

print()
print("=" * 72)
print("Zonder genoemd totaal wordt er niet gedaan alsof er is gecontroleerd")
print("=" * 72)
check("geen totaal geeft geen controle",
      crossfoot("x", [100.0, 200.0], None) is None,
      "een geslaagde controle voorwenden is erger dan niet controleren")
check("geen onderdelen geeft ook geen controle",
      crossfoot("x", [], 300.0) is None)

print()
print("=" * 72)
print("Hypotheekjaaropgave met twee leningdelen")
print("=" * 72)
goed = ExtractedFinancialData(
    extraction_confidence=0.95,
    mortgages=[
        MortgageInfo(current_balance_eur=300000.0, annual_interest_paid_eur=9000.0),
        MortgageInfo(current_balance_eur=80000.0, annual_interest_paid_eur=2400.0),
    ],
    stated_totals={
        "mortgage_debt_total": 380000.0,
        "mortgage_interest_total": 11400.0,
    },
)
rapport = controleer_uitlezing(goed)
check("beide tellingen zijn gecontroleerd", rapport.aantal_bewezen == 2,
      f"kreeg {rapport.aantal_bewezen}")
check("de uitlezing is bewezen", rapport.uitlezing_is_bewezen)
check("geen enkele controle faalt", rapport.gefaald == [])

# een verkeerd gelezen leningdeel
fout = ExtractedFinancialData(
    extraction_confidence=0.95,
    mortgages=[
        MortgageInfo(current_balance_eur=300000.0, annual_interest_paid_eur=9000.0),
        MortgageInfo(current_balance_eur=8000.0, annual_interest_paid_eur=2400.0),
    ],
    stated_totals={
        "mortgage_debt_total": 380000.0,
        "mortgage_interest_total": 11400.0,
    },
)
rapport_fout = controleer_uitlezing(fout)
check("een verkeerd gelezen bedrag wordt gevonden",
      not rapport_fout.uitlezing_is_bewezen,
      "80.000 als 8.000 gelezen moet opvallen zonder tweede model")
check("het risico is kritiek", rapport_fout.risico == RiskLevel.CRITICAL)
gefaalde = rapport_fout.gefaald[0]
print(f"        {gefaalde.melding[:110]}...")

print()
print("=" * 72)
print("Banksaldi tegen het totaal op het overzicht")
print("=" * 72)
bank = ExtractedFinancialData(
    extraction_confidence=0.94,
    bank_accounts=[
        BankBalance(account_number="NL01VBLD0000000001", bank_name="Voorbeeldbank",
                    balance_eur=15000.0),
        BankBalance(account_number="NL01VBLD0000000002", bank_name="Voorbeeldbank",
                    balance_eur=25000.0),
    ],
    stated_totals={"bank_balance_total_peildatum": 40000.0},
)
check("de saldi sluiten op het totaal",
      controleer_uitlezing(bank).uitlezing_is_bewezen)

bank_mis = ExtractedFinancialData(
    extraction_confidence=0.94,
    bank_accounts=[
        BankBalance(account_number="NL01VBLD0000000001", bank_name="Voorbeeldbank",
                    balance_eur=15000.0),
    ],
    stated_totals={"bank_balance_total_peildatum": 40000.0},
)
check("een gemiste rekening valt op",
      not controleer_uitlezing(bank_mis).uitlezing_is_bewezen,
      "dit vindt een rekening die het model over het hoofd zag")

print()
print("=" * 72)
print("Plausibiliteit: wat niet kan, kan niet")
print("=" * 72)
verwisseld = ExtractedFinancialData(
    extraction_confidence=0.9,
    # schuld en rente omgedraaid gelezen
    mortgages=[MortgageInfo(current_balance_eur=9000.0,
                            annual_interest_paid_eur=300000.0)],
)
controles = [c for c in controleer_uitlezing(verwisseld).controles
             if c.soort == ControleSoort.PLAUSIBILITEIT]
check("verwisselde schuld en rente vallen op",
      any(not c.geslaagd for c in controles))
check("de melding noemt de vermoedelijke oorzaak",
      any("verwisseld" in c.toelichting for c in controles if not c.geslaagd))

deel = ExtractedFinancialData(
    extraction_confidence=0.9,
    real_estate=[PropertyInfo(address="Voorbeeldstraat 1, Testdorp",
                              woz_value_eur=400000.0, year_valued=2024,
                              ownership_pct=50.0)],
)
eigendom = [c for c in controleer_uitlezing(deel).controles
            if "Eigendomsdeel" in c.onderwerp]
check("gedeeld eigendom wordt expliciet gemeld", bool(eigendom),
      "de volle WOZ nemen bij 50 procent is een factorfout")

vol = ExtractedFinancialData(
    extraction_confidence=0.9,
    real_estate=[PropertyInfo(address="Voorbeeldstraat 1, Testdorp",
                              woz_value_eur=400000.0, year_valued=2024,
                              ownership_pct=100.0)],
)
check("volledig eigendom geeft geen ruis",
      not [c for c in controleer_uitlezing(vol).controles
           if "Eigendomsdeel" in c.onderwerp])

print()
print("=" * 72)
print("Tweede lezing: aanwijzing en geen bewijs")
print("=" * 72)
eerste = {"saldo 000001": 15000.0, "WOZ Voorbeeldstraat": 400000.0}
tweede_gelijk = {"saldo 000001": 15000.0, "WOZ Voorbeeldstraat": 400000.0}
uitkomst = vergelijk_lezingen(eerste, tweede_gelijk)
check("gelijke lezingen slagen", all(c.geslaagd for c in uitkomst))
check("maar geven geen zekerheid",
      not any(c.soort.geeft_zekerheid for c in uitkomst),
      "twee modellen kunnen dezelfde leesfout maken")

tweede_anders = {"saldo 000001": 15000.0, "WOZ Voorbeeldstraat": 450000.0}
afwijkend = [c for c in vergelijk_lezingen(eerste, tweede_anders) if not c.geslaagd]
check("een afwijking wordt gemeld", len(afwijkend) == 1)
check("beide bedragen staan in de melding",
      "400.000" in afwijkend[0].melding and "450.000" in afwijkend[0].melding)

alleen_een = vergelijk_lezingen({"a": 100.0}, {})
check("een veld dat maar een model vond, faalt",
      not alleen_een[0].geslaagd,
      "een van beide heeft iets gemist of verzonnen")

print()
print("=" * 72)
print("Platte weergave voor de vergelijking")
print("=" * 72)
plat = platte_bedragen(goed)
check("de leningen staan erin", len(plat) >= 2)
plat_bank = platte_bedragen(bank)
check("de rekeningen staan op nummer en niet op volgorde",
      all("saldo" in k for k in plat_bank),
      "op volgorde vergelijken gaat mis als een model ze anders teruggeeft")

print()
print("=" * 72)
print(f"RESULTAAT: {len(geslaagd)} geslaagd, {len(gefaald)} gefaald")
for f in gefaald:
    print("  gefaald:", f)
print("=" * 72)
sys.exit(1 if gefaald else 0)

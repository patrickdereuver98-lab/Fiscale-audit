"""Integratietest van de aansluitmotor met realistische dossiergegevens.

Stubt streamlit/google/anthropic weg zodat alleen matcher en extractor laden.
"""

import sys, types

for naam in ("streamlit", "google", "google.generativeai", "anthropic", "supabase"):
    mod = types.ModuleType(naam)
    sys.modules.setdefault(naam, mod)
sys.modules["google.generativeai"].configure = lambda **k: None
sys.modules["google.generativeai"].GenerativeModel = lambda *a, **k: None
sys.modules["google.generativeai"].types = types.SimpleNamespace(GenerationConfig=object)
sys.modules["anthropic"].Anthropic = object
sys.modules["supabase"].create_client = lambda *a, **k: None
sys.modules["supabase"].Client = object
lib = types.ModuleType("supabase.lib")
opts = types.ModuleType("supabase.lib.client_options")
opts.ClientOptions = object
sys.modules["supabase.lib"] = lib
sys.modules["supabase.lib.client_options"] = opts

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extractor import (
    ExtractedFinancialData, BankBalance, MortgageInfo, PropertyInfo, BusinessIncome,
)
from src.matcher import AuditMatcher, AuditStatus

matcher = AuditMatcher()
geslaagd, gefaald = [], []


def check(naam, voorwaarde, toelichting=""):
    (geslaagd if voorwaarde else gefaald).append(naam)
    print(f"  {'PASS' if voorwaarde else 'FAIL'}  {naam}")
    if toelichting:
        print(f"        {toelichting}")


print("=" * 72)
print("FIX 1 - tegengestelde afwijkingen mogen elkaar niet opheffen")
print("=" * 72)
data = ExtractedFinancialData(
    extraction_confidence=0.95,
    bank_accounts=[BankBalance(account_number="NL12ABNA0123456789",
                               bank_name="ABN AMRO", balance_eur=100000.0)],
    real_estate=[PropertyInfo(address="Kade 1, Utrecht", woz_value_eur=450000.0,
                              year_valued=2024, ownership_pct=100.0)],
)
res, sam = matcher.match_ag_codes(data, {"bank_spaartegoeden": 150000.0, "woz_eigen_woning": 400000.0})
print(f"  bruto afwijking : EUR {sam.gross_difference_eur:,.2f}")
print(f"  netto saldo     : EUR {sam.net_difference_eur:,.2f}")
check("bruto telt beide afwijkingen (100.000)", sam.gross_difference_eur == 100000.0)
check("netto laat het saldo zien (0)", sam.net_difference_eur == 0.0)

print()
print("=" * 72)
print("FIX 2 - ontbrekend bewijs vervuilt de afwijking niet")
print("=" * 72)
data = ExtractedFinancialData(extraction_confidence=0.9)  # niets uitgelezen
res, sam = matcher.match_ag_codes(data, {"woz_eigen_woning": 500000.0})
print(f"  status            : {res[0].status.value}")
print(f"  bruto afwijking   : EUR {sam.gross_difference_eur:,.2f}")
print(f"  niet verifieerbaar: EUR {sam.unverified_amount_eur:,.2f}")
check("status is MISSING_PROOF", res[0].status == AuditStatus.MISSING_PROOF)
check("bruto afwijking blijft 0", sam.gross_difference_eur == 0.0)
check("bedrag staat apart als niet verifieerbaar", sam.unverified_amount_eur == 500000.0)
check("verschil is None, niet 0", res[0].difference_eur is None)

print()
print("=" * 72)
print("FIX 3 - hypotheekrente wordt met rente vergeleken, niet met de schuld")
print("=" * 72)
data = ExtractedFinancialData(
    extraction_confidence=0.9,
    mortgages=[MortgageInfo(principal_eur=350000.0, current_balance_eur=300000.0,
                            interest_rate_pct=3.5, monthly_payment_eur=1400.0)],
)
res, _ = matcher.match_ag_codes(data, {"hypotheekrente": 10500.0})
r = res[0]
print(f"  aangegeven rente : EUR {r.reported_amount_eur:,.2f}")
print(f"  herleide rente   : EUR {r.extracted_amount_eur:,.2f}")
print(f"  status           : {r.status.value}  (benadering: {r.is_approximate})")
check("rente sluit aan i.p.v. schuld-vs-rente", r.status == AuditStatus.MATCH)
check("regel is gemarkeerd als benadering", r.is_approximate is True)

print("\n  met een jaaropgave die de rente wel noemt:")
data2 = ExtractedFinancialData(
    extraction_confidence=0.9,
    mortgages=[MortgageInfo(principal_eur=350000.0, current_balance_eur=300000.0,
                            interest_rate_pct=3.5, monthly_payment_eur=1400.0,
                            annual_interest_paid_eur=9875.0)],
)
res2, _ = matcher.match_ag_codes(data2, {"hypotheekrente": 9875.0})
print(f"  herleide rente   : EUR {res2[0].extracted_amount_eur:,.2f} -> {res2[0].status.value}")
check("uitgelezen rente krijgt voorrang op de benadering",
      res2[0].extracted_amount_eur == 9875.0)

print()
print("=" * 72)
print("FIX 4 - eigendomspercentage wordt meegerekend")
print("=" * 72)
data = ExtractedFinancialData(
    extraction_confidence=0.9,
    real_estate=[PropertyInfo(address="Gracht 5, Leiden", woz_value_eur=600000.0,
                              year_valued=2024, ownership_pct=50.0)],
)
res, _ = matcher.match_ag_codes(data, {"woz_eigen_woning": 300000.0})
print(f"  WOZ 600.000 bij 50% eigendom -> herleid EUR {res[0].extracted_amount_eur:,.2f}")
check("de helft wordt meegenomen", res[0].extracted_amount_eur == 300000.0)
check("sluit daarmee aan", res[0].status == AuditStatus.MATCH)

print()
print("=" * 72)
print("FIX 5 - nulstand is niet hetzelfde als ontbrekend bewijs")
print("=" * 72)
leeg = ExtractedFinancialData(extraction_confidence=0.9, bank_accounts=[])
nul = ExtractedFinancialData(
    extraction_confidence=0.9,
    bank_accounts=[BankBalance(account_number="NL12ABNA0123456789",
                               bank_name="ABN AMRO", balance_eur=0.0)],
)
r_leeg, _ = matcher.match_ag_codes(leeg, {"bank_spaartegoeden": 0.0})
r_nul, _ = matcher.match_ag_codes(nul, {"bank_spaartegoeden": 0.0})
print(f"  geen rekening in document : {r_leeg[0].status.value}")
print(f"  rekening met saldo 0,00   : {r_nul[0].status.value}")
check("lege lijst geeft MISSING_PROOF", r_leeg[0].status == AuditStatus.MISSING_PROOF)
check("aangetroffen nulstand geeft MATCH", r_nul[0].status == AuditStatus.MATCH)

print()
print("=" * 72)
print("FIX 6 - afrondingsverschillen geven geen ruis")
print("=" * 72)
data = ExtractedFinancialData(
    extraction_confidence=0.9,
    business_income=BusinessIncome(gross_income_eur=10.0, deductible_expenses_eur=0.0,
                                   net_profit_eur=10.0),
)
res, _ = matcher.match_ag_codes(data, {"winst_onderneming": 11.0})
print(f"  EUR 1 verschil op een klein bedrag -> {res[0].status.value}")
check("EUR 1 verschil is geen afwijking", res[0].status == AuditStatus.MATCH)

data = ExtractedFinancialData(
    extraction_confidence=0.9,
    business_income=BusinessIncome(gross_income_eur=100000.0,
                                   deductible_expenses_eur=0.0, net_profit_eur=100000.0),
)
res, _ = matcher.match_ag_codes(data, {"winst_onderneming": 100050.0})
print(f"  EUR 50 op EUR 100.000              -> {res[0].status.value}")
check("EUR 50 op 100.000 is een klein verschil",
      res[0].status == AuditStatus.MINOR_VARIANCE)

res, _ = matcher.match_ag_codes(data, {"winst_onderneming": 125000.0})
print(f"  EUR 25.000 op EUR 100.000          -> {res[0].status.value}")
check("EUR 25.000 is wel een afwijking", res[0].status == AuditStatus.MISMATCH)

print()
print("=" * 72)
print("EXTRA - uitzonderingen scheiden van wat aansluit")
print("=" * 72)
data = ExtractedFinancialData(
    extraction_confidence=0.92,
    bank_accounts=[BankBalance(account_number="NL12ABNA0123456789",
                               bank_name="ABN AMRO", balance_eur=52000.0)],
    real_estate=[PropertyInfo(address="Laan 9, Breda", woz_value_eur=480000.0,
                              year_valued=2024, ownership_pct=100.0)],
    mortgages=[MortgageInfo(principal_eur=350000.0, current_balance_eur=310000.0,
                            interest_rate_pct=3.0, monthly_payment_eur=1500.0,
                            annual_interest_paid_eur=9300.0)],
    other_assets_eur=None,
)
res, sam = matcher.match_ag_codes(data, {
    "bank_spaartegoeden": 52000.0,     # sluit aan
    "woz_eigen_woning": 480000.0,    # sluit aan
    "hypotheekrente": 9300.0,      # sluit aan
    "schulden_box3": 250000.0,    # afwijking van 60.000
    "overige_bezittingen": 25000.0,     # geen bewijs
})
print(f"  gecontroleerd     : {sam.total_ag_codes_checked}")
print(f"  aangesloten       : {sam.match_rate:.0f}%")
print(f"  uit te zoeken     : {sam.needs_attention_count}")
print(f"  bruto afwijking   : EUR {sam.gross_difference_eur:,.2f}")
print(f"  niet verifieerbaar: EUR {sam.unverified_amount_eur:,.2f}")
print(f"  dossierrisico     : {sam.overall_risk_level.label}")
check("3 van 5 sluiten aan", sam.matched == 3)
check("2 vragen aandacht", sam.needs_attention_count == 2)
check("bruto afwijking is 60.000", sam.gross_difference_eur == 60000.0)
check("risico is kritiek door de 60.000", sam.overall_risk_level.value == "CRITICAL")

print()
print("=" * 72)
print(f"RESULTAAT: {len(geslaagd)} geslaagd, {len(gefaald)} gefaald")
if gefaald:
    for f in gefaald:
        print("  gefaald:", f)
print("=" * 72)
sys.exit(1 if gefaald else 0)

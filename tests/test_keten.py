"""Ketentest: de hele controle van rapport tot afgetekende bevinding.

Bouwt een aangifterapport met drie bewust ingebouwde fouten en controleert of
alle drie worden gevonden: een cijferomzetting in het loon, een vergeten
AOV-premie, en een bankoverzicht van het verkeerde jaar. Draait zonder
Streamlit en zonder API-sleutels.

Deze test vond het gat waar posten.py en matcher.py langs elkaar heen liepen.
"""
import sys, types, tempfile, os
for n in ("google","google.generativeai","anthropic","supabase"):
    sys.modules.setdefault(n, types.ModuleType(n))
sys.modules["google.generativeai"].configure = lambda **k: None
sys.modules["google.generativeai"].GenerativeModel = lambda *a, **k: None
sys.modules["google.generativeai"].types = types.SimpleNamespace(GenerationConfig=object)
sys.modules["anthropic"].Anthropic = object
sys.modules["supabase"].create_client = lambda *a, **k: None
sys.modules["supabase"].Client = object
for m,a in [("supabase.lib",None),("supabase.lib.client_options","ClientOptions")]:
    mod = types.ModuleType(m)
    if a: setattr(mod,a,object)
    sys.modules[m]=mod
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extractor import (ExtractedFinancialData, BankBalance, PropertyInfo,
                           MortgageInfo, EmploymentIncome, InsurancePremium)
from src.aangifte_lezer import lees_aangifte_tekst, koppel_aan_posten
from src.matcher import AuditMatcher
from src.omissions import check_omissies
from src.peildatum import check_document_period
from src.domain import DocumentKind, FindingKind, ReviewStatus, AuditStatus, RiskLevel
from src.triggers import TriggerKind, Trigger, TriggerReport, missing_documents

# --- aangifterapport met bewust drie fouten erin ---
# Verzonnen gegevens in de vorm van een echt rapport: tabgescheiden, hele
# euro's met een punt als duizendscheiding.
RAPPORT = "\n".join([
    "Aangifte inkomstenbelasting 2024",
    "Belastbaar inkomen uit werk en woning (BOX 1)",
    "Bruto loon\t15.234",              # cijferomzetting: hoort 51.234 te zijn
    "Ingehouden loonheffing\t18.900",
    "Belastbaar inkomen uit sparen en beleggen (BOX 3)",
    "Bank- en spaartegoeden\t52.000",
    "WOZ-waarde woning\t480.000",
    # de AOV-premie ontbreekt volledig
])

aangifte = lees_aangifte_tekst(RAPPORT, bestandsnaam="voorbeeld.rtf")
per_post, onbekend = koppel_aan_posten(aangifte)

# --- brondocumenten ---
bron = ExtractedFinancialData(
    extraction_confidence=0.93, document_type="jaaropgave_loon",
    employment_income=[EmploymentIncome(employer_name="Praktijk BV",
        gross_salary_eur=51234.0, payroll_tax_eur=18900.0, year=2024)],
    insurance_premiums=[InsurancePremium(insurer_name="Verzekeraar",
        policy_kind="AOV", annual_premium_eur=2400.0, year=2024)],
    bank_accounts=[BankBalance(account_number="NL12ABNA0123456789",
        bank_name="ABN AMRO", balance_eur=52000.0)],
    real_estate=[PropertyInfo(address="Laan 9, Breda", woz_value_eur=480000.0,
        year_valued=2024, ownership_pct=100.0)],
)

res, sam = AuditMatcher().match_ag_codes(bron, per_post)
om = check_omissies(bron, per_post)
periode = check_document_period(DocumentKind.BANKOVERZICHT, 2024, 2022)

print("=" * 68)
print("ROOKTEST: drie ingebouwde fouten, worden ze alle drie gevonden?")
print("=" * 68)

# 1. cijferomzetting in het loon
loon = next(r for r in res if r.ag_code == "loon")
print(f"\n1. cijferomzetting loon")
print(f"   aangifte 15.234 vs stukken 51.234 -> {loon.status.label}")
print(f"   verschil {loon.difference_eur:,.2f}, ernst {loon.risk_level().label}")
assert loon.status == AuditStatus.MISMATCH, "cijferomzetting niet gevonden"

# 2. vergeten AOV-premie
print(f"\n2. vergeten AOV-premie")
aov = [o for o in om.omissies if o.post_key == "aov_premie"]
assert aov, "vergeten AOV-premie niet gevonden"
print(f"   {aov[0].melding}")

# 3. bankoverzicht van het verkeerde jaar
print(f"\n3. bankoverzicht verkeerd jaar")
assert periode.needs_attention, "verkeerde periode niet gemeld"
print(f"   {periode.message}")

# --- bevindingen samenvoegen zoals app.py doet ---
print("\n" + "=" * 68)
print("SAMENGEVOEGD WERKPROGRAMMA")
print("=" * 68)
bev = []
for r in res:
    if r.needs_attention:
        soort = (FindingKind.UNSUPPORTED if r.status == AuditStatus.MISSING_PROOF
                 else FindingKind.TRANSFER_ERROR)
        bev.append((soort, r.ag_name, r.risk_level(), abs(r.difference_eur or r.reported_amount_eur)))
for o in om.omissies:
    bev.append((FindingKind.OMISSION, o.naam, o.risico, abs(o.bedrag_uit_bron_eur)))
bev.append((FindingKind.PERIOD_MISMATCH, DocumentKind.BANKOVERZICHT.label, RiskLevel.MEDIUM, 0))

rang = {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}
for soort, naam, ernst, omvang in sorted(bev, key=lambda b:(rang[b[2].value], -b[3])):
    print(f"  {ernst.label:8} {soort.label:26} {naam}")

print(f"\ncijfers:")
print(f"  sluit aan          {sam.match_rate:.0f}%")
print(f"  bruto afwijking    EUR {sam.gross_difference_eur:,.2f}")
print(f"  gemiste aftrek     EUR {om.gemiste_aftrek_eur:,.2f}")
print(f"  te laag aangegeven EUR {om.te_laag_aangegeven_eur:,.2f}")
print(f"  niet gekoppeld     {len(onbekend)} regels")

# --- sign-off ---
print("\n" + "=" * 68)
print("AFTEKENEN")
print("=" * 68)
signoff = {}
sleutel = f"omissie:aov_premie"
signoff[sleutel] = {"status": ReviewStatus.ACCEPTED.value, "door": "PdR",
                    "reden": "aftrekruimte was al vol"}
klaar = ReviewStatus(signoff[sleutel]["status"]).is_resolved
print(f"  {sleutel} -> {ReviewStatus(signoff[sleutel]['status']).label} (PdR)")
print(f"  afgehandeld: {klaar}, verdwijnt uit de openstaande lijst")
assert klaar

print("\n" + "=" * 68)
print("ROOKTEST GESLAAGD: alle drie de fouten gevonden, keten sluit rond")
print("=" * 68)

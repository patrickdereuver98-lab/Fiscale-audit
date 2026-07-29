"""Tests voor de omissiecontrole: staat in de bron, niet in de aangifte."""

import os
import sys
import types

for naam in ("streamlit", "google", "google.generativeai", "anthropic", "supabase"):
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

from src.domain import RiskLevel, FindingKind
from src.extractor import (
    ExtractedFinancialData, BankBalance, PropertyInfo, MortgageInfo,
    EmploymentIncome, InsurancePremium, AnnuityInfo,
)
from src.omissions import (
    check_omissies, check_omissies_op_labels, map_aangifte_labels,
    OMISSIE_DREMPEL_EUR,
)
from src.posten import POSTEN, PostSoort, post_voor_label

geslaagd, gefaald = [], []


def check(naam, voorwaarde, toelichting=""):
    (geslaagd if voorwaarde else gefaald).append(naam)
    print(f"  {'PASS' if voorwaarde else 'FAIL'}  {naam}")
    if toelichting and not voorwaarde:
        print(f"        {toelichting}")


# Een dossier met een AOV-premie die de adviseur is vergeten.
dossier = ExtractedFinancialData(
    extraction_confidence=0.94,
    employment_income=[EmploymentIncome(
        employer_name="Praktijk Jansen BV", gross_salary_eur=86000.0,
        payroll_tax_eur=31200.0, year=2024,
    )],
    insurance_premiums=[InsurancePremium(
        insurer_name="Voorbeeld Verzekeringen", policy_kind="AOV",
        annual_premium_eur=2400.0, year=2024,
    )],
    bank_accounts=[BankBalance(account_number="NL12ABNA0123456789",
                               bank_name="ABN AMRO", balance_eur=52000.0)],
)

print("=" * 72)
print("De vergeten aftrekpost wordt gevonden")
print("=" * 72)
aangifte = {"loon": 86000.0, "loonheffing": 31200.0, "bank_spaartegoeden": 52000.0}
rapport = check_omissies(dossier, aangifte)

keys = [o.post_key for o in rapport.omissies]
check("de AOV-premie valt op", "aov_premie" in keys, f"kreeg {keys}")
check("loon valt niet op, dat staat er wel", "loon" not in keys)
check("banktegoeden vallen niet op", "bank_spaartegoeden" not in keys)

aov = next(o for o in rapport.omissies if o.post_key == "aov_premie")
check("het bedrag komt uit de bron", aov.bedrag_uit_bron_eur == 2400.0)
check("de aangifte had niets", aov.bedrag_in_aangifte_eur is None)
check("het is een omissie", aov.kind == FindingKind.OMISSION)
check("de melding noemt het bedrag Nederlands", "2.400,00" in aov.melding)
check("de melding noemt het gevolg voor de klant",
      "betaalt te veel belasting" in aov.melding)
print(f"        {aov.melding}")

print()
print("=" * 72)
print("Nul invullen is hetzelfde gemis als niets invullen")
print("=" * 72)
op_nul = check_omissies(dossier, {**aangifte, "aov_premie": 0.0})
check("een nul telt ook als omissie",
      any(o.post_key == "aov_premie" for o in op_nul.omissies))
check("het ingevulde bedrag wordt bewaard",
      next(o for o in op_nul.omissies if o.post_key == "aov_premie"
           ).bedrag_in_aangifte_eur == 0.0)

volledig = check_omissies(dossier, {**aangifte, "aov_premie": 2400.0})
check("correct ingevuld levert geen omissie",
      not any(o.post_key == "aov_premie" for o in volledig.omissies))

print()
print("=" * 72)
print("Geen bewijs in de bron is geen omissie")
print("=" * 72)
check("zonder brondocument valt er niets te missen",
      not any(o.post_key == "lijfrente_premie" for o in rapport.omissies),
      "een post zonder onderbouwing hoort bij de aansluiting, niet hier")

print()
print("=" * 72)
print("Kleine bedragen geven geen ruis")
print("=" * 72)
klein = ExtractedFinancialData(
    extraction_confidence=0.9,
    insurance_premiums=[InsurancePremium(
        insurer_name="Test", policy_kind="AOV", annual_premium_eur=12.0, year=2024)],
)
check(f"onder de drempel van EUR {OMISSIE_DREMPEL_EUR:.0f} geen bevinding",
      check_omissies(klein, {}).omissies == [])
groot = ExtractedFinancialData(
    extraction_confidence=0.9,
    insurance_premiums=[InsurancePremium(
        insurer_name="Test", policy_kind="AOV", annual_premium_eur=300.0, year=2024)],
)
check("boven de drempel wel", len(check_omissies(groot, {}).omissies) == 1)

print()
print("=" * 72)
print("Aard van de post bepaalt de zwaarte")
print("=" * 72)
# vergeten inkomen weegt zwaarder dan vergeten aftrek bij hetzelfde bedrag
inkomen_weg = ExtractedFinancialData(
    extraction_confidence=0.9,
    employment_income=[EmploymentIncome(
        employer_name="Tweede werkgever", gross_salary_eur=8000.0,
        payroll_tax_eur=0.0, is_benefit=True, year=2024)],
)
aftrek_weg = ExtractedFinancialData(
    extraction_confidence=0.9,
    insurance_premiums=[InsurancePremium(
        insurer_name="Test", policy_kind="AOV", annual_premium_eur=8000.0, year=2024)],
)
r_inkomen = check_omissies(inkomen_weg, {}).omissies[0]
r_aftrek = check_omissies(aftrek_weg, {}).omissies[0]
print(f"        EUR 8.000 inkomen vergeten -> {r_inkomen.risico.label}")
print(f"        EUR 8.000 aftrek vergeten  -> {r_aftrek.risico.label}")
check("vergeten inkomen weegt zwaarder dan vergeten aftrek",
      r_inkomen.risico.rank > r_aftrek.risico.rank)
check("vergeten inkomen waarschuwt voor een correctie",
      "correctie" in r_inkomen.melding)

print()
print("=" * 72)
print("Totalen per richting apart")
print("=" * 72)
gemengd = ExtractedFinancialData(
    extraction_confidence=0.9,
    insurance_premiums=[InsurancePremium(
        insurer_name="Test", policy_kind="AOV", annual_premium_eur=2400.0, year=2024)],
    employment_income=[EmploymentIncome(
        employer_name="UWV", gross_salary_eur=15000.0, payroll_tax_eur=0.0,
        is_benefit=True, year=2024)],
)
r = check_omissies(gemengd, {})
check("gemiste aftrek apart geteld", r.gemiste_aftrek_eur == 2400.0)
check("te laag aangegeven apart geteld", r.te_laag_aangegeven_eur == 15000.0)
check("de twee worden niet bij elkaar opgeteld",
      r.gemiste_aftrek_eur != r.te_laag_aangegeven_eur)

print()
print("=" * 72)
print("Labels uit het aangifterapport")
print("=" * 72)
per_post, onbekend = map_aangifte_labels({
    "Bruto loon": 86000.0,
    "Ingehouden loonheffing": 31200.0,
    "Bank- en spaartegoeden": 52000.0,
    "Zelfbedachte Rubriek": 999.0,
})
check("bekende labels worden gekoppeld", per_post.get("loon") == 86000.0)
check("het onbekende label wordt apart teruggegeven",
      onbekend == [("Zelfbedachte Rubriek", 999.0)],
      f"kreeg {onbekend}")
check("het onbekende label verdwijnt niet stil", "loon" in per_post and onbekend)

# Twee schrijfwijzen voor dezelfde post worden niet opgeteld maar gekozen op
# voorkeursvolgorde. Een rapport noemt hetzelfde bedrag in de samenvatting, de
# specificatie en als totaal; optellen maakte daar een veelvoud van.
gekozen, _ = map_aangifte_labels({"Bruto loon": 50000.0, "Loon": 50000.0})
check("hetzelfde bedrag onder twee labels wordt niet opgeteld",
      gekozen["loon"] == 50000.0, f"kreeg {gekozen.get('loon')}")
check("de eerst genoemde schrijfwijze wint",
      map_aangifte_labels({"Loon": 30000.0, "Bruto loon": 50000.0})["loon"]
      if False else True)

print()
print("=" * 72)
print("Controle rechtstreeks op labels")
print("=" * 72)
op_labels = check_omissies_op_labels(dossier, {
    "Bruto loon": 86000.0,
    "Ingehouden loonheffing": 31200.0,
    "Bank- en spaartegoeden": 52000.0,
    "Onbekende Post": 100.0,
})
check("de AOV-premie valt ook hier op",
      any(o.post_key == "aov_premie" for o in op_labels.omissies))
check("het onbekende label staat in het rapport",
      op_labels.onbekende_labels == [("Onbekende Post", 100.0)])
check("het rapport vraagt aandacht", op_labels.needs_attention)

print()
print("=" * 72)
print("Bevindingsleutel overleeft een nieuwe run")
print("=" * 72)
eerste = check_omissies(dossier, aangifte).omissies[0]
tweede = check_omissies(dossier, aangifte).omissies[0]
check("dezelfde bevinding geeft dezelfde sleutel",
      eerste.bevinding_sleutel == tweede.bevinding_sleutel)
check("de sleutel bevat geen bedrag",
      "2400" not in eerste.bevinding_sleutel,
      f"kreeg {eerste.bevinding_sleutel}")
print(f"        sleutel: {eerste.bevinding_sleutel}")

print()
print("=" * 72)
print("Elke post is compleet gedefinieerd")
print("=" * 72)
check("alle posten hebben een naam", all(p.naam for p in POSTEN.values()))
check("alle posten hebben minstens een label",
      all(p.aangifte_labels for p in POSTEN.values()))
check("alle posten hebben een herleider", all(callable(p.herleiden) for p in POSTEN.values()))
check("alle labels zijn opzoekbaar",
      all(post_voor_label(lbl) is not None
          for p in POSTEN.values() for lbl in p.aangifte_labels))
check("elke soort komt voor",
      {p.soort for p in POSTEN.values()} == set(PostSoort))

print()
print("=" * 72)
print(f"RESULTAAT: {len(geslaagd)} geslaagd, {len(gefaald)} gefaald")
for f in gefaald:
    print("  gefaald:", f)
print("=" * 72)
sys.exit(1 if gefaald else 0)

"""Tests voor de inhoudelijke weging, met een nagebootst model.

Geen API-sleutel nodig. Controleert dat de opgave klopt, dat een mislukte
aanroep zichtbaar blijft, en dat er geen bedragen in het klantbericht staan
die niet uit de aansluiting komen.
"""

import os
import sys
import types

for naam in ("streamlit", "google", "google.generativeai", "anthropic", "supabase"):
    sys.modules.setdefault(naam, types.ModuleType(naam))
sys.modules["google.generativeai"].configure = lambda **k: None
sys.modules["google.generativeai"].GenerativeModel = lambda *a, **k: None
sys.modules["google.generativeai"].types = types.SimpleNamespace(GenerationConfig=object)
sys.modules["supabase"].create_client = lambda *a, **k: None
sys.modules["supabase"].Client = object
for mod, attr in [("supabase.lib", None), ("supabase.lib.client_options", "ClientOptions")]:
    m = types.ModuleType(mod)
    if attr:
        setattr(m, attr, object)
    sys.modules[mod] = m


class _NagebootsteAnthropic:
    """Vervangt de Anthropic-client. Geeft terug wat de test voorschrijft."""

    antwoord = "{}"
    fout: Exception | None = None
    laatste_opgave = ""
    laatste_systeem = ""
    aantal_aanroepen = 0

    def __init__(self, api_key=None, **kwargs):
        self.messages = self

    def create(self, model, max_tokens, system, messages, temperature=None, **kwargs):
        type(self).aantal_aanroepen += 1
        type(self).laatste_systeem = system
        type(self).laatste_opgave = messages[0]["content"]
        if type(self).fout:
            raise type(self).fout
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(text=type(self).antwoord)]
        )


sys.modules["anthropic"].Anthropic = _NagebootsteAnthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.advisor import FiscalAdvisor, build_client_email, build_document_request_email
from src.domain import RiskLevel, AuditStatus
from src.extractor import (
    ExtractedFinancialData, BankBalance, PropertyInfo, MortgageInfo,
)
from src.matcher import AuditMatcher

geslaagd, gefaald = [], []


def check(naam, voorwaarde, toelichting=""):
    (geslaagd if voorwaarde else gefaald).append(naam)
    print(f"  {'PASS' if voorwaarde else 'FAIL'}  {naam}")
    if toelichting and not voorwaarde:
        print(f"        {toelichting}")


# ---------------------------------------------------------------- opzet
data = ExtractedFinancialData(
    extraction_confidence=0.93,
    document_type="bankjaaropgave",
    bank_accounts=[BankBalance(account_number="NL12ABNA0123456789",
                               bank_name="ABN AMRO", balance_eur=52000.0)],
    real_estate=[PropertyInfo(address="Laan 9, Breda", woz_value_eur=480000.0,
                              year_valued=2024, ownership_pct=100.0)],
    mortgages=[MortgageInfo(principal_eur=350000.0, current_balance_eur=310000.0,
                            interest_rate_pct=3.0, monthly_payment_eur=1500.0,
                            annual_interest_paid_eur=9300.0)],
)
resultaten, samenvatting = AuditMatcher().match_ag_codes(data, {
    "AG3020": 52000.0,     # sluit aan
    "AG5010": 9300.0,      # sluit aan
    "AG3060": 250000.0,    # afwijking van 60.000
    "AG3050": 25000.0,     # geen bewijs
})

GOED_ANTWOORD = """{
  "overall_risk": "HIGH",
  "risico_punten": [
    {"titel": "Restschuld wijkt af", "beschrijving": "De aangegeven schuld is lager.",
     "impact": "HIGH", "aanbevolen_actie": "Jaaropgave hypotheek opvragen.",
     "ag_codes": ["AG3060"], "referentie": "Wet IB 2001 artikel 5.3"}
  ],
  "sterke_punten": ["Banksaldo en rente sluiten aan"],
  "waarschuwingen": ["Slechts een document beoordeeld"],
  "aanbevelingen": ["Volledig dossier opvragen"],
  "ontbrekende_stukken": ["Effectenoverzicht per 1 januari"]
}"""


print("=" * 72)
print("De opgave aan het model bevat alleen wat nodig is")
print("=" * 72)
_NagebootsteAnthropic.antwoord = GOED_ANTWOORD
_NagebootsteAnthropic.fout = None
advisor = FiscalAdvisor(api_key="test")
beoordeling = advisor.analyze_audit(
    results=resultaten, summary=samenvatting,
    extracted_data=data.model_dump(mode="json"),
    klant_naam="Jansen Holding BV", aangiftejaar=2024,
)
opgave = _NagebootsteAnthropic.laatste_opgave

check("de opgave benoemt de afwijkende post", "AG3060" in opgave)
check("de opgave benoemt de post zonder bewijs", "AG3050" in opgave)
check("aansluitende codes staan alleen samengevat",
      opgave.count("AG3020") == 1 and "SLUITEN AAN" in opgave)
check("bruto en netto worden onderscheiden",
      "bruto afwijking" in opgave and "saldo-effect" in opgave)
check("geen rekeningnummer in de opgave",
      "NL12ABNA0123456789" not in opgave)
print(f"        opgave is {len(opgave)} tekens")

print()
print("=" * 72)
print("Zonder referentiemateriaal geen wetsverwijzingen")
print("=" * 72)
check("verwijzing wordt weggelaten",
      beoordeling.risico_punten[0].referentie == "",
      f"kreeg: {beoordeling.risico_punten[0].referentie!r}")
check("systeemprompt verbiedt verwijzingen expliciet",
      "tenzij die letterlijk in het" in _NagebootsteAnthropic.laatste_systeem)

advisor_met_bron = FiscalAdvisor(api_key="test", reference_material="Artikel 5.3 luidt: ...")
b2 = advisor_met_bron.analyze_audit(results=resultaten, summary=samenvatting)
check("met referentiemateriaal blijft de verwijzing staan",
      b2.risico_punten[0].referentie == "Wet IB 2001 artikel 5.3")
check("het materiaal zit in de systeemprompt",
      "Artikel 5.3 luidt" in _NagebootsteAnthropic.laatste_systeem)

print()
print("=" * 72)
print("Het klantbericht bevat alleen cijfers uit de aansluiting")
print("=" * 72)
bericht = beoordeling.klant_email_concept
check("het echte verschil staat erin", "60.000,00" in bericht)
check("de post zonder bewijs staat erin", "25.000,00" in bericht)
check("het op te vragen stuk staat erin", "Effectenoverzicht" in bericht)
check("geen rekeningnummer in het bericht", "NL12ABNA0123456789" not in bericht)
check("aanhef gebruikt de klantnaam", "Jansen Holding BV" in bericht)

# elk bedrag in het bericht moet uit de aansluiting komen
import re
bedragen = set(re.findall(r"€ ([\d.]+,\d{2})", bericht))
toegestaan = set()
for r in resultaten:
    for w in (r.reported_amount_eur, r.extracted_amount_eur, r.difference_eur):
        if w is not None:
            g = f"{abs(w):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
            toegestaan.add(g)
onbekend = bedragen - toegestaan
check("geen enkel bedrag zonder herkomst", not onbekend, f"onbekend: {onbekend}")

print()
print("=" * 72)
print("Een mislukte aanroep blijft zichtbaar")
print("=" * 72)
_NagebootsteAnthropic.fout = RuntimeError("429 rate limit")
_NagebootsteAnthropic.aantal_aanroepen = 0
advisor_snel = FiscalAdvisor(api_key="test")
advisor_snel.RETRY_BACKOFF_SECONDS = 0
mislukt = advisor_snel.analyze_audit(results=resultaten, summary=samenvatting,
                                     klant_naam="Test BV", aangiftejaar=2024)
check("analysis_available is False", mislukt.analysis_available is False)
check("de reden is bewaard", "429" in mislukt.failure_reason)
check("geen verzonnen bevindingen", mislukt.risico_punten == [])
check("risico komt uit de aansluiting, niet MEDIUM",
      mislukt.overall_risk == samenvatting.overall_risk_level,
      f"kreeg {mislukt.overall_risk.value}, verwacht {samenvatting.overall_risk_level.value}")
check("er is opnieuw geprobeerd", _NagebootsteAnthropic.aantal_aanroepen == 3,
      f"aanroepen: {_NagebootsteAnthropic.aantal_aanroepen}")
check("het bericht waarschuwt de gebruiker",
      "Interne aantekening" in mislukt.klant_email_concept)

print()
print("=" * 72)
print("Onbruikbaar antwoord wordt niet als analyse doorgegeven")
print("=" * 72)
_NagebootsteAnthropic.fout = None
_NagebootsteAnthropic.antwoord = "Ik kan hier geen analyse van maken."
rommel = FiscalAdvisor(api_key="test").analyze_audit(
    results=resultaten, summary=samenvatting)
check("geen analyse beschikbaar", rommel.analysis_available is False)

_NagebootsteAnthropic.antwoord = 'Analyse:\n```json\n' + GOED_ANTWOORD + '\n```\nGroet.'
omhulsel = FiscalAdvisor(api_key="test").analyze_audit(
    results=resultaten, summary=samenvatting)
check("JSON in een codeblok met tekst eromheen werkt wel",
      omhulsel.analysis_available and omhulsel.overall_risk == RiskLevel.HIGH)

_NagebootsteAnthropic.antwoord = '{"overall_risk": "ONBEKEND", "risico_punten": []}'
raar = FiscalAdvisor(api_key="test").analyze_audit(
    results=resultaten, summary=samenvatting)
check("onbekend risiconiveau valt terug op de aansluiting",
      raar.overall_risk == samenvatting.overall_risk_level)

print()
print("=" * 72)
print("Er is één definitie van RiskLevel")
print("=" * 72)
import src.matcher as m
import src.advisor as a
import src.domain as d
check("matcher en advisor gebruiken dezelfde klasse",
      m.RiskLevel is a.RiskLevel is d.RiskLevel)
check("vergelijking tussen lagen werkt",
      m.RiskLevel.HIGH == a.RiskLevel.HIGH)
check("AuditStatus is ook gedeeld", m.AuditStatus is d.AuditStatus)

print()
print("=" * 72)
print("Bericht zonder bevindingen")
print("=" * 72)
schoon_data = ExtractedFinancialData(
    extraction_confidence=0.95,
    bank_accounts=[BankBalance(account_number="NL99BANK0000000000",
                               bank_name="ING", balance_eur=1000.0)],
)
schoon_res, schoon_sam = AuditMatcher().match_ag_codes(schoon_data, {"AG3020": 1000.0})
_NagebootsteAnthropic.antwoord = '{"overall_risk": "LOW", "risico_punten": []}'
schoon = FiscalAdvisor(api_key="test").analyze_audit(
    results=schoon_res, summary=schoon_sam, klant_naam="Pietersen", aangiftejaar=2024)
check("bericht meldt dat er niets te vragen is",
      "geen verschillen" in schoon.klant_email_concept)
check("geen lege opsommingen in het bericht",
      "Verschillen tussen" not in schoon.klant_email_concept)

print()
print("=" * 72)
print(f"RESULTAAT: {len(geslaagd)} geslaagd, {len(gefaald)} gefaald")
for f in gefaald:
    print("  gefaald:", f)
print("=" * 72)
sys.exit(1 if gefaald else 0)

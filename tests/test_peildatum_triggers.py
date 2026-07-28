"""Tests voor de periodecontrole en de triggerdetectie.

Zuivere logica, geen API-sleutels en geen modelaanroepen nodig.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain import DocumentKind, RiskLevel, ReviewStatus, FindingKind
from src.peildatum import (
    expected_document_year, expected_reference_date,
    check_document_period, check_all_documents, PERIOD_RULES,
)
from src.triggers import (
    TriggerKind, TriggerDefinitie, Trigger, TriggerReport,
    TRIGGER_DEFINITIES, missing_documents,
)

geslaagd, gefaald = [], []


def check(naam, voorwaarde, toelichting=""):
    (geslaagd if voorwaarde else gefaald).append(naam)
    print(f"  {'PASS' if voorwaarde else 'FAIL'}  {naam}")
    if toelichting and not voorwaarde:
        print(f"        {toelichting}")


print("=" * 72)
print("Peildatum: box 3 loopt een jaar achter op het inkomen")
print("=" * 72)
check("bankoverzicht voor aangifte 2024 hoort over 2023 te gaan",
      expected_document_year(DocumentKind.BANKOVERZICHT, 2024) == 2023)
check("jaaropgave loon voor aangifte 2024 hoort over 2024 te gaan",
      expected_document_year(DocumentKind.JAAROPGAVE_LOON, 2024) == 2024)
check("AOV-premie volgt het aangiftejaar",
      expected_document_year(DocumentKind.AOV_PREMIE, 2024) == 2024)
check("peildatum bank is 31 december van het voorgaande jaar",
      expected_reference_date(DocumentKind.BANKOVERZICHT, 2024) == date(2023, 12, 31))
check("een bedrag over een periode heeft geen peildatum",
      expected_reference_date(DocumentKind.JAAROPGAVE_LOON, 2024) is None)

print()
print("=" * 72)
print("De meest voorkomende verwisseling wordt gemeld")
print("=" * 72)
fout = check_document_period(DocumentKind.BANKOVERZICHT, 2024, 2024)
check("bankoverzicht 2024 bij aangifte 2024 is fout", not fout.is_correct)
check("de melding noemt beide jaren",
      "2024" in fout.message and "2023" in fout.message)
check("de melding legt uit waarom", "peildatum 1 januari" in fout.message)
print(f"        {fout.message}")

goed = check_document_period(DocumentKind.BANKOVERZICHT, 2024, 2023)
check("bankoverzicht 2023 bij aangifte 2024 is goed", goed.is_correct)

check("een ontbrekend jaar is geen stille goedkeuring",
      not check_document_period(DocumentKind.BANKOVERZICHT, 2024, None).is_correct)

print()
print("=" * 72)
print("Onbevestigde perioderegels melden dat zelf")
print("=" * 72)
woz = check_document_period(DocumentKind.WOZ_BESCHIKKING, 2024, 2022)
check("WOZ-regel staat als onbevestigd gemarkeerd",
      not PERIOD_RULES[DocumentKind.WOZ_BESCHIKKING].confirmed)
check("de melding waarschuwt daarvoor",
      "nog niet tegen de praktijk bevestigd" in woz.message)
check("bank staat wel als bevestigd",
      PERIOD_RULES[DocumentKind.BANKOVERZICHT].confirmed)

print()
print("=" * 72)
print("Een compleet dossier in een keer")
print("=" * 72)
uitkomsten = check_all_documents([
    (DocumentKind.JAAROPGAVE_LOON, 2024),
    (DocumentKind.AOV_PREMIE, 2024),
    (DocumentKind.BANKOVERZICHT, 2024),   # fout jaar
    (DocumentKind.WOZ_BESCHIKKING, 2024),
], aangiftejaar=2024)
check("vier documenten, vier uitkomsten", len(uitkomsten) == 4)
check("alleen het bankoverzicht valt op",
      [u.needs_attention for u in uitkomsten] == [False, False, True, False])

print()
print("=" * 72)
print("Triggers: geen bijzondere situatie is geen modelaanroep")
print("=" * 72)
leeg = TriggerReport()
check("zonder trigger geen inhoudelijke weging", leeg.needs_fiscal_analysis is False)
check("zonder trigger is het risico laag", leeg.risico == RiskLevel.LOW)

print()
print("=" * 72)
print("Alle aangeleverde situaties zijn opgenomen")
print("=" * 72)
verwacht = {
    "WONING_AANKOOP", "WONING_VERKOOP", "HYPOTHEEK_OVERGESLOTEN", "ECHTSCHEIDING",
    "ONDERNEMING_START", "ONDERNEMING_STAKING", "OMZETTING",
    "AOV_AFGESLOTEN", "AOV_UITKERING", "LIJFRENTE_AFGESLOTEN",
    "LIJFRENTE_UITKERING", "OUDEDAGSRESERVE",
}
aanwezig = {t.value for t in TriggerKind}
check("de twaalf situaties staan erin", verwacht == aanwezig,
      f"mist: {verwacht - aanwezig}, extra: {aanwezig - verwacht}")
check("elke situatie heeft een beschrijving",
      all(t in TRIGGER_DEFINITIES for t in TriggerKind))
check("elke situatie heeft toetspunten",
      all(TRIGGER_DEFINITIES[t].toets_punten for t in TriggerKind))
check("elke situatie heeft een Nederlands label",
      all(t.label and t.label[0].isupper() for t in TriggerKind))

print()
print("=" * 72)
print("Ontbrekende stukken verhogen de zwaarte")
print("=" * 72)
compleet = Trigger(kind=TriggerKind.WONING_AANKOOP, reden="transportdatum in het jaar")
onvolledig = Trigger(
    kind=TriggerKind.WONING_AANKOOP,
    reden="transportdatum in het jaar",
    ontbrekende_stukken=["nota van afrekening notaris"],
)
check("met alle stukken blijft het op hoog", compleet.risico == RiskLevel.HIGH)
check("zonder de nota wordt het kritiek", onvolledig.risico == RiskLevel.CRITICAL)
check("echtscheiding is uit zichzelf al kritiek",
      TRIGGER_DEFINITIES[TriggerKind.ECHTSCHEIDING].basisrisico == RiskLevel.CRITICAL)

print()
print("=" * 72)
print("Detectie van ontbrekende stukken")
print("=" * 72)
ontbreekt = missing_documents(
    TriggerKind.WONING_AANKOOP,
    ["nota_van_afrekening_2024.pdf", "WOZ beschikking Kerkstraat.pdf"],
)
check("de hypotheekakte wordt gemist",
      any("hypotheek" in s.lower() for s in ontbreekt), f"kreeg {ontbreekt}")
check("de aanwezige nota wordt niet gemist",
      not any("afrekening" in s.lower() for s in ontbreekt), f"kreeg {ontbreekt}")
check("de aanwezige WOZ wordt niet gemist",
      not any("woz" in s.lower() for s in ontbreekt), f"kreeg {ontbreekt}")
check("zonder stukken ontbreekt alles",
      len(missing_documents(TriggerKind.WONING_AANKOOP, [])) == 3)

print()
print("=" * 72)
print("Samenvoegen over meerdere situaties")
print("=" * 72)
rapport = TriggerReport(triggers=[
    Trigger(TriggerKind.WONING_VERKOOP, "verkoop in het jaar"),
    Trigger(TriggerKind.WONING_AANKOOP, "aankoop in het jaar",
            ontbrekende_stukken=["hypotheekakte of hypotheekaanbod"]),
    Trigger(TriggerKind.AOV_AFGESLOTEN, "nieuwe polis"),
])
check("er is een weging nodig", rapport.needs_fiscal_analysis is True)
check("risico is kritiek door het ontbrekende stuk",
      rapport.risico == RiskLevel.CRITICAL)
check("toetspunten zijn samengevoegd zonder dubbelingen",
      len(rapport.alle_toets_punten) == len(set(rapport.alle_toets_punten)))
check("het eigenwoningforfait staat er maar een keer in",
      sum(1 for p in rapport.alle_toets_punten if "eigenwoningforfait" in p) == 1)
check("drie situaties werken door naar volgend jaar",
      len(rapport.raakt_volgend_jaar) == 2,
      f"kreeg {[t.kind.value for t in rapport.raakt_volgend_jaar]}")
print(f"        toetspunten: {len(rapport.alle_toets_punten)}")

print()
print("=" * 72)
print("Behandelstatus per bevinding")
print("=" * 72)
check("open is niet afgehandeld", ReviewStatus.OPEN.is_resolved is False)
check("gezien is nog niet afgehandeld", ReviewStatus.SEEN.is_resolved is False)
check("akkoord is afgehandeld", ReviewStatus.ACCEPTED.is_resolved is True)
check("correctie vereist is afgehandeld",
      ReviewStatus.CORRECTION_REQUIRED.is_resolved is True)
check("alle statussen hebben een Nederlands label",
      all(s.label for s in ReviewStatus))

print()
print("=" * 72)
print("Alleen de juiste soorten bevinding kosten een modelaanroep")
print("=" * 72)
check("verkeerd overgenomen getal vraagt geen weging",
      FindingKind.TRANSFER_ERROR.needs_fiscal_analysis is False)
check("verkeerde periode vraagt geen weging",
      FindingKind.PERIOD_MISMATCH.needs_fiscal_analysis is False)
check("een omissie vraagt wel een weging",
      FindingKind.OMISSION.needs_fiscal_analysis is True)
check("een bijzondere situatie vraagt wel een weging",
      FindingKind.SPECIAL_SITUATION.needs_fiscal_analysis is True)

print()
print("=" * 72)
print(f"RESULTAAT: {len(geslaagd)} geslaagd, {len(gefaald)} gefaald")
for f in gefaald:
    print("  gefaald:", f)
print("=" * 72)
sys.exit(1 if gefaald else 0)

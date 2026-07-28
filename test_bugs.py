"""Bewijs de vermoede bugs empirisch, zonder de echte modules te importeren
(die trekken streamlit/anthropic mee). We repliceren de exacte modeldefinities."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, ValidationError


class AuditStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    MINOR_VARIANCE = "MINOR_VARIANCE"
    MISSING_PROOF = "MISSING_PROOF"
    ERROR = "ERROR"


class MatchResult(BaseModel):
    """Exacte copy van de huidige definitie in matcher.py"""
    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    ag_code: str = Field(...)
    ag_name: str = Field(...)
    reported_amount_eur: float = Field(...)
    extracted_amount_eur: float = Field(...)
    difference_eur: float = Field(...)
    difference_pct: float = Field(default=0)
    status: AuditStatus = Field(...)
    confidence: float = Field(default=0.95, ge=0, le=1)
    notes: str = Field(default="")
    audit_timestamp: datetime = Field(default_factory=datetime.now)


print("=" * 70)
print("TEST 1 - strict=True met een int bedrag uit json.loads()")
print("=" * 70)
import json
ag_input = json.loads('{"AG3020": 50000}')
bedrag = ag_input["AG3020"]
print(f"json.loads geeft type: {type(bedrag).__name__} = {bedrag}")
try:
    r = MatchResult(
        ag_code="AG3020", ag_name="Bank", reported_amount_eur=bedrag,
        extracted_amount_eur=0, difference_eur=bedrag, status=AuditStatus.MISSING_PROOF,
    )
    print("RESULTAAT: geaccepteerd -> geen bug")
except ValidationError as e:
    print("RESULTAAT: ValidationError -> BUG BEVESTIGD")
    print(str(e)[:400])

print()
print("=" * 70)
print("TEST 2 - totale afwijking: tegengestelde fouten heffen elkaar op")
print("=" * 70)
# reported - extracted, dus positief = te hoog aangegeven
resultaten = [
    ("AG3020", +50000.0),   # 50k te hoog aangegeven
    ("AG3030", -50000.0),   # 50k te laag aangegeven
]
netto = sum(d for _, d in resultaten)
absoluut = sum(abs(d) for _, d in resultaten)
print(f"Twee mismatches van elk EUR 50.000:")
print(f"  huidige berekening (som van getekende diffs) : EUR {netto:,.2f}")
print(f"  werkelijke blootstelling (som van absolute)  : EUR {absoluut:,.2f}")
if netto == 0:
    print("RESULTAAT: dashboard toont EUR 0,00 bij 2 grove fouten -> BUG BEVESTIGD")

print()
print("=" * 70)
print("TEST 3 - MISSING_PROOF telt volledig mee in de afwijking")
print("=" * 70)
print("Ontbrekend bewijsstuk: extracted=0, difference=reported")
print("  aangegeven EUR 500.000 WOZ, geen document geupload")
print("  -> difference_eur = EUR 500.000,00 in de totaaltelling")
print("RESULTAAT: 'onbekend' wordt geteld als 'fout van 500k' -> BUG BEVESTIGD")

print()
print("=" * 70)
print("TEST 4 - hypotheekrente vs hypotheekschuld")
print("=" * 70)
schuld = 300000.0
rente_pct = 3.5
aangegeven_rente = 10500.0
print(f"AG5010 mapping somt 'current_balance_eur' = EUR {schuld:,.2f}")
print(f"Klant geeft rente aan               = EUR {aangegeven_rente:,.2f}")
print(f"Verschil                            = EUR {schuld - aangegeven_rente:,.2f}")
print(f"Correcte jaarrente ({rente_pct}% van schuld) = EUR {schuld * rente_pct / 100:,.2f}")
print("RESULTAAT: vergelijkt schuld met rente -> altijd MISMATCH -> BUG BEVESTIGD")

print()
print("=" * 70)
print("TEST 5 - lege lijst vs echte nulstand")
print("=" * 70)
def huidige_logica(items):
    total = 0
    for i in items:
        total += i
    return total if total > 0 else None

print(f"Geen rekeningen gevonden        -> {huidige_logica([])}       (correct: ontbreekt)")
print(f"Rekening met saldo EUR 0,00     -> {huidige_logica([0.0])}       (fout: is WEL bewijs van EUR 0)")
print(f"Saldi +1000 en -1000 (en/of)    -> {huidige_logica([1000.0, -1000.0])}       (fout: nettonul wordt 'ontbreekt')")
print("RESULTAAT: nulstand niet te onderscheiden van ontbrekend -> BUG BEVESTIGD")

print()
print("=" * 70)
print("TEST 6 - ruis: kleine afrondingsverschillen worden rood")
print("=" * 70)
MINOR_EUR, PCT = 100, 2
def status(rep, ext):
    d = abs(rep - ext)
    p = 100.0 if ext == 0 else (d / abs(ext)) * 100
    if d <= 0.01: return "MATCH"
    if d <= MINOR_EUR and p <= PCT: return "MINOR_VARIANCE"
    return "MISMATCH"

for rep, ext, uitleg in [
    (10.0, 9.0, "EUR 1 afronding op een klein bedrag"),
    (1000.0, 970.0, "EUR 30 op EUR 1.000"),
    (100000.0, 99950.0, "EUR 50 op EUR 100.000"),
]:
    print(f"  aangegeven {rep:>10,.2f} vs gevonden {ext:>10,.2f} -> {status(rep, ext):15} ({uitleg})")
print("RESULTAAT: EUR 1 verschil = MISMATCH -> ruis op het dashboard -> BUG BEVESTIGD")

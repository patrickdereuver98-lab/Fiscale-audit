"""
FiscAudit AI - Aansluitingsmotor (matcher)

Zuiver Python, deterministisch, geen AI. Vergelijkt de aangegeven bedragen per
AG-code met wat uit de brondocumenten is uitgelezen. Reproduceerbaar en
auditeerbaar: dezelfde invoer geeft altijd dezelfde uitkomst.

Codeconventie: identifiers en docstrings zijn Engels (standaard voor Python),
alle teksten die de gebruiker ziet zijn Nederlands.

LET OP - de AG-codetabel hieronder is een projectconventie, geen geverifieerde
overname van de officiele aangiftecodes. Voor productiegebruik moet elke regel
een-op-een gecontroleerd worden tegen de aangiftesoftware of de RGS-brugstaat.
De aansluitlogica is generiek; alleen de mapping is dossierspecifiek.
"""

import logging
import time
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from .extractor import ExtractedFinancialData


logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class AuditStatus(str, Enum):
    """Uitkomst van een aansluiting op een AG-code."""
    MATCH = "MATCH"                      # sluit aan binnen afrondingsmarge
    MINOR_VARIANCE = "MINOR_VARIANCE"    # klein verschil, waarschijnlijk afronding/timing
    MISMATCH = "MISMATCH"                # echte afwijking, uitzoeken
    MISSING_PROOF = "MISSING_PROOF"      # geen onderbouwing in de documenten
    ERROR = "ERROR"                      # fout tijdens verwerken
    PENDING = "PENDING"                  # nog niet verwerkt

    @property
    def label(self) -> str:
        """Nederlandse omschrijving voor de interface."""
        return {
            "MATCH": "Akkoord",
            "MINOR_VARIANCE": "Klein verschil",
            "MISMATCH": "Afwijking",
            "MISSING_PROOF": "Geen bewijs",
            "ERROR": "Fout",
            "PENDING": "In wachtrij",
        }[self.value]


class RiskLevel(str, Enum):
    """Risiconiveau van een bevinding."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def label(self) -> str:
        """Nederlandse omschrijving voor de interface."""
        return {
            "LOW": "Laag",
            "MEDIUM": "Middel",
            "HIGH": "Hoog",
            "CRITICAL": "Kritiek",
        }[self.value]


class Aggregation(str, Enum):
    """Hoe een lijst met bewijsstukken tot een bedrag wordt herleid.

    Expliciet in de mapping vastgelegd in plaats van raden op basis van
    aanwezige attributen. Dat laatste leidde tot het vergelijken van
    hypotheekschuld met hypotheekrente.
    """
    DIRECT = "direct"                        # enkel getalveld, geen lijst
    BANK_BALANCE = "bank_balance"            # som van banksaldi
    WOZ_VALUE = "woz_value"                  # som van WOZ-waarden, naar eigendomsdeel
    MORTGAGE_DEBT = "mortgage_debt"          # som van restschulden
    MORTGAGE_INTEREST = "mortgage_interest"  # jaarrente over de restschuld


# ============================================================================
# AG-CODE MAPPING
# ============================================================================
# Zie de waarschuwing in de moduledocstring: dit is een projectconventie.

AG_CODE_MAPPING: Dict[str, Dict[str, Any]] = {

    # ---------------- Box 1: inkomen uit werk en woning ----------------

    "AG1010": {
        "name": "Bruto ondernemingsresultaat",
        "field": "business_income.gross_income_eur",
        "aggregation": Aggregation.DIRECT,
        "description": "Bruto-omzet of loon voor aftrekposten (box 1)",
        "category": "Inkomen",
    },

    "AG4010": {
        "name": "Aftrekbare ondernemingskosten",
        "field": "business_income.deductible_expenses_eur",
        "aggregation": Aggregation.DIRECT,
        "description": "Totaal aan zakelijke kosten dat in aftrek is gebracht",
        "category": "Aftrekposten",
    },

    "AG4020": {
        "name": "Kleinschaligheidsinvesteringsaftrek (KIA)",
        "field": "kia_profit_eur",
        "aggregation": Aggregation.DIRECT,
        "description": "Geclaimde KIA over de investeringen van het boekjaar",
        "category": "Aftrekposten",
    },

    "AG5010": {
        "name": "Aftrekbare hypotheekrente",
        "field": "mortgages",
        "aggregation": Aggregation.MORTGAGE_INTEREST,
        "description": "Betaalde rente eigenwoningschuld (box 1)",
        "category": "Aftrekposten",
        # Benadering wanneer het document alleen schuld en rentepercentage geeft;
        # zie _mortgage_interest voor de berekening en de beperking daarvan.
        "approximate": True,
    },

    "AG5020": {
        "name": "Overige aftrekposten",
        "field": "deductible_items_eur",
        "aggregation": Aggregation.DIRECT,
        "description": "Overige persoonsgebonden aftrek",
        "category": "Aftrekposten",
    },

    # ---------------- Box 3: sparen en beleggen ----------------

    "AG3020": {
        "name": "Bank- en spaarrekeningen",
        "field": "bank_accounts",
        "aggregation": Aggregation.BANK_BALANCE,
        "description": "Saldo van alle rekeningen per 1 januari (box 3)",
        "category": "Bezittingen",
    },

    "AG3030": {
        "name": "Onroerende zaken (niet eigen woning)",
        "field": "real_estate",
        "aggregation": Aggregation.WOZ_VALUE,
        "description": (
            "WOZ-waarde van tweede woning of verhuurd pand, naar eigendomsdeel "
            "(box 3). De eigen woning hoort in box 1 en niet onder deze code."
        ),
        "category": "Bezittingen",
    },

    "AG3050": {
        "name": "Overige bezittingen en beleggingen",
        "field": "other_assets_eur",
        "aggregation": Aggregation.DIRECT,
        "description": "Effecten, obligaties en overige beleggingen (box 3)",
        "category": "Bezittingen",
    },

    "AG3060": {
        "name": "Schulden",
        "field": "mortgages",
        "aggregation": Aggregation.MORTGAGE_DEBT,
        "description": "Restschuld van leningen per 1 januari (box 3)",
        "category": "Schulden",
    },
}


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class MatchResult(BaseModel):
    """Uitkomst van een enkele AG-code-aansluiting."""

    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    ag_code: str = Field(..., description="AG-code, bijvoorbeeld AG3020")
    ag_name: str = Field(..., description="Omschrijving van de AG-code")
    category: str = Field(default="", description="Rubriek, bijvoorbeeld Bezittingen")
    reported_amount_eur: float = Field(..., description="Aangegeven bedrag")
    extracted_amount_eur: Optional[float] = Field(
        default=None,
        description="Uit de documenten herleid bedrag, None als er geen bewijs is",
    )
    difference_eur: Optional[float] = Field(
        default=None,
        description="Aangegeven minus herleid; None als er geen bewijs is",
    )
    difference_pct: Optional[float] = Field(
        default=None, description="Verschil in procenten van het herleide bedrag"
    )
    status: AuditStatus = Field(..., description="Uitkomst van de aansluiting")
    confidence: float = Field(
        default=0.95, ge=0, le=1, description="Betrouwbaarheid van de aansluiting"
    )
    is_approximate: bool = Field(
        default=False,
        description="True als het herleide bedrag een benadering is, geen harde uitlezing",
    )
    notes: str = Field(default="", description="Toelichting voor de gebruiker")
    audit_timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def needs_attention(self) -> bool:
        """Of deze regel op het uitzonderingendashboard hoort."""
        return self.status in (
            AuditStatus.MISMATCH,
            AuditStatus.MISSING_PROOF,
            AuditStatus.ERROR,
        )

    def risk_level(self) -> RiskLevel:
        """Risiconiveau op basis van status en omvang van het verschil."""
        if self.status == AuditStatus.MATCH:
            return RiskLevel.LOW

        if self.status == AuditStatus.MINOR_VARIANCE:
            return RiskLevel.LOW

        if self.status == AuditStatus.MISMATCH:
            afwijking = abs(self.difference_eur or 0)
            if afwijking > 50_000:
                return RiskLevel.CRITICAL
            if afwijking > 10_000:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        if self.status == AuditStatus.MISSING_PROOF:
            # Een ontbrekend bewijsstuk voor een groot bedrag weegt zwaarder.
            return RiskLevel.HIGH if self.reported_amount_eur > 10_000 else RiskLevel.MEDIUM

        return RiskLevel.MEDIUM


class AuditSummary(BaseModel):
    """Samenvatting van een volledige controle.

    Let op het onderscheid tussen de drie geldbedragen. Ze meten verschillende
    dingen en mogen niet door elkaar gebruikt worden:

    - gross_difference_eur: som van de absolute verschillen. Dit is de omvang
      van het uitzoekwerk. Tegengestelde fouten heffen elkaar hier niet op.
    - net_difference_eur: som van de getekende verschillen. Dit is het effect
      op de aangifte als saldo.
    - unverified_amount_eur: aangegeven bedragen zonder onderbouwing. Onbekend,
      geen fout, dus apart gehouden.
    """

    model_config = ConfigDict(strict=True)

    total_ag_codes_checked: int = Field(..., description="Aantal gecontroleerde codes")
    matched: int = Field(..., description="Aantal dat aansluit")
    minor_variance: int = Field(..., description="Aantal met klein verschil")
    mismatched: int = Field(..., description="Aantal met echte afwijking")
    missing_proof: int = Field(..., description="Aantal zonder onderbouwing")
    errors: int = Field(..., description="Aantal verwerkingsfouten")

    gross_difference_eur: float = Field(
        ..., description="Som van absolute verschillen, exclusief ontbrekend bewijs"
    )
    net_difference_eur: float = Field(
        ..., description="Som van getekende verschillen, exclusief ontbrekend bewijs"
    )
    unverified_amount_eur: float = Field(
        ..., description="Som van aangegeven bedragen zonder onderbouwing"
    )

    overall_risk_level: RiskLevel = Field(..., description="Hoogste risico in het dossier")
    audit_timestamp: datetime = Field(default_factory=datetime.now)
    duration_seconds: float = Field(default=0, description="Doorlooptijd in seconden")

    @property
    def match_rate(self) -> float:
        """Percentage dat aansluit, inclusief kleine afrondingsverschillen.

        Kleine verschillen tellen mee als aangesloten: ze vragen geen actie.
        Wie de strikte variant wil, gebruikt exact_match_rate.
        """
        if self.total_ag_codes_checked == 0:
            return 0.0
        return ((self.matched + self.minor_variance) / self.total_ag_codes_checked) * 100

    @property
    def exact_match_rate(self) -> float:
        """Percentage dat exact aansluit, zonder kleine verschillen."""
        if self.total_ag_codes_checked == 0:
            return 0.0
        return (self.matched / self.total_ag_codes_checked) * 100

    @property
    def needs_attention_count(self) -> int:
        """Aantal regels dat handmatig uitzoekwerk vraagt."""
        return self.mismatched + self.missing_proof + self.errors


# ============================================================================
# MATCHER
# ============================================================================

class AuditMatcher:
    """Deterministische aansluitmotor.

    Vergelijkt aangegeven bedragen met uitgelezen brondocumenten.

    Voorbeeld:
        >>> matcher = AuditMatcher()
        >>> resultaten, samenvatting = matcher.match_ag_codes(
        ...     extracted_data=data,
        ...     reported_amounts={"AG3020": 50000},
        ... )
    """

    # Een aangifte gaat in hele euro's, dus een verschil tot en met EUR 1 is
    # afronding en geen bevinding. Zonder deze marge wordt elk afrondingsverschil
    # een rode regel en verdrinkt het echte werk in ruis.
    ROUNDING_TOLERANCE_EUR = 1.00

    # Daarboven: klein verschil zolang het zowel absoluut als relatief klein is.
    MINOR_VARIANCE_THRESHOLD_EUR = 100.00
    VARIANCE_THRESHOLD_PCT = 2.0

    def __init__(self) -> None:
        logger.info("AuditMatcher gestart (zuiver Python, geen AI)")

    # ---------------------- waardebepaling per bewijsstuk ----------------------

    @staticmethod
    def _woz_value(item: Any) -> float:
        """WOZ-waarde naar eigendomsdeel.

        Bij gedeeld eigendom hoort alleen het eigen aandeel in de aangifte.
        De volle WOZ-waarde nemen levert bij 50% eigendom een factor 2 fout op.
        """
        waarde = float(getattr(item, "woz_value_eur", 0.0))
        deel = float(getattr(item, "ownership_pct", 100.0))
        return waarde * deel / 100.0

    @staticmethod
    def _mortgage_interest(item: Any) -> float:
        """Jaarrente over een lening.

        Voorkeur: het bedrag dat de jaaropgave zelf noemt. Ontbreekt dat, dan
        wordt het benaderd als restschuld maal rentepercentage. Die benadering
        overschat bij een annuitaire of lineaire lening, omdat de schuld in de
        loop van het jaar daalt. Daarom wordt de regel als benadering gemarkeerd
        en niet als harde uitlezing gepresenteerd.
        """
        gerapporteerd = getattr(item, "annual_interest_paid_eur", None)
        if gerapporteerd is not None:
            return float(gerapporteerd)

        schuld = float(getattr(item, "current_balance_eur", 0.0))
        percentage = float(getattr(item, "interest_rate_pct", 0.0))
        return schuld * percentage / 100.0

    def _aggregate(self, items: List[Any], how: Aggregation) -> float:
        """Herleid een lijst bewijsstukken tot een bedrag."""
        if how == Aggregation.BANK_BALANCE:
            return float(sum(getattr(i, "balance_eur", 0.0) for i in items))
        if how == Aggregation.WOZ_VALUE:
            return float(sum(self._woz_value(i) for i in items))
        if how == Aggregation.MORTGAGE_DEBT:
            return float(sum(getattr(i, "current_balance_eur", 0.0) for i in items))
        if how == Aggregation.MORTGAGE_INTEREST:
            return float(sum(self._mortgage_interest(i) for i in items))
        raise ValueError(f"Aggregatie {how} is niet geldig voor een lijst")

    # ---------------------- veldextractie ----------------------

    def _extract_field_value(
        self,
        data: ExtractedFinancialData,
        field_path: str,
        how: Aggregation,
    ) -> Optional[float]:
        """Herleid het bedrag voor een AG-code uit de uitgelezen data.

        Onderscheidt bewust twee gevallen die eerder allebei op None uitkwamen:
        een lege lijst betekent geen bewijs (None), een gevulde lijst die op
        nul uitkomt is wel bewijs van een nulstand (0.0). Dat verschil bepaalt
        of iets als 'geen bewijs' of als 'sluit aan' op het dashboard komt.

        Returns:
            Het bedrag, of None als er geen onderbouwing is.
        """
        try:
            current: Any = data
            for part in field_path.split("."):
                if current is None or not hasattr(current, part):
                    logger.debug("Veld niet aanwezig: %s", field_path)
                    return None
                current = getattr(current, part)

            if current is None:
                return None

            if isinstance(current, list):
                if not current:
                    return None  # geen enkel bewijsstuk aangetroffen
                return self._aggregate(current, how)

            # bool is een subtype van int; hier nooit een bedrag
            if isinstance(current, bool):
                return None

            if isinstance(current, (int, float)):
                return float(current)

            logger.debug("Geen bedrag te herleiden uit %s (%s)", field_path, type(current))
            return None

        except Exception as exc:
            logger.error("Fout bij uitlezen van %s: %s", field_path, exc)
            return None

    # ---------------------- vergelijking ----------------------

    @staticmethod
    def _calculate_difference(reported: float, extracted: float) -> Tuple[float, float]:
        """Bereken het getekende verschil en het percentage.

        Returns:
            (getekend verschil, percentage van het herleide bedrag)
            Positief verschil betekent dat er te veel is aangegeven.
        """
        verschil = round(reported - extracted, 2)

        if extracted == 0:
            percentage = 0.0 if verschil == 0 else 100.0
        else:
            percentage = abs(verschil) / abs(extracted) * 100

        return verschil, round(percentage, 2)

    def _determine_status(self, difference_eur: float, difference_pct: float) -> AuditStatus:
        """Bepaal de status op basis van het verschil.

        - tot en met EUR 1: afronding, sluit aan
        - daarboven en zowel onder EUR 100 als onder 2%: klein verschil
        - anders: afwijking
        """
        afwijking = abs(difference_eur)

        if afwijking <= self.ROUNDING_TOLERANCE_EUR:
            return AuditStatus.MATCH

        if (
            afwijking <= self.MINOR_VARIANCE_THRESHOLD_EUR
            and difference_pct <= self.VARIANCE_THRESHOLD_PCT
        ):
            return AuditStatus.MINOR_VARIANCE

        return AuditStatus.MISMATCH

    def match_single_ag_code(
        self,
        ag_code: str,
        reported_amount_eur: float,
        extracted_data: ExtractedFinancialData,
    ) -> MatchResult:
        """Sluit een enkele AG-code aan op de brondocumenten."""
        try:
            mapping = AG_CODE_MAPPING.get(ag_code)

            if mapping is None:
                return MatchResult(
                    ag_code=ag_code,
                    ag_name="Onbekende code",
                    reported_amount_eur=float(reported_amount_eur),
                    status=AuditStatus.ERROR,
                    confidence=0.0,
                    notes=f"AG-code {ag_code} staat niet in de codetabel",
                )

            extracted_value = self._extract_field_value(
                extracted_data, mapping["field"], mapping["aggregation"]
            )

            if extracted_value is None:
                return MatchResult(
                    ag_code=ag_code,
                    ag_name=mapping["name"],
                    category=mapping.get("category", ""),
                    reported_amount_eur=float(reported_amount_eur),
                    extracted_amount_eur=None,
                    difference_eur=None,
                    status=AuditStatus.MISSING_PROOF,
                    confidence=0.0,
                    notes=(
                        f"Geen onderbouwing gevonden voor {mapping['name'].lower()}. "
                        "Upload het bijbehorende brondocument."
                    ),
                )

            verschil, percentage = self._calculate_difference(
                float(reported_amount_eur), extracted_value
            )
            status = self._determine_status(verschil, percentage)
            benadering = bool(mapping.get("approximate", False))

            toelichting = mapping["description"]
            if benadering and status != AuditStatus.MATCH:
                toelichting += (
                    " Let op: het herleide bedrag is een benadering op basis van "
                    "restschuld en rentepercentage. Controleer de jaaropgave."
                )

            result = MatchResult(
                ag_code=ag_code,
                ag_name=mapping["name"],
                category=mapping.get("category", ""),
                reported_amount_eur=float(reported_amount_eur),
                extracted_amount_eur=extracted_value,
                difference_eur=verschil,
                difference_pct=percentage,
                status=status,
                confidence=0.70 if benadering else (0.95 if status == AuditStatus.MATCH else 0.85),
                is_approximate=benadering,
                notes=toelichting,
            )

            logger.info(
                "%s: %s (aangegeven EUR %s, herleid EUR %s, verschil EUR %s)",
                ag_code,
                status.value,
                f"{reported_amount_eur:,.2f}",
                f"{extracted_value:,.2f}",
                f"{verschil:,.2f}",
            )
            return result

        except Exception as exc:
            logger.error("Fout bij aansluiten van %s: %s", ag_code, exc)
            return MatchResult(
                ag_code=ag_code,
                ag_name="Fout",
                reported_amount_eur=float(reported_amount_eur),
                status=AuditStatus.ERROR,
                confidence=0.0,
                notes=f"Onverwachte fout tijdens de aansluiting: {exc}",
            )

    def match_ag_codes(
        self,
        extracted_data: ExtractedFinancialData,
        reported_amounts: Dict[str, float],
    ) -> Tuple[List[MatchResult], AuditSummary]:
        """Sluit meerdere AG-codes aan en stel de samenvatting op."""
        start = time.perf_counter()
        logger.info("Start aansluiting voor %d AG-codes", len(reported_amounts))

        results = [
            self.match_single_ag_code(code, amount, extracted_data)
            for code, amount in reported_amounts.items()
        ]

        # Alleen regels met een daadwerkelijk verschil tellen mee in de bedragen.
        # Ontbrekend bewijs is onbekend, geen fout, en wordt apart getoond.
        verschillen = [r.difference_eur for r in results if r.difference_eur is not None]

        summary = AuditSummary(
            total_ag_codes_checked=len(results),
            matched=sum(1 for r in results if r.status == AuditStatus.MATCH),
            minor_variance=sum(1 for r in results if r.status == AuditStatus.MINOR_VARIANCE),
            mismatched=sum(1 for r in results if r.status == AuditStatus.MISMATCH),
            missing_proof=sum(1 for r in results if r.status == AuditStatus.MISSING_PROOF),
            errors=sum(1 for r in results if r.status == AuditStatus.ERROR),
            gross_difference_eur=round(sum(abs(d) for d in verschillen), 2),
            net_difference_eur=round(sum(verschillen), 2),
            unverified_amount_eur=round(
                sum(
                    r.reported_amount_eur
                    for r in results
                    if r.status == AuditStatus.MISSING_PROOF
                ),
                2,
            ),
            overall_risk_level=self._determine_overall_risk(results),
            duration_seconds=round(time.perf_counter() - start, 3),
        )

        logger.info(
            "Aansluiting klaar. %d/%d sluit aan. Bruto afwijking EUR %s, "
            "netto EUR %s, niet verifieerbaar EUR %s. Risico %s. Duur %.2fs",
            summary.matched + summary.minor_variance,
            summary.total_ag_codes_checked,
            f"{summary.gross_difference_eur:,.2f}",
            f"{summary.net_difference_eur:,.2f}",
            f"{summary.unverified_amount_eur:,.2f}",
            summary.overall_risk_level.value,
            summary.duration_seconds,
        )

        return results, summary

    @staticmethod
    def _determine_overall_risk(results: List[MatchResult]) -> RiskLevel:
        """Het hoogste individuele risico bepaalt het dossierrisico."""
        if not results:
            return RiskLevel.LOW

        niveaus = [r.risk_level() for r in results]
        for niveau in (RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM):
            if niveau in niveaus:
                return niveau
        return RiskLevel.LOW

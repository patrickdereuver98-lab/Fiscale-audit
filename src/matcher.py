"""
FiscAudit AI - Aansluitingsmotor (matcher)

Zuiver Python, deterministisch, geen AI. Vergelijkt de aangegeven bedragen per
AG-code met wat uit de brondocumenten is uitgelezen. Reproduceerbaar en
auditeerbaar: dezelfde invoer geeft altijd dezelfde uitkomst.

Codeconventie: identifiers en docstrings zijn Engels (standaard voor Python),
alle teksten die de gebruiker ziet zijn Nederlands.

De posten en de herleiding uit de brondocumenten staan in posten.py. Deze
module bevat alleen de vergelijking en de drempels; welke post waar uit volgt is
daar vastgelegd, zodat er een plek is waar dat gewijzigd wordt.
"""

import logging
import time
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

# AuditStatus en RiskLevel komen uit domain.py, zodat er één definitie is.
# Ze worden hier opnieuw geexporteerd omdat bestaande code ze uit matcher
# importeert.
from .domain import AuditStatus, RiskLevel
from .extractor import ExtractedFinancialData
from .posten import POSTEN, Post


logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

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
        return self.status.needs_attention

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

    def match_single_post(
        self,
        post_key: str,
        reported_amount_eur: float,
        extracted_data: ExtractedFinancialData,
    ) -> MatchResult:
        """Sluit een enkele aangiftepost aan op de brondocumenten.

        De herleiding uit de documenten komt uit posten.py. Die stond hier
        eerder ook, met een eigen AG-codetabel; twee plekken met dezelfde
        logica liepen uit elkaar zodra er een post bij kwam.
        """
        try:
            post: Optional[Post] = POSTEN.get(post_key)

            if post is None:
                return MatchResult(
                    ag_code=post_key,
                    ag_name="Onbekende post",
                    reported_amount_eur=float(reported_amount_eur),
                    status=AuditStatus.ERROR,
                    confidence=0.0,
                    notes=(
                        f"Post {post_key!r} staat niet in de postentabel en is "
                        "niet gecontroleerd. Vul src/posten.py aan."
                    ),
                )

            try:
                uit_documenten = post.herleiden(extracted_data)
            except Exception as exc:
                logger.error("Herleiden van %s mislukt: %s", post_key, exc)
                uit_documenten = None

            if uit_documenten is None:
                return MatchResult(
                    ag_code=post_key,
                    ag_name=post.naam,
                    category=post.soort.label,
                    reported_amount_eur=float(reported_amount_eur),
                    extracted_amount_eur=None,
                    difference_eur=None,
                    status=AuditStatus.MISSING_PROOF,
                    confidence=0.0,
                    notes=(
                        f"Geen onderbouwing gevonden voor {post.naam.lower()}. "
                        "Het bijbehorende stuk ontbreekt in het dossier."
                    ),
                )

            verschil, percentage = self._calculate_difference(
                float(reported_amount_eur), uit_documenten
            )
            status = self._determine_status(verschil, percentage)

            toelichting = post.toelichting
            if post.is_benadering and status != AuditStatus.MATCH:
                toelichting += (
                    " Let op: het bedrag uit de stukken is een benadering. "
                    "Controleer de jaaropgave."
                )

            result = MatchResult(
                ag_code=post_key,
                ag_name=post.naam,
                category=post.soort.label,
                reported_amount_eur=float(reported_amount_eur),
                extracted_amount_eur=uit_documenten,
                difference_eur=verschil,
                difference_pct=percentage,
                status=status,
                confidence=(
                    0.70 if post.is_benadering
                    else (0.95 if status == AuditStatus.MATCH else 0.85)
                ),
                is_approximate=post.is_benadering,
                notes=toelichting,
            )

            logger.info(
                "%s: %s (aangifte EUR %s, stukken EUR %s, verschil EUR %s)",
                post_key, status.value,
                f"{reported_amount_eur:,.2f}", f"{uit_documenten:,.2f}",
                f"{verschil:,.2f}",
            )
            return result

        except Exception as exc:
            logger.error("Aansluiten van %s mislukt: %s", post_key, exc)
            return MatchResult(
                ag_code=post_key,
                ag_name="Fout",
                reported_amount_eur=float(reported_amount_eur),
                status=AuditStatus.ERROR,
                confidence=0.0,
                notes=f"Onverwachte fout tijdens de aansluiting: {exc}",
            )

    # Oude naam, zodat bestaande aanroepen blijven werken.
    match_single_ag_code = match_single_post

    def match_ag_codes(
        self,
        extracted_data: ExtractedFinancialData,
        reported_amounts: Dict[str, float],
    ) -> Tuple[List[MatchResult], AuditSummary]:
        """Sluit meerdere AG-codes aan en stel de samenvatting op."""
        start = time.perf_counter()
        logger.info("Start aansluiting voor %d AG-codes", len(reported_amounts))

        results = [
            self.match_single_post(post_key, amount, extracted_data)
            for post_key, amount in reported_amounts.items()
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

        return RiskLevel.highest(r.risk_level() for r in results)

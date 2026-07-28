"""
FiscAudit AI - Inhoudelijke weging (advisor)

Neemt de uitkomst van de cijfermatige aansluiting en laat Claude wegen wat de
bevindingen betekenen: wat moet worden uitgezocht, welk stuk moet worden
opgevraagd, waar zit het risico. De cijfers zelf komen uit matcher.py en worden
hier niet herrekend.

Opzet:
  - Eén modelaanroep, uitsluitend voor de analyse.
  - Het bericht aan de klant wordt daarna in Python opgebouwd uit de analyse
    plus de cijfers van de matcher. Zo staat er geen enkel bedrag in de tekst
    naar de klant dat een taalmodel heeft bedacht.
  - Faalt de aanroep, dan is dat zichtbaar. Er wordt geen vervangende
    inschatting verzonnen.

WAT DEZE MODULE NIET DOET
Er staan geen tarieven, drempels of vrijstellingen in deze code. Die wijzigen
jaarlijks en een verouderd of verzonnen bedrag in een fiscaal advies is
schadelijker dan een ontbrekend bedrag. De vorige versie bevatte hier
onjuistheden (waaronder een niet-bestaand woord voor de KIA en een verzonnen
giftendrempel), die het model richting verkeerde conclusies duwden.

Wil je dat de analyse naar concrete regelgeving verwijst, geef dan
referentiemateriaal mee via de parameter `reference_material`. Zonder dat
materiaal wordt het model opgedragen geen wetsartikelen te noemen, omdat het
die anders plausibel maar onjuist verzint.
"""

import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from anthropic import Anthropic

from .domain import RiskLevel, AuditStatus
from .llm_json import extract_json_object, JsonExtractionError
from .matcher import MatchResult, AuditSummary


logger = logging.getLogger(__name__)


# ============================================================================
# UITKOMSTEN
# ============================================================================

@dataclass
class RiskPoint:
    """Eén bevinding uit de inhoudelijke weging."""

    titel: str
    beschrijving: str
    impact: RiskLevel
    aanbevolen_actie: str
    ag_codes: List[str] = field(default_factory=list)
    referentie: str = ""


@dataclass
class RiskAssessment:
    """Uitkomst van de inhoudelijke weging.

    `analysis_available` is False wanneer de modelaanroep is mislukt. In dat
    geval staat de reden in `failure_reason` en zijn de overige velden leeg.
    De interface hoort dat als 'geen analyse beschikbaar' te tonen en niet als
    een inschatting, want een verzonnen middenwaarde leest als een bevinding.
    """

    overall_risk: RiskLevel
    analysis_available: bool = True
    failure_reason: str = ""
    risico_punten: List[RiskPoint] = field(default_factory=list)
    sterke_punten: List[str] = field(default_factory=list)
    waarschuwingen: List[str] = field(default_factory=list)
    aanbevelingen: List[str] = field(default_factory=list)
    ontbrekende_stukken: List[str] = field(default_factory=list)
    klant_email_concept: str = ""
    model: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Platte weergave, geschikt voor opslag en export."""
        gegevens = asdict(self)
        gegevens["overall_risk"] = self.overall_risk.value
        for punt, bron in zip(gegevens["risico_punten"], self.risico_punten):
            punt["impact"] = bron.impact.value
        return gegevens


# ============================================================================
# ADVISEUR
# ============================================================================

class FiscalAdvisor:
    """Weegt de bevindingen van de aansluiting inhoudelijk."""

    MAX_RETRIES = 3
    RETRY_BACKOFF_SECONDS = 2
    MAX_TOKENS = 4000

    # Temperatuur op 0: bij dezelfde bevindingen hoort dezelfde weging. Een
    # controle die twee keer een ander antwoord geeft is niet auditeerbaar.
    TEMPERATURE = 0.0

    SYSTEM_PROMPT_BASE = """Je ondersteunt een Nederlandse assistent-accountant bij de
controle van een belastingaangifte. De cijfermatige aansluiting is al gedaan door
een deterministisch programma. Jouw taak is die uitkomst wegen, niet herrekenen.

WAT JE KRIJGT
Per AG-code het aangegeven bedrag, het uit de brondocumenten herleide bedrag en
de status. Alleen de posten die aandacht vragen worden uitgewerkt; posten die
aansluiten zijn samengevat in een aantal.

WAT JE DOET
1. Benoem per bevinding de waarschijnlijke oorzaak. Onderscheid daarbij een
   invoerfout, een tijdsverschil, een onvolledig dossier en een inhoudelijk
   fiscaal punt. Dat onderscheid bepaalt de vervolgactie.
2. Zeg concreet welk stuk moet worden opgevraagd of welke boeking moet worden
   nagekeken. "Nader onderzoeken" is geen actie.
3. Weeg de zwaarte naar het bedrag en de aard, niet naar het aantal regels.
4. Noem het wanneer een aftrekpost of vrijstelling gemist lijkt te zijn. Een
   te hoog aangegeven bezitting en een gemiste aftrek zijn beide relevant.

WAT JE NIET DOET
- Geen bedragen berekenen of herhalen die niet in de opgave staan.
- Geen tarieven, drempels of vrijstellingsbedragen noemen. Je kent het
  actuele jaar niet met zekerheid en een verkeerd bedrag is hier schadelijk.
- Geen wetsartikelen of besluiten noemen tenzij die letterlijk in het
  meegegeven referentiemateriaal staan. Laat "referentie" anders leeg.
- Geen conclusie over de aanvaardbaarheid van de aangifte als geheel. Je
  signaleert; de accountant beslist.

TOON
Zakelijk en beknopt, gericht aan een vakgenoot. Nederlands.

UITVOER
Uitsluitend één geldig JSON-object, zonder codeblok en zonder begeleidende tekst:
{
  "overall_risk": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "risico_punten": [
    {
      "titel": "korte aanduiding",
      "beschrijving": "wat er aan de hand is en wat de vermoedelijke oorzaak is",
      "impact": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
      "aanbevolen_actie": "concrete vervolgstap",
      "ag_codes": ["AG3020"],
      "referentie": ""
    }
  ],
  "sterke_punten": ["wat goed is onderbouwd"],
  "waarschuwingen": ["waar de controle zelf beperkt is"],
  "aanbevelingen": ["vervolgstappen op dossierniveau"],
  "ontbrekende_stukken": ["op te vragen document"]
}"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        reference_material: Optional[str] = None,
    ) -> None:
        """
        Args:
            api_key: Anthropic-sleutel.
            model: Modelnaam.
            reference_material: Optionele fiscale bronteksten. Alleen wanneer
                dit is meegegeven mag de analyse naar regelgeving verwijzen.
        """
        self.model = model
        self.reference_material = reference_material
        self.client = Anthropic(api_key=api_key)
        logger.info("FiscalAdvisor gestart met model %s (referentiemateriaal: %s)",
                    model, "ja" if reference_material else "nee")

    # ---------------------- systeemprompt ----------------------

    def _system_prompt(self) -> str:
        """Systeemprompt, aangevuld met referentiemateriaal als dat er is."""
        if not self.reference_material:
            return self.SYSTEM_PROMPT_BASE

        return (
            self.SYSTEM_PROMPT_BASE
            + "\n\nREFERENTIEMATERIAAL\nJe mag uitsluitend naar het onderstaande "
              "verwijzen. Staat een punt hier niet in, laat \"referentie\" dan leeg.\n\n"
            + self.reference_material
        )

    # ---------------------- opgave voor het model ----------------------

    @staticmethod
    def _format_amount(value: Optional[float]) -> str:
        """Bedrag in Nederlandse notatie, of een streepje als het onbekend is."""
        if value is None:
            return "onbekend"
        getal = f"{abs(value):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
        return f"{'-' if value < 0 else ''}EUR {getal}"

    def _build_briefing(
        self,
        results: List[MatchResult],
        summary: AuditSummary,
        document_type: Optional[str],
        klant_naam: str,
        aangiftejaar: int,
    ) -> str:
        """Stel een compacte opgave op.

        De vorige versie stuurde dezelfde gegevens drie keer mee: de volledige
        uitgelezen data, een tekstuele opsomming van de afwijkingen, en nog eens
        alle resultaten als JSON. Daarmee verdween het signaal in de ruis en
        werd de aanroep onnodig groot. Hier gaan alleen de posten mee die
        aandacht vragen; de rest is samengevat in aantallen.
        """
        uitzonderingen = [r for r in results if r.status.needs_attention]
        aansluitend = [r for r in results if not r.status.needs_attention]

        regels: List[str] = [
            f"DOSSIER: {klant_naam or 'niet ingevuld'}, aangiftejaar {aangiftejaar}",
            f"BRONDOCUMENT: {document_type or 'niet vastgesteld'}",
            "",
            "OMVANG VAN DE CONTROLE",
            f"- gecontroleerde AG-codes: {summary.total_ag_codes_checked}",
            f"- sluiten aan: {summary.matched}"
            f" (plus {summary.minor_variance} met een klein verschil)",
            f"- vragen aandacht: {summary.needs_attention_count}",
            "",
            "BEDRAGEN",
            f"- bruto afwijking, som van de absolute verschillen: "
            f"{self._format_amount(summary.gross_difference_eur)}",
            f"- saldo-effect op de aangifte: "
            f"{self._format_amount(summary.net_difference_eur)}",
            f"- aangegeven zonder onderbouwing: "
            f"{self._format_amount(summary.unverified_amount_eur)}",
            "",
        ]

        if not uitzonderingen:
            regels.append("BEVINDINGEN: geen. Alle gecontroleerde posten sluiten aan.")
        else:
            regels.append("POSTEN DIE AANDACHT VRAGEN")
            for r in sorted(uitzonderingen,
                            key=lambda x: -abs(x.difference_eur or x.reported_amount_eur)):
                regels.append(
                    f"- {r.ag_code} {r.ag_name} ({r.category or 'geen rubriek'})"
                )
                regels.append(f"    status: {r.status.label}")
                regels.append(
                    f"    aangegeven: {self._format_amount(r.reported_amount_eur)}"
                    f" | uit document: {self._format_amount(r.extracted_amount_eur)}"
                    f" | verschil: {self._format_amount(r.difference_eur)}"
                )
                if r.is_approximate:
                    regels.append(
                        "    let op: het bedrag uit het document is een benadering, "
                        "geen harde uitlezing"
                    )
                if r.notes:
                    regels.append(f"    toelichting bij de post: {r.notes}")

        if aansluitend:
            codes = ", ".join(r.ag_code for r in aansluitend)
            regels += ["", f"SLUITEN AAN, GEEN ACTIE: {codes}"]

        betrouwbaarheid = [
            r.ag_code for r in results
            if r.confidence < 0.8 and r.status != AuditStatus.MISSING_PROOF
        ]
        if betrouwbaarheid:
            regels += [
                "",
                "BEPERKING VAN DE CONTROLE",
                f"- lagere betrouwbaarheid bij: {', '.join(betrouwbaarheid)}",
            ]

        regels += ["", "Geef uitsluitend het JSON-object terug."]
        return "\n".join(regels)

    # ---------------------- modelaanroep ----------------------

    def _call_model(self, system_prompt: str, briefing: str) -> str:
        """Roep het model aan, met herhaalpogingen bij tijdelijke fouten."""
        laatste_fout: Optional[Exception] = None

        for poging in range(1, self.MAX_RETRIES + 1):
            try:
                antwoord = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.MAX_TOKENS,
                    temperature=self.TEMPERATURE,
                    system=system_prompt,
                    messages=[{"role": "user", "content": briefing}],
                )
                return antwoord.content[0].text

            except Exception as exc:
                laatste_fout = exc
                if poging < self.MAX_RETRIES:
                    wachttijd = self.RETRY_BACKOFF_SECONDS ** poging
                    logger.warning(
                        "Analyse-aanroep mislukt (poging %d van %d): %s. "
                        "Nieuwe poging over %ds",
                        poging, self.MAX_RETRIES, exc, wachttijd,
                    )
                    time.sleep(wachttijd)

        raise RuntimeError(
            f"De analyse-aanroep is na {self.MAX_RETRIES} pogingen mislukt: {laatste_fout}"
        )

    # ---------------------- hoofdingang ----------------------

    def analyze_audit(
        self,
        results: List[MatchResult],
        summary: AuditSummary,
        extracted_data: Optional[Dict[str, Any]] = None,
        klant_naam: str = "",
        aangiftejaar: int = 0,
    ) -> RiskAssessment:
        """Weeg de bevindingen en stel het conceptbericht op.

        Args:
            results: Uitkomsten per AG-code uit de matcher.
            summary: Samenvatting uit de matcher.
            extracted_data: Uitgelezen documentgegevens. Hiervan wordt alleen
                het documenttype gebruikt. De bedragen zitten al in `results`;
                de volledige gegevens meesturen voegt niets toe en zou
                rekeningnummers naar een externe partij sturen.
            klant_naam: Voor het conceptbericht.
            aangiftejaar: Voor het conceptbericht.

        Returns:
            RiskAssessment. Bij een mislukte aanroep is `analysis_available`
            False en staat de reden in `failure_reason`.
        """
        document_type = None
        if extracted_data:
            document_type = extracted_data.get("document_type")

        briefing = self._build_briefing(
            results, summary, document_type, klant_naam, aangiftejaar
        )

        try:
            ruw = self._call_model(self._system_prompt(), briefing)
        except Exception as exc:
            logger.error("Inhoudelijke weging niet uitgevoerd: %s", exc)
            return self._no_analysis(summary, str(exc), klant_naam, aangiftejaar, results)

        try:
            gegevens = extract_json_object(ruw, context="analyse-antwoord")
        except JsonExtractionError as exc:
            logger.error("Antwoord op de analyse was geen JSON: %s", exc)
            return self._no_analysis(
                summary, "het model gaf geen bruikbaar antwoord",
                klant_naam, aangiftejaar, results,
            )

        beoordeling = self._parse_assessment(gegevens, summary)

        # Het bericht aan de klant wordt hier opgebouwd, niet door het model.
        # Zo kan er geen bedrag in de klantcommunicatie staan dat niet uit de
        # aansluiting komt.
        beoordeling.klant_email_concept = build_client_email(
            beoordeling, summary, results, klant_naam, aangiftejaar
        )
        return beoordeling

    # ---------------------- verwerking van het antwoord ----------------------

    def _parse_assessment(
        self, gegevens: Dict[str, Any], summary: AuditSummary
    ) -> RiskAssessment:
        """Zet het JSON-antwoord om naar een RiskAssessment."""
        punten: List[RiskPoint] = []
        for ruw_punt in gegevens.get("risico_punten") or []:
            if not isinstance(ruw_punt, dict):
                continue
            punten.append(
                RiskPoint(
                    titel=str(ruw_punt.get("titel", "")).strip() or "Zonder titel",
                    beschrijving=str(ruw_punt.get("beschrijving", "")).strip(),
                    impact=self._parse_risk(ruw_punt.get("impact"), summary),
                    aanbevolen_actie=str(ruw_punt.get("aanbevolen_actie", "")).strip(),
                    ag_codes=[str(c) for c in (ruw_punt.get("ag_codes") or [])],
                    referentie=(
                        str(ruw_punt.get("referentie", "")).strip()
                        if self.reference_material else ""
                    ),
                )
            )

        return RiskAssessment(
            overall_risk=self._parse_risk(gegevens.get("overall_risk"), summary),
            analysis_available=True,
            risico_punten=punten,
            sterke_punten=self._string_list(gegevens.get("sterke_punten")),
            waarschuwingen=self._string_list(gegevens.get("waarschuwingen")),
            aanbevelingen=self._string_list(gegevens.get("aanbevelingen")),
            ontbrekende_stukken=self._string_list(gegevens.get("ontbrekende_stukken")),
            model=self.model,
        )

    @staticmethod
    def _string_list(waarde: Any) -> List[str]:
        """Maak een lijst met tekstregels, ongeacht wat het model teruggaf."""
        if not waarde:
            return []
        if isinstance(waarde, str):
            return [waarde.strip()] if waarde.strip() else []
        return [str(item).strip() for item in waarde if str(item).strip()]

    @staticmethod
    def _parse_risk(waarde: Any, summary: AuditSummary) -> RiskLevel:
        """Zet een risiconiveau om.

        Valt terug op het niveau dat de matcher zelf al deterministisch heeft
        vastgesteld, in plaats van op een vaste middenwaarde. Dat niveau is
        gebaseerd op de werkelijke bedragen en is dus een betere schatting dan
        MEDIUM wanneer het model iets onverwachts teruggeeft.
        """
        try:
            return RiskLevel(str(waarde).strip().upper())
        except (ValueError, AttributeError):
            logger.warning(
                "Onbekend risiconiveau %r; het niveau uit de aansluiting (%s) wordt gebruikt",
                waarde, summary.overall_risk_level.value,
            )
            return summary.overall_risk_level

    def _no_analysis(
        self,
        summary: AuditSummary,
        reden: str,
        klant_naam: str,
        aangiftejaar: int,
        results: List[MatchResult],
    ) -> RiskAssessment:
        """Uitkomst wanneer de weging niet is gelukt.

        Neemt bewust het risiconiveau van de matcher over en zet
        analysis_available op False. De vorige versie gaf hier MEDIUM terug met
        "Audit proces succesvol afgerond" als sterk punt, waardoor een mislukte
        aanroep niet te onderscheiden was van een echte beoordeling.
        """
        beoordeling = RiskAssessment(
            overall_risk=summary.overall_risk_level,
            analysis_available=False,
            failure_reason=reden,
            waarschuwingen=[
                "De inhoudelijke weging is niet uitgevoerd. De cijfermatige "
                "aansluiting hieronder is wel volledig en betrouwbaar; alleen de "
                "toelichting per bevinding ontbreekt.",
            ],
            model=self.model,
        )
        beoordeling.klant_email_concept = build_client_email(
            beoordeling, summary, results, klant_naam, aangiftejaar
        )
        return beoordeling


# ============================================================================
# CONCEPTBERICHT
# ============================================================================

def build_client_email(
    assessment: RiskAssessment,
    summary: AuditSummary,
    results: List[MatchResult],
    klant_naam: str,
    aangiftejaar: int,
) -> str:
    """Stel het conceptbericht aan de klant op.

    Bewust in Python en niet door het model. De bedragen en aantallen komen
    rechtstreeks uit de aansluiting, zodat er geen door een taalmodel bedacht
    bedrag in een bericht aan een klant terecht kan komen. De inhoudelijke
    toelichting komt uit de analyse, de cijfers uit de matcher.
    """
    def bedrag(waarde: Optional[float]) -> str:
        if waarde is None:
            return "onbekend"
        getal = f"{abs(waarde):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
        return f"{'-' if waarde < 0 else ''}€ {getal}"

    aanhef = f"Geachte {klant_naam}," if klant_naam else "Geachte heer, mevrouw,"
    jaar = str(aangiftejaar) if aangiftejaar else "het betreffende jaar"

    regels = [
        aanhef,
        "",
        f"Wij hebben de aangifte over {jaar} vergeleken met de door u aangeleverde "
        f"stukken. Hieronder de uitkomst.",
        "",
        f"Van de {summary.total_ag_codes_checked} gecontroleerde posten sluiten er "
        f"{summary.matched + summary.minor_variance} aan op de onderliggende stukken.",
    ]

    if summary.needs_attention_count == 0:
        regels += [
            "",
            "Er zijn geen verschillen gevonden die navraag vragen. Wij ronden het "
            "dossier af en nemen contact op zodra de aangifte kan worden ingediend.",
        ]
    else:
        regels += [
            f"Voor {summary.needs_attention_count} posten hebben wij een vraag.",
        ]

        afwijkingen = [r for r in results if r.status == AuditStatus.MISMATCH]
        if afwijkingen:
            regels += ["", "Verschillen tussen de aangifte en de stukken:"]
            for r in sorted(afwijkingen, key=lambda x: -abs(x.difference_eur or 0)):
                regels.append(
                    f"- {r.ag_name}: in de aangifte {bedrag(r.reported_amount_eur)}, "
                    f"volgens de stukken {bedrag(r.extracted_amount_eur)} "
                    f"(verschil {bedrag(r.difference_eur)})."
                )

        ontbrekend = [r for r in results if r.status == AuditStatus.MISSING_PROOF]
        if ontbrekend:
            regels += ["", "Voor de volgende posten ontbreekt nog een onderbouwing:"]
            for r in sorted(ontbrekend, key=lambda x: -x.reported_amount_eur):
                regels.append(
                    f"- {r.ag_name}: {bedrag(r.reported_amount_eur)} aangegeven."
                )

        if assessment.ontbrekende_stukken:
            regels += ["", "Wij verzoeken u de volgende stukken aan te leveren:"]
            regels += [f"- {stuk}" for stuk in assessment.ontbrekende_stukken]

        regels += [
            "",
            "Wij verzoeken u de bovenstaande punten na te gaan. Een verschil komt "
            "vaak door een ontbrekend stuk of een afwijkende peildatum en is dan "
            "eenvoudig te verklaren.",
        ]

    regels += [
        "",
        "Met vriendelijke groet,",
        "",
        "",
    ]

    if not assessment.analysis_available:
        regels += [
            "",
            "[Interne aantekening, niet meesturen: de inhoudelijke weging is niet "
            "uitgevoerd. Loop de bevindingen zelf na voordat je dit verstuurt.]",
        ]

    return "\n".join(regels)


def build_document_request_email(
    klant_naam: str,
    ontbrekende_stukken: List[str],
    aangiftejaar: int,
    termijn: str = "twee weken",
) -> str:
    """Kort bericht om alleen ontbrekende stukken op te vragen."""
    aanhef = f"Geachte {klant_naam}," if klant_naam else "Geachte heer, mevrouw,"
    opsomming = "\n".join(f"- {stuk}" for stuk in ontbrekende_stukken)

    return "\n".join([
        aanhef,
        "",
        f"Voor de afronding van de aangifte over {aangiftejaar} missen wij nog "
        f"een aantal stukken:",
        "",
        opsomming,
        "",
        f"Wij ontvangen deze graag binnen {termijn}. Zonder deze stukken kunnen "
        f"wij de betreffende posten niet onderbouwen.",
        "",
        "Met vriendelijke groet,",
        "",
    ])

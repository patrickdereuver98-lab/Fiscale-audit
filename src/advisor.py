"""
FiscAudit AI - Fiscal Advisor Engine
Claude 3.5 Sonnet voor inhoudelijke fiscale risico-analyse en adviespunten.
Genereert ook concept-mails naar klanten.
"""

import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from anthropic import Anthropic

from .matcher import MatchResult, AuditSummary


# ============================================================================
# ENUMS
# ============================================================================

class RiskLevel(str, Enum):
    """Risicoclassificatie"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class RiskPoint:
    """Individueel risicopunt"""
    titel: str
    beschrijving: str
    impact: RiskLevel
    aanbevolen_actie: str
    referentie: str = ""  # Bijv. "IB 2024 artikel 5.2"


@dataclass
class RiskAssessment:
    """Volledige risico-analyse"""
    overall_risk: RiskLevel
    risico_punten: List[RiskPoint] = field(default_factory=list)
    sterke_punten: List[str] = field(default_factory=list)
    waarschuwingen: List[str] = field(default_factory=list)
    aanbevelingen: List[str] = field(default_factory=list)
    klant_email_concept: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        """Convert naar dict"""
        return {
            "overall_risk": self.overall_risk.value,
            "risico_punten": [
                {
                    "titel": p.titel,
                    "beschrijving": p.beschrijving,
                    "impact": p.impact.value,
                    "aanbevolen_actie": p.aanbevolen_actie,
                    "referentie": p.referentie
                }
                for p in self.risico_punten
            ],
            "sterke_punten": self.sterke_punten,
            "waarschuwingen": self.waarschuwingen,
            "aanbevelingen": self.aanbevelingen,
            "timestamp": self.timestamp
        }


# ============================================================================
# FISCAL ADVISOR CLASS
# ============================================================================

class FiscalAdvisor:
    """
    Claude 3.5 Sonnet-gebaseerde fiscale adviseur.
    Analyseert audit-resultaten en genereert professioneel advies.
    """
    
    SYSTEM_PROMPT = """Je bent een senior fiscaal auditor en belastingadviseur met 15+ jaren ervaring.

Je specialisaties:
- Nederlands belastingrecht (Inkomstenbelasting, Vennootschapsbelasting)
- Box 3 regelgeving (vermogensrendement)
- Particuliere ondernemers (Eenmanszaken, VOF, BV)
- Aftrekbeperkingen en bijzondere regelingen (KIA, herinvesteringsreserves)
- WOZ-waarderingen en vastgoedberekeningen
- Compliance en documentatie

Je taak:
1. Analyseer de audit-resultaten en geëxtraheerde financiële gegevens
2. Identificeer fiscale risico's en inconsistenties
3. Beoordeel de naleving van het Nederlands belastingrecht
4. Geef concrete, praktische aanbevelingen
5. Genereer een professionele email naar de klant

OUTPUT FORMAAT:
Retourneer UITSLUITEND geldige JSON (geen markdown, geen preamble):
{
  "overall_risk": "LOW/MEDIUM/HIGH/CRITICAL",
  "risico_punten": [
    {
      "titel": "Korte titel",
      "beschrijving": "Gedetailleerde beschrijving",
      "impact": "LOW/MEDIUM/HIGH/CRITICAL",
      "aanbevolen_actie": "Wat de klant/adviseur moet doen",
      "referentie": "Bijv. IB 2024 artikel X"
    }
  ],
  "sterke_punten": ["Goed punt 1", "Goed punt 2"],
  "waarschuwingen": ["Mogelijke valkuil 1", "Mogelijke valkuil 2"],
  "aanbevelingen": [
    "Aanbeveling 1",
    "Aanbeveling 2",
    "Aanbeveling 3"
  ],
  "klant_email_concept": "Email text in Nederlands (formeel, professioneel)"
}

BELASTINGREGELS WAARMEE JE REKENING HOUDT:
- Box 1: Winst onderneming met aftrekposten (hypotheekrente, giften)
- Box 2: Winstbelastingen (minder relevant voor particulieren)
- Box 3: Vermogensrendementsheffing (woning, beleggingen, rekeningen)
- KIA: Kleinschaligheidsinitieerafheffing (bedrijvenstarters)
- Herinvesteringsreserve: Gereserveerde winst voor groei
- WOZ-bepalingen: Eigenwoningen tegen vastgestelde waarde
- Aftrekbeperkingen: Rente (box 1), giften (min. €5 per onderwerp)

Wees voorzichtig met:
- Ontbrekende documentatie
- Inconsistenties tussen aangiften en documenten
- Mogelijke belastingmijding (je rol is audit, niet enforcement)
"""
    
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        Parameters:
        -----------
        api_key : str
            Anthropic API key
        model : str
            Claude model name
        """
        self.api_key = api_key
        self.model = model
        self.client = Anthropic(api_key=api_key)
    
    def analyze_audit(self, 
                     results: List[MatchResult],
                     summary: AuditSummary,
                     extracted_data: Dict[str, Any],
                     klant_naam: str = "Klant",
                     aangiftejaar: int = 2024) -> RiskAssessment:
        """
        Voer fiscale risico-analyse uit op audit-resultaten.
        
        Parameters:
        -----------
        results : List[MatchResult]
            Lijst van match-resultaten
        summary : AuditSummary
            Samenvatting van audit
        extracted_data : Dict[str, Any]
            Geëxtraheerde financiële data
        klant_naam : str
            Naam van klant (voor email)
        aangiftejaar : int
            Aangiftejaar
        
        Returns:
        --------
        RiskAssessment
            Volledige risico-analyse
        """
        
        # Bouw analysis prompt
        prompt = self._build_analysis_prompt(
            results, summary, extracted_data, klant_naam, aangiftejaar
        )
        
        try:
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            raw_response = response.content[0].text
        except Exception as e:
            # Fallback als Claude faalt
            return self._generate_fallback_assessment(str(e))
        
        # Parse JSON response
        try:
            # Clean response
            clean_json = raw_response.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
            
            data = json.loads(clean_json)
            
            # Converteer naar RiskAssessment
            assessment = RiskAssessment(
                overall_risk=RiskLevel(data.get("overall_risk", "MEDIUM")),
                sterke_punten=data.get("sterke_punten", []),
                waarschuwingen=data.get("waarschuwingen", []),
                aanbevelingen=data.get("aanbevelingen", []),
                klant_email_concept=data.get("klant_email_concept", "")
            )
            
            # Parse risico punten
            for rp in data.get("risico_punten", []):
                assessment.risico_punten.append(RiskPoint(
                    titel=rp.get("titel", ""),
                    beschrijving=rp.get("beschrijving", ""),
                    impact=RiskLevel(rp.get("impact", "MEDIUM")),
                    aanbevolen_actie=rp.get("aanbevolen_actie", ""),
                    referentie=rp.get("referentie", "")
                ))
            
            return assessment
            
        except json.JSONDecodeError:
            print(f"Claude response is geen geldige JSON: {raw_response[:100]}")
            return self._generate_fallback_assessment("JSON parse error")
        except Exception as e:
            return self._generate_fallback_assessment(str(e))
    
    def _build_analysis_prompt(self,
                              results: List[MatchResult],
                              summary: AuditSummary,
                              extracted_data: Dict[str, Any],
                              klant_naam: str,
                              aangiftejaar: int) -> str:
        """Bouw de analysis prompt"""
        
        # Samenvatting van mismatches
        mismatches_text = ""
        for r in results:
            if r.status.value == "MISMATCH":
                mismatches_text += f"  - {r.ag_code} ({r.ag_name}): Aangifte €{r.bedrag_aangifte:.2f}, Document €{r.bedrag_document:.2f}, Verschil €{r.verschil:.2f}\n"
        
        missing_text = ""
        for r in results:
            if r.status.value == "MISSING_PROOF":
                missing_text += f"  - {r.ag_code} ({r.ag_name}): €{r.bedrag_aangifte:.2f} aangegeven, geen ondersteunend document\n"
        
        prompt = f"""
AUDIT SAMENVATTING VOOR {klant_naam} - AANGIFTEJAAR {aangiftejaar}

STATISTIEKEN:
- Totaal AG-codes: {summary.total_ag_codes}
- Correcte matches: {summary.matched_count} ({summary.accuracy_percentage:.0f}%)
- Mismatches: {summary.mismatched_count}
- Ontbrekende bewijzen: {summary.missing_proof_count}
- Totaal verschil: €{summary.total_verschil:.2f} ({summary.total_mismatch_percentage:.1f}% van totaal)

GEËXTRAHEERDE FINANCIËLE DATA:
{json.dumps(extracted_data, indent=2, ensure_ascii=False)}

MISMATCHES GEDETAILLEERD:
{mismatches_text if mismatches_text else "  (geen mismatches)"}

ONTBREKENDE BEWIJZEN:
{missing_text if missing_text else "  (alles is ondersteund)"}

VOLLEDIG DETAIL VAN ALLE RESULTATEN:
{json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False)}

JOUW TAAK:
1. Analyseer welke risico's uit deze audit naar voren komen
2. Beoordeel de fiscale naleving
3. Identificeer ontbrekende documentatie
4. Geef concrete vervolgstappen
5. Genereer een professionele email naar de klant met de bevindingen en vervolgstappen

GENEREER UITSLUITEND JSON RESPONSE (geen andere tekst).
"""
        return prompt
    
    def _generate_fallback_assessment(self, error_msg: str) -> RiskAssessment:
        """Fallback assessment als Claude niet beschikbaar is"""
        return RiskAssessment(
            overall_risk=RiskLevel.MEDIUM,
            sterke_punten=[
                "Audit proces succesvol afgerond"
            ],
            waarschuwingen=[
                f"Fiscale analyse kon niet volledig worden afgerond: {error_msg}",
                "Raadpleeg een belastingadviseur voor gedetailleerd advies"
            ],
            aanbevelingen=[
                "Controleer alle mismatches handmatig",
                "Verzamel ontbrekende documentatie",
                "Plan bespreking met belastingadviseur"
            ],
            klant_email_concept=self._generate_generic_email()
        )
    
    def _generate_generic_email(self) -> str:
        """Genereer een generieke email template"""
        return """Geachte klant,

Wij hebben een financiële audit uitgevoerd op uw aangiftegegevens. 
In de bijlage vindt u een gedetailleerd rapport met onze bevindingen en aanbevelingen.

Punten voor vervolgactie:
1. Verzamel alle nog ontbrekende ondersteunende documenten
2. Controleer de geïdentificeerde verschillen
3. Plan een bespreking met uw belastingadviseur

Wij bellen u volgende week voor afronding.

Met vriendelijke groeten,
FiscAudit AI Team"""


# ============================================================================
# EMAIL GENERATOR
# ============================================================================

class EmailGenerator:
    """Helper class voor professionele emails naar klanten"""
    
    EMAIL_TEMPLATES = {
        "initial_audit": """Geachte {klant_naam},

Naar aanleiding van uw verzoek hebben wij een fiscale audit uitgevoerd op uw aangiften voor het jaar {jaar}.

SAMENVATTING BEVINDINGEN:
Totaal onderzochte posten: {total_codes}
Correct: {matches} ({match_pct}%)
Correcties nodig: {mismatches}
Ontbrekende documentatie: {missing}

VERVOLGSTAPPEN:
1. Controleer onderstaande punten zorgvuldig
2. Verzamel ontbrekende documenten
3. Neem contact op voor verdere toelichting

Volledige rapport bijgesloten.

Met vriendelijke groeten,
FiscAudit AI Team""",
        
        "missing_documents": """Geachte {klant_naam},

Ter voorbereiding op uw belastingaangifte voor {jaar} verzoeken wij u de volgende documenten aan te leveren:

{documents_list}

Deze stukken zijn nodig om de juistheid van uw aangiften te garanderen.

Deadline: {deadline}

Bij vragen: {contact}

Met vriendelijke groeten,
FiscAudit AI Team""",
        
        "final_report": """Geachte {klant_naam},

Hierbij dienen wij u het definitieve auditrapport in voor aangiftejaar {jaar}.

EINDCONCLUSIE: {conclusion}

Aanbevelingen voor toekomst:
{recommendations}

Wij verzoeken u dit rapport goed door te nemen en eventuele opmerkingen met ons te delen.

Met vriendelijke groeten,
FiscAudit AI Team"""
    }
    
    @staticmethod
    def generate_document_request_email(klant_naam: str, 
                                       missing_docs: List[str],
                                       jaar: int,
                                       deadline: str = "7 dagen") -> str:
        """Genereer email voor aanvraag ontbrekende documenten"""
        docs_list = "\n".join([f"- {doc}" for doc in missing_docs])
        
        template = EmailGenerator.EMAIL_TEMPLATES["missing_documents"]
        return template.format(
            klant_naam=klant_naam,
            jaar=jaar,
            documents_list=docs_list,
            deadline=deadline,
            contact="audit@company.nl"
        )


if __name__ == "__main__":
    print("Fiscal Advisor module loaded")
    print("Available risk levels:", [r.value for r in RiskLevel])

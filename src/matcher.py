"""
FiscAudit AI - Audit Matcher Engine
Pure Python deterministic matching van AG-codes vs. geëxtraheerde financiële data.
GEEN AI-afhankelijkheden - 100% reproducible en auditabel.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json

from .extractor import ExtractedFinancialData


# ============================================================================
# ENUMS
# ============================================================================

class AuditStatus(str, Enum):
    """Status van een AG-code match"""
    MATCH = "MATCH"                    # Verschil is € 0
    MISMATCH = "MISMATCH"              # Verschil > € 0
    MISSING_PROOF = "MISSING_PROOF"    # Geen onderbouwing gevonden
    ERROR = "ERROR"                    # Fout bij vergelijking
    PENDING = "PENDING"                # Nog niet verwerkt


# ============================================================================
# MAPPING DEFINITIONS (AG-codes to Financial Fields)
# ============================================================================

# Nederlands belastingstelsel AG-codes mapping
AG_CODE_MAPPING = {
    # Inkomstenbelasting - Salaris
    "AG1010": {
        "name": "Looninkomen",
        "field": "bedrijfsinkomen.winst",
        "description": "Salaris uit dienstbetrekking"
    },
    
    # Inkomstenbelasting - Box 1 Onderneming
    "AG2010": {
        "name": "Winst onderneming",
        "field": "bedrijfsinkomen.winst",
        "description": "Netto bedrijfswinst (omzet - kosten)"
    },
    "AG2050": {
        "name": "Omzet/opbrengsten",
        "field": "bedrijfsinkomen.bruto_omzet",
        "description": "Bruto opbrengsten onderneming"
    },
    "AG2060": {
        "name": "Bedrijfskosten",
        "field": "bedrijfsinkomen.kosten_totaal",
        "description": "Totale bedrijfskosten"
    },
    
    # Inkomstenbelasting - Box 2 (niet veel gebruikt)
    
    # Inkomstenbelasting - Box 3 Vermogen
    "AG3010": {
        "name": "Totaal Box 3 vermogen",
        "field": "box3_totaalwaarde",
        "description": "Totale waarde inkomstensfeer vermogen"
    },
    "AG3020": {
        "name": "Bank- en spaartegoeden",
        "field": "totaal_bank_saldi",
        "description": "Som van alle banksaldi 31 december"
    },
    "AG3030": {
        "name": "WOZ-waarde eigenwoningen",
        "field": "woz_gegevens.woz_waarde",
        "description": "Vastgestelde WOZ-waarde op 1 januari"
    },
    "AG3050": {
        "name": "Overige bezittingen Box 3",
        "field": "box3_totaalwaarde",
        "description": "Effecten, goud, andere beleggingen"
    },
    
    # Inkomstenbelasting - Aftrekposten
    "AG4010": {
        "name": "Hypotheekrente",
        "field": "hypotheekrente_totaal",
        "description": "Aftrekbare hypotheekrente"
    },
    "AG4020": {
        "name": "Giften instellingen",
        "field": "giften_charitabel",
        "description": "Giften aan liefdadige instellingen"
    },
    "AG4030": {
        "name": "Studiefinanciering rente",
        "field": "studiefinanciering_rente",
        "description": "Aftrekbare studieschuldrente"
    },
    
    # Vennootschapsbelasting
    "AG6010": {
        "name": "Winst vennootschap",
        "field": "bedrijfsinkomen.winst",
        "description": "Winst NV/BV"
    },
    "AG6020": {
        "name": "Opbrengsten vennootschap",
        "field": "bedrijfsinkomen.bruto_omzet",
        "description": "Opbrengsten/omzet NV/BV"
    },
    
    # Bijzondere regelingen
    "AG7010": {
        "name": "KIA (Kleinschaligheidsaftrek)",
        "field": "kia_investering",
        "description": "Investeringsaftrek voor kleine bedrijven"
    },
    "AG7020": {
        "name": "Herinvesteringsreserve",
        "field": "herinvesteringsreserve",
        "description": "Gereserveerde winstgedeelte"
    }
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class MatchResult:
    """Resultaat van een AG-code match"""
    ag_code: str
    ag_name: str
    status: AuditStatus
    bedrag_aangifte: Optional[float] = None     # Wat de klant heeft ingediend
    bedrag_document: Optional[float] = None     # Wat we in documenten vonden
    verschil: Optional[float] = None            # |aangifte - document|
    percentage_verschil: Optional[float] = None # (verschil / aangifte) * 100
    opmerking: str = ""
    document_bron: str = ""                     # Welk document dit came from
    confidence: float = 1.0                     # Vertrouwen in de match (0-1)
    extracted_path: Optional[str] = None        # Pad in geëxtraheerde data
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        """Converteer naar dict voor database"""
        return {
            "ag_code": self.ag_code,
            "ag_name": self.ag_name,
            "status": self.status.value,
            "bedrag_aangifte": self.bedrag_aangifte,
            "bedrag_document": self.bedrag_document,
            "verschil": self.verschil,
            "percentage_verschil": self.percentage_verschil,
            "opmerking": self.opmerking,
            "document_bron": self.document_bron,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }


@dataclass
class AuditSummary:
    """Samenvattend rapport van een volledige audit"""
    total_ag_codes: int = 0
    matched_count: int = 0           # Status MATCH
    mismatched_count: int = 0        # Status MISMATCH
    missing_proof_count: int = 0     # Status MISSING_PROOF
    error_count: int = 0             # Status ERROR
    total_aangifte: float = 0.0
    total_document: float = 0.0
    total_verschil: float = 0.0
    kritieke_mismatches: List[MatchResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def accuracy_percentage(self) -> float:
        """Hoeveel procent van de AG-codes zijn correct"""
        if self.total_ag_codes == 0:
            return 0.0
        return (self.matched_count / self.total_ag_codes) * 100
    
    @property
    def total_mismatch_percentage(self) -> float:
        """Hoeveel procent van totaal bedrag is fout"""
        if self.total_aangifte == 0:
            return 0.0
        return (self.total_verschil / self.total_aangifte) * 100


# ============================================================================
# AUDIT MATCHER CLASS
# ============================================================================

class AuditMatcher:
    """
    Deterministische matcher: vergelijkt AG-codes met geëxtraheerde data.
    Geen AI, 100% reproducible en auditabel.
    """
    
    # Threshold voor warschuwing bij verschillen
    MISMATCH_THRESHOLD_EUR = 100.0    # Alles > €100 is significant
    PERCENTAGE_THRESHOLD = 2.0         # Of > 2% verschil
    
    def __init__(self, threshold_eur: float = 100.0, threshold_pct: float = 2.0):
        """
        Parameters:
        -----------
        threshold_eur : float
            Minimaal verschil in EUR om als MISMATCH te markeren
        threshold_pct : float
            Minimaal procentueel verschil om als MISMATCH te markeren
        """
        self.threshold_eur = threshold_eur
        self.threshold_pct = threshold_pct
    
    def match_ag_codes(self, 
                      ag_codes: Dict[str, float],
                      extracted_data: ExtractedFinancialData) -> Tuple[List[MatchResult], AuditSummary]:
        """
        Match ingevoerde AG-codes tegen geëxtraheerde documentdata.
        
        Parameters:
        -----------
        ag_codes : Dict[str, float]
            Ingevoerde AG-codes: bijv. {"AG2010": 50000.0, "AG3030": 400000.0}
        extracted_data : ExtractedFinancialData
            Geëxtraheerde data uit PDF's
        
        Returns:
        --------
        Tuple[List[MatchResult], AuditSummary]
            Lijst van matches en een samenvatting
        """
        results = []
        summary = AuditSummary(total_ag_codes=len(ag_codes))
        
        for ag_code, bedrag_aangifte in ag_codes.items():
            try:
                result = self._match_single_ag_code(
                    ag_code, bedrag_aangifte, extracted_data
                )
                results.append(result)
                
                # Update summary statistieken
                if result.status == AuditStatus.MATCH:
                    summary.matched_count += 1
                elif result.status == AuditStatus.MISMATCH:
                    summary.mismatched_count += 1
                    summary.kritieke_mismatches.append(result)
                elif result.status == AuditStatus.MISSING_PROOF:
                    summary.missing_proof_count += 1
                elif result.status == AuditStatus.ERROR:
                    summary.error_count += 1
                
                if result.bedrag_aangifte:
                    summary.total_aangifte += result.bedrag_aangifte
                if result.bedrag_document:
                    summary.total_document += result.bedrag_document
                if result.verschil:
                    summary.total_verschil += result.verschil
                    
            except Exception as e:
                # Vang onverwachte errors
                result = MatchResult(
                    ag_code=ag_code,
                    ag_name=AG_CODE_MAPPING.get(ag_code, {}).get("name", "Unknown"),
                    status=AuditStatus.ERROR,
                    bedrag_aangifte=bedrag_aangifte,
                    opmerking=f"Error: {str(e)}",
                    confidence=0.0
                )
                results.append(result)
                summary.error_count += 1
        
        return results, summary
    
    def _match_single_ag_code(self, 
                             ag_code: str,
                             bedrag_aangifte: float,
                             extracted_data: ExtractedFinancialData) -> MatchResult:
        """
        Match een enkel AG-code tegen de geëxtraheerde data.
        """
        # Lookup AG-code definitie
        ag_def = AG_CODE_MAPPING.get(ag_code)
        if not ag_def:
            return MatchResult(
                ag_code=ag_code,
                ag_name="Unknown",
                status=AuditStatus.ERROR,
                bedrag_aangifte=bedrag_aangifte,
                opmerking=f"AG-code niet herkend"
            )
        
        ag_name = ag_def["name"]
        field_path = ag_def["field"]
        
        # Extraheer corresponderende waarde uit extracted data
        bedrag_document = self._extract_field_value(extracted_data, field_path)
        
        # Vergelijk
        if bedrag_document is None:
            return MatchResult(
                ag_code=ag_code,
                ag_name=ag_name,
                status=AuditStatus.MISSING_PROOF,
                bedrag_aangifte=bedrag_aangifte,
                bedrag_document=None,
                opmerking=f"Geen ondersteunend document gevonden voor {field_path}",
                confidence=0.5
            )
        
        # Bereken verschil
        verschil = abs(bedrag_aangifte - bedrag_document)
        percentage = (verschil / bedrag_aangifte * 100) if bedrag_aangifte != 0 else 0
        
        # Bepaal status
        if verschil == 0:
            status = AuditStatus.MATCH
            confidence = 1.0
            opmerking = "Perfecte match"
        elif verschil < self.threshold_eur and percentage < self.threshold_pct:
            status = AuditStatus.MATCH
            confidence = 0.95
            opmerking = f"Match binnen tolerantie (€{verschil:.2f})"
        else:
            status = AuditStatus.MISMATCH
            confidence = 0.7
            opmerking = f"Verschil: €{verschil:.2f} ({percentage:.1f}%)"
        
        return MatchResult(
            ag_code=ag_code,
            ag_name=ag_name,
            status=status,
            bedrag_aangifte=bedrag_aangifte,
            bedrag_document=bedrag_document,
            verschil=verschil,
            percentage_verschil=percentage,
            opmerking=opmerking,
            confidence=confidence,
            extracted_path=field_path,
            document_bron="Extracted PDF Data"
        )
    
    def _extract_field_value(self, data: ExtractedFinancialData, 
                           field_path: str) -> Optional[float]:
        """
        Extract een waarde uit ExtractedFinancialData via dot notation.
        Bijv. "bedrijfsinkomen.winst" -> data.bedrijfsinkomen.winst
        """
        try:
            parts = field_path.split(".")
            current = data
            
            for part in parts:
                if hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return None
            
            # Convert naar float als nodig
            if isinstance(current, (int, float)):
                return float(current)
            return None
            
        except Exception:
            return None
    
    def generate_audit_report(self, results: List[MatchResult], 
                            summary: AuditSummary) -> Dict:
        """
        Genereer een structured audit report.
        """
        return {
            "timestamp": summary.timestamp,
            "summary": {
                "total_ag_codes": summary.total_ag_codes,
                "matched": summary.matched_count,
                "mismatched": summary.mismatched_count,
                "missing_proof": summary.missing_proof_count,
                "errors": summary.error_count,
                "accuracy_percentage": round(summary.accuracy_percentage, 1),
                "total_aangifte": summary.total_aangifte,
                "total_document": summary.total_document,
                "total_verschil": summary.total_verschil,
                "total_verschil_percentage": round(summary.total_mismatch_percentage, 1)
            },
            "details": [r.to_dict() for r in results],
            "kritieke_punten": [
                {
                    "ag_code": r.ag_code,
                    "naam": r.ag_name,
                    "bedrag_aangifte": r.bedrag_aangifte,
                    "bedrag_document": r.bedrag_document,
                    "verschil": r.verschil,
                    "opmerking": r.opmerking
                }
                for r in summary.kritieke_mismatches
            ]
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def validate_ag_code(ag_code: str) -> bool:
    """Valideer of een AG-code geldig is"""
    return ag_code in AG_CODE_MAPPING


def get_ag_code_description(ag_code: str) -> Optional[str]:
    """Krijg beschrijving van een AG-code"""
    if ag_code in AG_CODE_MAPPING:
        return AG_CODE_MAPPING[ag_code]["description"]
    return None


if __name__ == "__main__":
    # Test
    print("Audit Matcher loaded")
    print(f"Gedefinieerde AG-codes: {len(AG_CODE_MAPPING)}")
    for code, info in list(AG_CODE_MAPPING.items())[:5]:
        print(f"  {code}: {info['name']}")

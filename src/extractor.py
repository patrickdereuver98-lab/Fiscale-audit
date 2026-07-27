"""
FiscAudit AI - Document Extractor Engine
Gemini 1.5 Pro voor visuele PDF-extractie naar gestructureerde JSON.
Pydantic v2 voor strikte output validation.
"""

import json
import base64
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

import google.generativeai as genai
from pydantic import BaseModel, Field, ValidationError


# ============================================================================
# ENUMS
# ============================================================================

class DocumentType(str, Enum):
    """Type documenten die we kunnen extracten"""
    WOZ_BESCHIKKING = "WOZ_Beschikking"
    BANK_JAAROVERZICHT = "Bank_Jaaroverzicht"
    JAARREKENING = "Jaarrekening"
    BELASTINGOPGAAF = "Belastingopgaaf"
    HYPOTHEEKDOCUMENT = "Hypotheekdocument"
    BELEGGINGSAFSCHRIFT = "Beleggingsafschrift"
    BOX3_AANGIFTE = "Box3_Aangifte"
    OVERIG = "Overig"


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class BankBalance(BaseModel):
    """Bank saldo informatie"""
    iban: Optional[str] = Field(None, description="IBAN (geanonimiseerd)")
    saldo: Optional[float] = Field(None, description="Saldo in EUR")
    rente: Optional[float] = Field(None, description="Rentetarief (%)")
    peildatum: Optional[str] = Field(None, description="Peildatum (YYYY-MM-DD)")


class MortgageInfo(BaseModel):
    """Hypotheek informatie"""
    schuld_ausstande: Optional[float] = Field(None, description="Restschuld EUR")
    betaalde_rente: Optional[float] = Field(None, description="Betaalde rente EUR")
    percentage: Optional[float] = Field(None, description="Rentepercentage")
    type_hypotheek: Optional[str] = Field(None, description="Bijv. 'Aflossingshypotheek'")


class BusinessIncome(BaseModel):
    """Bedrijfsinkomen informatie"""
    bruto_omzet: Optional[float] = Field(None, description="Bruto omzet EUR")
    kosten_totaal: Optional[float] = Field(None, description="Totale bedrijfskosten EUR")
    winst: Optional[float] = Field(None, description="Netto bedrijfswinst EUR")
    type_onderneming: Optional[str] = Field(None, description="Bijv. 'Eenmanszaak', 'VOF'")


class PropertyInfo(BaseModel):
    """Vastgoed/WOZ informatie"""
    woz_waarde: Optional[float] = Field(None, description="WOZ-waarde EUR")
    adres: Optional[str] = Field(None, description="Adres (geanonimiseerd)")
    eigenaar_percentage: Optional[float] = Field(None, description="Eigendomspercentage")
    type_woning: Optional[str] = Field(None, description="Bijv. 'Appartementsrecht'")


class ExtractedFinancialData(BaseModel):
    """
    Volledig schema voor geëxtraheerde financiële data.
    Dit is de canonical form voor audit matching.
    """
    
    # Document metadata
    document_type: DocumentType = Field(..., description="Type document")
    peildatum_of_jaar: str = Field(..., description="Peildatum of jaar (YYYY-MM-DD of YYYY)")
    extraction_date: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # WOZ/Vastgoed
    woz_gegevens: Optional[PropertyInfo] = Field(None)
    
    # Bankrekeningen
    bank_saldi: Optional[List[BankBalance]] = Field(None, description="Lijst van bankrekeningen")
    totaal_bank_saldi: Optional[float] = Field(None, description="Som van alle banksaldi")
    
    # Hypotheek
    hypotheek_info: Optional[MortgageInfo] = Field(None)
    
    # Bedrijfsinkomen
    bedrijfsinkomen: Optional[BusinessIncome] = Field(None)
    
    # Box 3 / Belegingen
    box3_totaalwaarde: Optional[float] = Field(None, description="Totale waarde Box 3 vermogen")
    beleggingsrekeningen: Optional[List[Dict[str, Any]]] = Field(None)
    
    # Overige posten
    overige_inkomsten: Optional[float] = Field(None, description="Andere inkomstenbronnen")
    renteopbrengsten: Optional[float] = Field(None)
    dividendopbrengsten: Optional[float] = Field(None)
    
    # Aftrekposten
    giften_charitabel: Optional[float] = Field(None, description="Giften aan liefdadige doelen")
    studiefinanciering_rente: Optional[float] = Field(None)
    hypotheekrente_totaal: Optional[float] = Field(None)
    
    # Bijzondere regelingen
    kia_investering: Optional[float] = Field(None, description="Kleinschaligheidsiftrek")
    herinvesteringsreserve: Optional[float] = Field(None)
    
    # Metadata
    betrouwbaarheid_score: float = Field(0.0, ge=0.0, le=1.0, 
                                         description="Hoe zeker de AI is (0-1)")
    geëxtraheerde_velden: List[str] = Field(default_factory=list, 
                                           description="Welke velden zijn echt gevonden")
    waarschuwingen: List[str] = Field(default_factory=list,
                                     description="Problemen bij extractie")
    ruwe_extractie: Optional[str] = Field(None, description="Ruwe tekst uit PDF")


# ============================================================================
# DOCUMENT EXTRACTOR CLASS
# ============================================================================

class DocumentExtractor:
    """
    Gemini 1.5 Pro-gebaseerde documentextractor.
    Herkent financiële documenten en extraheert gestructureerde data.
    """
    
    SYSTEM_PROMPT = """Je bent een expert fiscaal auditor en documentextractor. 
Je taak is om financiële documenten (PDF's) te analyseren en alle relevante gegevens 
in gestructureerde JSON-format terug te geven.

STRIKTE REGELS:
1. Extracteer ALLEEN gegevens die werkelijk in het document voorkomen.
2. Beleg getallen in JSON met het type 'number' (geen strings).
3. Datums altijd in YYYY-MM-DD format (of YYYY voor jaren).
4. Currencywaarden altijd in EUR (als nodig: converteer).
5. Als je onzeker bent: laat het veld leeg (null) maar voeg een waarschuwing toe.
6. Nooit raden, hallucinerend inventeren.

FOCUS GEBIEDEN:
- WOZ-waarden en vastgoedgegevens
- Banksaldi en rente-inkomsten
- Hypotheekschulden en betaalde rente
- Bedrijfsinkomen (omzet, winst)
- Box 3 vermogen (beleggingen, spaarrekeningen)
- Aftrekbare posten (giften, studiefinanciering, hypotheekrente)
- Bijzondere regelingen (KIA, herinvesteringsreserve)

Retourneer het antwoord UITSLUITEND als geldige JSON (geen markdown, geen ```json wrapper)."""
    
    def __init__(self, api_key: str, model: str = "gemini-1.5-pro-vision-latest"):
        """
        Parameters:
        -----------
        api_key : str
            Google Gemini API key
        model : str
            Model name (default: gemini-1.5-pro-vision-latest)
        """
        self.api_key = api_key
        self.model = model
        genai.configure(api_key=api_key)
        self.client = genai.GenerativeModel(model)
    
    async def extract_from_pdf(self, pdf_path: str, 
                              document_type_hint: Optional[DocumentType] = None) -> ExtractedFinancialData:
        """
        Extraheer financiële data uit een PDF.
        
        Parameters:
        -----------
        pdf_path : str
            Pad naar PDF-bestand
        document_type_hint : Optional[DocumentType]
            Hint wat voor soort document het is
        
        Returns:
        --------
        ExtractedFinancialData
            Gevalideerde gestructureerde data
        
        Raises:
        -------
        ValidationError : Als JSON niet voldoet aan schema
        FileNotFoundError : Als PDF niet bestaat
        """
        try:
            # Lees PDF en converteer naar base64
            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()
            pdf_base64 = base64.standard_b64encode(pdf_data).decode('utf-8')
        except FileNotFoundError:
            raise FileNotFoundError(f"PDF niet gevonden: {pdf_path}")
        
        # Bouw prompt met context
        user_prompt = self._build_extraction_prompt(document_type_hint)
        
        try:
            # Call Gemini met vision
            response = self.client.generate_content([
                user_prompt,
                {
                    "mime_type": "application/pdf",
                    "data": pdf_base64
                }
            ])
            
            raw_response = response.text
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {str(e)}")
        
        # Parse en validate JSON
        try:
            # Clean response (verwijder markdown wrappers als aanwezig)
            clean_json = raw_response.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
            
            data_dict = json.loads(clean_json)
            
            # Validate tegen Pydantic schema
            extracted_data = ExtractedFinancialData(**data_dict)
            
            # Sla ruwe extractie op voor audit trail
            extracted_data.ruwe_extractie = raw_response
            
            return extracted_data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini response is geen geldige JSON: {str(e)}")
        except ValidationError as e:
            raise ValueError(f"Geëxtraheerde data voldoet niet aan schema: {str(e)}")
    
    async def extract_batch(self, pdf_paths: List[str]) -> List[ExtractedFinancialData]:
        """
        Extraheer data uit meerdere PDF's (parallel).
        
        Parameters:
        -----------
        pdf_paths : List[str]
            Lijst van PDF-paden
        
        Returns:
        --------
        List[ExtractedFinancialData]
            Geëxtraheerde data per PDF
        """
        tasks = [self.extract_from_pdf(path) for path in pdf_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter errors
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Error extracting {pdf_paths[i]}: {result}")
            else:
                valid_results.append(result)
        
        return valid_results
    
    def extract_from_pdf_sync(self, pdf_path: str, 
                             document_type_hint: Optional[DocumentType] = None) -> ExtractedFinancialData:
        """
        Synchrone wrapper voor extract_from_pdf (voor Streamlit).
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.extract_from_pdf(pdf_path, document_type_hint))
        finally:
            loop.close()
    
    def _build_extraction_prompt(self, document_type_hint: Optional[DocumentType]) -> str:
        """Bouw de extractie prompt met context"""
        base_prompt = self.SYSTEM_PROMPT
        
        if document_type_hint:
            base_prompt += f"\n\nDocument type hint: {document_type_hint.value}"
        
        base_prompt += "\n\nReturneer de geëxtraheerde data in dit JSON formaat:"
        base_prompt += """
{
  "document_type": "DocumentType (WOZ_Beschikking/Bank_Jaaroverzicht/etc)",
  "peildatum_of_jaar": "YYYY-MM-DD of YYYY",
  "woz_gegevens": {
    "woz_waarde": 500000.0,
    "adres": "[ADRES_GEANONIMISEERD]",
    "eigenaar_percentage": 100.0,
    "type_woning": "Appartementsrecht"
  },
  "bank_saldi": [
    {
      "iban": "[IBAN_GEANONIMISEERD]",
      "saldo": 50000.0,
      "rente": null,
      "peildatum": "2024-12-31"
    }
  ],
  "totaal_bank_saldi": 50000.0,
  "hypotheek_info": {
    "schuld_ausstande": 300000.0,
    "betaalde_rente": 12000.0,
    "percentage": 4.0,
    "type_hypotheek": "Aflossingshypotheek"
  },
  "bedrijfsinkomen": {
    "bruto_omzet": 150000.0,
    "kosten_totaal": 50000.0,
    "winst": 100000.0,
    "type_onderneming": "Eenmanszaak"
  },
  "box3_totaalwaarde": 75000.0,
  "overige_inkomsten": null,
  "renteopbrengsten": 2500.0,
  "dividendopbrengsten": null,
  "giften_charitabel": 5000.0,
  "hypotheekrente_totaal": 12000.0,
  "kia_investering": null,
  "herinvesteringsreserve": null,
  "betrouwbaarheid_score": 0.95,
  "geëxtraheerde_velden": ["woz_gegevens", "bank_saldi", "hypotheek_info"],
  "waarschuwingen": []
}
"""
        return base_prompt


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def merge_financial_data(datasets: List[ExtractedFinancialData]) -> Dict[str, Any]:
    """
    Merge multiple extracted datasets (bijv. van verschillende documenten).
    """
    merged = {
        "totaal_woz": None,
        "totaal_bank_saldi": 0.0,
        "totaal_hypotheekschuld": None,
        "totaal_bedrijfswinst": None,
        "totaal_box3": 0.0,
        "alle_documenten": []
    }
    
    for data in datasets:
        merged["alle_documenten"].append({
            "type": data.document_type.value,
            "datum": data.peildatum_of_jaar
        })
        
        if data.woz_gegevens and data.woz_gegevens.woz_waarde:
            merged["totaal_woz"] = data.woz_gegevens.woz_waarde
        
        if data.totaal_bank_saldi:
            merged["totaal_bank_saldi"] += data.totaal_bank_saldi
        
        if data.hypotheek_info and data.hypotheek_info.schuld_ausstande:
            merged["totaal_hypotheekschuld"] = data.hypotheek_info.schuld_ausstande
        
        if data.bedrijfsinkomen and data.bedrijfsinkomen.winst:
            merged["totaal_bedrijfswinst"] = data.bedrijfsinkomen.winst
        
        if data.box3_totaalwaarde:
            merged["totaal_box3"] += data.box3_totaalwaarde
    
    return merged


if __name__ == "__main__":
    # Placeholder voor testing (je hebt API key nodig)
    print("Document Extractor module loaded.")
    print("Usage: Create instance van DocumentExtractor en call extract_from_pdf()")

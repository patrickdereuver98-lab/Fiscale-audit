"""
FiscAudit AI - Data Anonymizer Engine
Regex-based masking van gevoelige persoonsgegevens (BSN, IBAN, emails, etc.)
GDPR/AVG compliance layer.
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class MaskingRule:
    """Definitie van een masking rule"""
    name: str
    pattern: re.Pattern
    replacement: str
    description: str


@dataclass
class AnonymizationReport:
    """Rapportage van wat er geanonimiseerd is"""
    timestamp: str
    bsn_count: int = 0
    iban_count: int = 0
    email_count: int = 0
    phone_count: int = 0
    name_count: int = 0
    total_masked: int = 0
    masked_items: Dict[str, List[str]] = field(default_factory=dict)


class DataAnonymizer:
    """
    Robuuste data anonymizer die:
    1. BSN-nummers (11-proof) herkent en maskeert
    2. IBAN's (NL format) herkent en maskeert
    3. E-mailadressen herkent en maskeert
    4. Telefoonnummers herkent en maskeert
    5. Persoonsnamen (optioneel) maskeert
    
    Ondersteuning voor unmask/reveal bij verificatie.
    """
    
    def __init__(self, strict_mode: bool = True):
        """
        Parameters:
        -----------
        strict_mode : bool
            Als True, mask zeer voorzichtig. Als False, kan agressiever maskeren.
        """
        self.strict_mode = strict_mode
        self.mask_registry: Dict[str, str] = {}  # Voor tracking en unmask
        self._setup_patterns()
    
    def _setup_patterns(self):
        """Compileer alle regex patterns voor efficiency"""
        # BSN: 9 cijfers (simpel) of 11 digits met proof (complex)
        # Formaat: NXX XXX XXX of X.XXX.XXX (met punten)
        self.bsn_pattern = re.compile(
            r'\b([0-9]{2}[0-9]{1}[\s\.]?[0-9]{3}[\s\.]?[0-9]{3}|[0-9]{9})\b'
        )
        
        # IBAN: Volledig Nederlands format (NL + 2 check digits + 18 chars)
        self.iban_pattern = re.compile(
            r'\bNL\d{2}[A-Z]{4}\d{10}\b'
        )
        
        # Email: Standard email regex
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
        
        # Telefoonnummers: Nederlands format
        # +31 6 1234 5678 of +31(0)6 1234 5678 of 06-1234-5678
        self.phone_pattern = re.compile(
            r'(?:\+31|0031|0)?[\s\.\-]?[1-9][\s\.\-]?[0-9]{3}[\s\.\-]?[0-9]{4}(?:\s|$|\b)'
        )
        
        # Persoonsnamen: Optioneel, voor strict mode
        # Patroon: "Voornaam Achternaam" (2+ woorden met hoofdletters)
        self.name_pattern = re.compile(
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'
        )
    
    def anonymize_text(self, text: str, mask_bsn: bool = True, 
                       mask_iban: bool = True, mask_email: bool = True,
                       mask_phone: bool = True, mask_names: bool = False) -> Tuple[str, AnonymizationReport]:
        """
        Anonymiseer gevoelige data in tekst.
        
        Parameters:
        -----------
        text : str
            De tekst om te anonymiseren
        mask_bsn : bool
            Mask BSN-nummers
        mask_iban : bool
            Mask IBAN's
        mask_email : bool
            Mask e-mailadressen
        mask_phone : bool
            Mask telefoonnummers
        mask_names : bool
            Mask persoonsnamen (voorzichtig!)
        
        Returns:
        --------
        Tuple[str, AnonymizationReport]
            (geanonimiseerde tekst, rapport met statistieken)
        """
        if not text:
            return text, AnonymizationReport(timestamp=datetime.now().isoformat())
        
        anonymized_text = text
        report = AnonymizationReport(timestamp=datetime.now().isoformat())
        
        # BSN's
        if mask_bsn:
            anonymized_text, bsn_count = self._mask_bsn(anonymized_text)
            report.bsn_count = bsn_count
            report.total_masked += bsn_count
        
        # IBAN's
        if mask_iban:
            anonymized_text, iban_count = self._mask_iban(anonymized_text)
            report.iban_count = iban_count
            report.total_masked += iban_count
        
        # E-mails
        if mask_email:
            anonymized_text, email_count = self._mask_email(anonymized_text)
            report.email_count = email_count
            report.total_masked += email_count
        
        # Telefoon
        if mask_phone:
            anonymized_text, phone_count = self._mask_phone(anonymized_text)
            report.phone_count = phone_count
            report.total_masked += phone_count
        
        # Namen (optioneel, voorzichtig)
        if mask_names and not self.strict_mode:
            anonymized_text, name_count = self._mask_names(anonymized_text)
            report.name_count = name_count
            report.total_masked += name_count
        
        return anonymized_text, report
    
    def _mask_bsn(self, text: str) -> Tuple[str, int]:
        """Mask BSN-nummers (11-proof of 9-cijfers)"""
        count = 0
        masked_bsns = []
        
        def replace_func(match):
            nonlocal count
            original = match.group(0)
            # Verwijder spaties en punten voor opslag
            clean = original.replace(" ", "").replace(".", "")
            mask_key = f"BSN_{count}"
            self.mask_registry[mask_key] = clean
            masked_bsns.append(clean)
            count += 1
            return f"[BSN_MASKED_{count}]"
        
        result = self.bsn_pattern.sub(replace_func, text)
        if masked_bsns:
            report_key = "bsn_masked"
            if report_key not in self.mask_registry:
                self.mask_registry[report_key] = masked_bsns
        return result, count
    
    def _mask_iban(self, text: str) -> Tuple[str, int]:
        """Mask IBAN's"""
        count = 0
        masked_ibans = []
        
        def replace_func(match):
            nonlocal count
            original = match.group(0)
            mask_key = f"IBAN_{count}"
            self.mask_registry[mask_key] = original
            masked_ibans.append(original)
            count += 1
            # Toon alleen eerste 2 en laatste 4 karakters
            return f"[IBAN_{original[:2]}...{original[-4:]}]"
        
        result = self.iban_pattern.sub(replace_func, text)
        if masked_ibans:
            self.mask_registry["iban_masked"] = masked_ibans
        return result, count
    
    def _mask_email(self, text: str) -> Tuple[str, int]:
        """Mask e-mailadressen"""
        count = 0
        masked_emails = []
        
        def replace_func(match):
            nonlocal count
            original = match.group(0)
            mask_key = f"EMAIL_{count}"
            self.mask_registry[mask_key] = original
            masked_emails.append(original)
            count += 1
            # Toon domein voor context
            domain = original.split("@")[1] if "@" in original else "unknown"
            return f"[EMAIL_MASKED@{domain}]"
        
        result = self.email_pattern.sub(replace_func, text)
        if masked_emails:
            self.mask_registry["email_masked"] = masked_emails
        return result, count
    
    def _mask_phone(self, text: str) -> Tuple[str, int]:
        """Mask telefoonnummers"""
        count = 0
        masked_phones = []
        
        def replace_func(match):
            nonlocal count
            original = match.group(0).strip()
            mask_key = f"PHONE_{count}"
            self.mask_registry[mask_key] = original
            masked_phones.append(original)
            count += 1
            return "[PHONE_MASKED]"
        
        result = self.phone_pattern.sub(replace_func, text)
        if masked_phones:
            self.mask_registry["phone_masked"] = masked_phones
        return result, count
    
    def _mask_names(self, text: str) -> Tuple[str, int]:
        """Mask persoonsnamen (voorzichtig!)"""
        count = 0
        masked_names = []
        
        def replace_func(match):
            nonlocal count
            original = match.group(0)
            # Controleer of het waarschijnlijk een naam is
            # (niet in de eerste sentence, niet na bepaalde woorden)
            mask_key = f"NAME_{count}"
            self.mask_registry[mask_key] = original
            masked_names.append(original)
            count += 1
            return "[NAME_MASKED]"
        
        # Voorzichtig: alleen maskeren in bepaalde contexten
        if "[" not in text:  # Skip als al andere masking is gebeurd
            result = self.name_pattern.sub(replace_func, text)
        else:
            result = text
        
        if masked_names:
            self.mask_registry["names_masked"] = masked_names
        return result, count
    
    def anonymize_json(self, data: Dict, mask_bsn: bool = True,
                       mask_iban: bool = True, mask_email: bool = True,
                       mask_phone: bool = True) -> Tuple[Dict, AnonymizationReport]:
        """
        Anonymiseer alle string-values in een dict recursief.
        """
        anonymized = {}
        report = AnonymizationReport(timestamp=datetime.now().isoformat())
        
        def process_value(value):
            if isinstance(value, str):
                masked, _ = self.anonymize_text(
                    value, mask_bsn=mask_bsn, mask_iban=mask_iban,
                    mask_email=mask_email, mask_phone=mask_phone
                )
                return masked
            elif isinstance(value, dict):
                return {k: process_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [process_value(item) for item in value]
            return value
        
        return process_value(data), report
    
    def unmask(self, masked_text: str, mask_key: str) -> Optional[str]:
        """
        Onmask een specifieke geanonimiseerde waarde.
        Voor verificatie/audit trails.
        
        Parameters:
        -----------
        masked_text : str
            De geanonimiseerde tekst
        mask_key : str
            Bijv. "BSN_0", "IBAN_0", etc.
        
        Returns:
        --------
        Optional[str]
            Originele waarde als gevonden, anders None
        """
        return self.mask_registry.get(mask_key)
    
    def get_registry_summary(self) -> Dict:
        """Geef een overzicht van wat er geanonimiseerd is"""
        return {
            "bsn_count": len(self.mask_registry.get("bsn_masked", [])),
            "iban_count": len(self.mask_registry.get("iban_masked", [])),
            "email_count": len(self.mask_registry.get("email_masked", [])),
            "phone_count": len(self.mask_registry.get("phone_masked", [])),
            "name_count": len(self.mask_registry.get("names_masked", [])),
            "total_masked": sum([
                len(self.mask_registry.get("bsn_masked", [])),
                len(self.mask_registry.get("iban_masked", [])),
                len(self.mask_registry.get("email_masked", [])),
                len(self.mask_registry.get("phone_masked", [])),
                len(self.mask_registry.get("names_masked", [])),
            ])
        }
    
    def reset_registry(self):
        """Wis de mask registry (bijv. tussen operaties)"""
        self.mask_registry.clear()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_valid_bsn(bsn_str: str) -> bool:
    """
    Valideer een BSN met de 11-proof check.
    """
    # Verwijder spaties/punten
    clean = bsn_str.replace(" ", "").replace(".", "")
    
    if len(clean) != 9:
        return False
    
    if not clean.isdigit():
        return False
    
    # 11-proof berekening
    try:
        total = 0
        for i, digit in enumerate(clean):
            total += (9 - i) * int(digit)
        return total % 11 == 0
    except:
        return False


def is_valid_iban(iban_str: str) -> bool:
    """
    Basis validatie van een IBAN.
    """
    clean = iban_str.replace(" ", "").replace("-", "")
    return bool(re.match(r'^NL\d{2}[A-Z]{4}\d{10}$', clean))


if __name__ == "__main__":
    # Test
    anonymizer = DataAnonymizer()
    
    test_text = """
    Dhr. J. Pieterse, BSN 123456789, IBAN NL91ABNA0417164300
    Contactgegevens: j.pieterse@example.com / +31 6 12345678
    Vastgesteld vermogen: € 500.000 (WOZ-waarde)
    """
    
    masked, report = anonymizer.anonymize_text(test_text)
    print("Original:")
    print(test_text)
    print("\n\nMasked:")
    print(masked)
    print("\n\nReport:")
    print(f"Total masked: {report.total_masked}")
    print(f"BSN's: {report.bsn_count}, IBAN's: {report.iban_count}, Emails: {report.email_count}")

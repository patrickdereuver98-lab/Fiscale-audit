"""
FiscAudit AI - Ontwerptokens

Eén plek voor alle kleuren, afstanden en schaduwen. Hier wijzigen betekent
overal wijzigen.

Waarom dit bestand bestaat: de kleuren stonden op drie plaatsen. In de
:root-variabelen van style.css, in het Streamlit-thema in .streamlit/config.toml,
en hardgecodeerd tussen de HTML in ui_components.py. Bij een wijziging moest je
alle drie vinden, en de kans dat er een achterbleef was groot. Nu genereert dit
bestand het CSS-blok en leest de Python-kant dezelfde constanten.

Het Streamlit-thema in config.toml blijft een apart bestand, want Streamlit leest
dat voordat de app draait en het kan dus niet vanuit Python worden gezet. Dat
bestand kan daarom alsnog uit de pas lopen; tests/test_thema.py controleert of het
nog overeenkomt met de waarden hieronder en faalt als iemand er een verandert.
"""

from dataclasses import dataclass
from typing import Dict


# ============================================================================
# KLEUREN
# ============================================================================

@dataclass(frozen=True)
class Kleuren:
    """Het palet. Deze hexen zijn opgegeven en staan vast."""

    # achtergronden, van diep naar licht
    achtergrond: str = "#0F172A"
    vlak: str = "#1E293B"
    vlak_hover: str = "#334155"

    # primaire actie
    primair: str = "#2563EB"
    primair_hover: str = "#1D4ED8"
    primair_licht: str = "#3B82F6"

    # status
    goed: str = "#059669"
    goed_licht: str = "#10B981"
    fout: str = "#DC2626"
    fout_licht: str = "#EF4444"
    let_op: str = "#D97706"
    let_op_licht: str = "#F59E0B"
    hoog: str = "#EA580C"        # tussen let_op en fout, voor risiconiveau hoog
    hoog_licht: str = "#FB923C"

    # tekst, van hard naar zacht
    tekst: str = "#F8FAFC"
    tekst_zacht: str = "#CBD5E1"
    tekst_zachtst: str = "#94A3B8"

    # lijnen
    rand: str = "#1E293B"
    rand_licht: str = "#334155"

    # verloop, alleen als tweede stop in een gradient
    achtergrond_verloop: str = "#1A2847"
    vlak_verloop: str = "#2D3748"

    # status "geen bewijs": paars, want het is geen fout maar een onbekende.
    # Rood zou suggereren dat er iets mis is met de aangifte terwijl er alleen
    # een document ontbreekt.
    geen_bewijs: str = "#9333EA"
    geen_bewijs_licht: str = "#C4B5FD"

    def rgba(self, hex_kleur: str, alfa: float) -> str:
        """Zet een hex om naar rgba, voor doorschijnende achtergronden."""
        hex_kleur = hex_kleur.lstrip("#")
        r, g, b = (int(hex_kleur[i:i + 2], 16) for i in (0, 2, 4))
        return f"rgba({r}, {g}, {b}, {alfa})"


KLEUR = Kleuren()


# Risiconiveau naar kleur en label. Op één plek, zodat de rail in het
# werkprogramma, de risico-indicator en de reviewnote niet uit elkaar lopen.
RISICO_KLEUR: Dict[str, str] = {
    "LOW": KLEUR.goed,
    "MEDIUM": KLEUR.let_op,
    "HIGH": KLEUR.hoog,
    "CRITICAL": KLEUR.fout,
}


# ============================================================================
# AFSTANDEN, RADII, SCHADUWEN
# ============================================================================

RUIMTE: Dict[str, str] = {
    "xs": "4px",
    "sm": "8px",
    "md": "16px",
    "lg": "24px",
    "xl": "32px",
}

RADIUS: Dict[str, str] = {
    "sm": "6px",
    "md": "8px",
    "lg": "12px",
}

SCHADUW: Dict[str, str] = {
    "sm": "0 1px 2px rgba(0, 0, 0, 0.3)",
    "md": "0 4px 6px rgba(0, 0, 0, 0.2)",
    "lg": "0 10px 15px rgba(0, 0, 0, 0.3)",
}


# ============================================================================
# TYPOGRAFIE
# ============================================================================
# Systeemfonts: geen externe aanvraag, dus geen wachttijd en geen verschuiving
# van de opmaak tijdens het laden. Voor een gereedschap dat dagelijks open staat
# weegt dat zwaarder dan een eigen letter.

FONT_SANS = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', "
    "Arial, sans-serif"
)

# Monospace voor bedragen: cijfers moeten onder elkaar staan.
FONT_MONO = "'SF Mono', Monaco, Consolas, 'Liberation Mono', monospace"


# ============================================================================
# CSS-VARIABELEN GENEREREN
# ============================================================================

def css_variabelen() -> str:
    """Bouw het :root-blok met alle tokens.

    Wordt door layout.py voor het stijlblad geplaatst, zodat style.css met
    var(--naam) werkt zonder de waarden zelf te kennen.
    """
    regels = [
        "/* Gegenereerd uit src/theme.py. Wijzig de waarden daar, niet hier. */",
        ":root {",
        f"    --dark-bg: {KLEUR.achtergrond};",
        f"    --dark-bg-alt: {KLEUR.vlak};",
        f"    --dark-bg-hover: {KLEUR.vlak_hover};",
        f"    --primary: {KLEUR.primair};",
        f"    --primary-hover: {KLEUR.primair_hover};",
        f"    --primary-light: {KLEUR.primair_licht};",
        f"    --success: {KLEUR.goed};",
        f"    --success-light: {KLEUR.goed_licht};",
        f"    --error: {KLEUR.fout};",
        f"    --error-light: {KLEUR.fout_licht};",
        f"    --warning: {KLEUR.let_op};",
        f"    --warning-light: {KLEUR.let_op_licht};",
        f"    --high: {KLEUR.hoog};",
        f"    --high-light: {KLEUR.hoog_licht};",
        f"    --text-primary: {KLEUR.tekst};",
        f"    --text-secondary: {KLEUR.tekst_zacht};",
        f"    --text-tertiary: {KLEUR.tekst_zachtst};",
        f"    --border: {KLEUR.rand};",
        f"    --border-light: {KLEUR.rand_licht};",
        f"    --dark-bg-gradient: {KLEUR.achtergrond_verloop};",
        f"    --vlak-gradient: {KLEUR.vlak_verloop};",
        f"    --geen-bewijs: {KLEUR.geen_bewijs};",
        f"    --geen-bewijs-light: {KLEUR.geen_bewijs_licht};",
        f"    --font-sans: {FONT_SANS};",
        f"    --font-mono: {FONT_MONO};",
    ]
    for naam, waarde in RUIMTE.items():
        regels.append(f"    --space-{naam}: {waarde};")
    for naam, waarde in RADIUS.items():
        regels.append(f"    --radius-{naam}: {waarde};")
    for naam, waarde in SCHADUW.items():
        regels.append(f"    --shadow-{naam}: {waarde};")
    regels.append("}")
    return "\n".join(regels)


def streamlit_thema() -> Dict[str, str]:
    """De waarden die in .streamlit/config.toml onder [theme] horen.

    Streamlit leest dat bestand voordat de app draait, dus het kan niet vanuit
    Python worden gezet. Deze functie bestaat om te kunnen controleren of het
    bestand nog overeenkomt; tests/test_thema.py doet dat.
    """
    return {
        "base": "dark",
        "primaryColor": KLEUR.primair,
        "backgroundColor": KLEUR.achtergrond,
        "secondaryBackgroundColor": KLEUR.vlak,
        "textColor": KLEUR.tekst,
    }

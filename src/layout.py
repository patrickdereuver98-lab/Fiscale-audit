"""
FiscAudit AI - Paginaopzet

Eén aanroep per pagina: `stel_pagina_in()`. Die zet de paginaconfiguratie en
plaatst de opmaak.

Waarom dit bestand bestaat: `load_css()` stond in app.py en nog een keer in
pages/1_Data_Monitor.py, met elk hun eigen pad naar het stijlblad. Bij een derde
pagina zou het een derde keer worden overgeschreven, en een wijziging aan de een
gaat dan langs de ander heen.

De tokens komen uit theme.py en worden voor het stijlblad geplaatst, zodat
style.css met var(--naam) werkt zonder de waarden zelf te bevatten.
"""

import logging
from pathlib import Path
from typing import Optional

import streamlit as st

from .theme import css_variabelen


logger = logging.getLogger(__name__)

STIJLBLAD = Path(__file__).resolve().parent.parent / "assets" / "style.css"


def _lees_stijlblad() -> str:
    """Lees het stijlblad, of geef een lege tekst terug.

    Een ontbrekend stijlblad maakt de app onaantrekkelijk maar niet onbruikbaar,
    dus dit is een waarschuwing en geen fout.
    """
    try:
        return STIJLBLAD.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Stijlblad niet gelezen (%s): %s", STIJLBLAD, exc)
        return ""


def pas_opmaak_toe() -> None:
    """Plaats de tokens en het stijlblad in de pagina.

    De tokens gaan eerst, want style.css verwijst ernaar met var(--naam).
    """
    st.markdown(
        f"<style>\n{css_variabelen()}\n\n{_lees_stijlblad()}\n</style>",
        unsafe_allow_html=True,
    )


def stel_pagina_in(
    titel: str,
    icoon: str = "📋",
    zijbalk: str = "expanded",
    breed: bool = True,
) -> None:
    """Zet de paginaconfiguratie en de opmaak in één aanroep.

    Moet de eerste Streamlit-aanroep van een pagina zijn, omdat
    st.set_page_config dat eist.

    Args:
        titel: Titel in het browsertabblad.
        icoon: Icoon in het browsertabblad.
        zijbalk: "expanded" of "collapsed".
        breed: True voor de brede indeling.
    """
    st.set_page_config(
        page_title=f"FiscAudit AI · {titel}" if titel else "FiscAudit AI",
        page_icon=icoon,
        layout="wide" if breed else "centered",
        initial_sidebar_state=zijbalk,
    )
    pas_opmaak_toe()


def sectie(nummer: Optional[int], titel: str, toelichting: str = "") -> None:
    """Kop van een sectie in de doorlopende indeling.

    Het nummer is er omdat de stappen een werkelijke volgorde hebben: zonder
    stukken kun je niet controleren, zonder controle valt er niets af te tekenen.
    Waar die volgorde niet bestaat hoort geen nummer, dus dan None meegeven.
    """
    aanduiding = f'<span class="sectie-nummer">{nummer}</span>' if nummer else ""
    st.markdown(
        f"""
        <div class="sectie-kop">
            {aanduiding}
            <div>
                <h2 class="sectie-titel">{titel}</h2>
                {f'<p class="sectie-toelichting">{toelichting}</p>' if toelichting else ""}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

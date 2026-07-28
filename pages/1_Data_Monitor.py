"""
FiscAudit AI - Data Monitor

Beheer van de fiscale kernwaarden en de status van de koppelingen.

De opzet volgt hetzelfde patroon als de bestaande VvAA-monitor: de controles
lezen de kernwaarden rechtstreeks uit de store, dus zonder modelaanroep per
berekening. Alleen hier, op verzoek, worden de waarden tegen officiele bronnen
nagekeken. Wijzigingen worden nooit automatisch doorgevoerd: je ziet elk
voorstel met bron en keurt per stuk goed.
"""

import os
import sys
from datetime import date

import streamlit as st

st.set_page_config(
    page_title="FiscAudit AI - Data Monitor",
    page_icon="🔧",
    layout="wide",
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fiscale_kern import (
    laad_kernwaarden, bewaar_in_json, lege_kernwaarden,
    maak_voorstellen, pas_voorstellen_toe, KERN_BESTAND,
)
from src.triggers import TRIGGER_DEFINITIES, TriggerKind
from src.posten import POSTEN, PostSoort
from src.peildatum import PERIOD_RULES
from src.ui_components import info_box, divider, metric_row, format_count


def load_css() -> None:
    """Laad het stijlblad van de hoofdapplicatie."""
    pad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "style.css")
    try:
        with open(pad, "r", encoding="utf-8") as bestand:
            st.markdown(f"<style>{bestand.read()}</style>", unsafe_allow_html=True)
    except OSError:
        pass


load_css()


def get_secret(*names: str):
    """Zoek een sleutel op, ongeacht de schrijfwijze."""
    try:
        uit_secrets = {str(k).lower(): v for k, v in st.secrets.items()}
    except Exception:
        uit_secrets = {}
    uit_omgeving = {k.lower(): v for k, v in os.environ.items()}
    for naam in names:
        waarde = uit_secrets.get(naam.lower()) or uit_omgeving.get(naam.lower())
        if waarde:
            return str(waarde).strip()
    return None


# ============================================================================
# TAB 1 - FISCALE KERNWAARDEN
# ============================================================================

def render_kernwaarden() -> None:
    """Overzicht en beheer van de fiscale getallen."""
    st.markdown("## Fiscale kernwaarden")
    st.caption(
        "Eén bron voor tarieven, drempels en schijven. De controles lezen dit "
        "rechtstreeks, dus snel en zonder kosten. Kijk periodiek na tegen de "
        "officiele bronnen; wijzigingen moet je per stuk goedkeuren."
    )

    jaar = st.number_input(
        "Belastingjaar",
        value=int(st.session_state.get("kern_jaar", date.today().year - 1)),
        min_value=2015,
        max_value=date.today().year,
        step=1,
    )
    st.session_state["kern_jaar"] = jaar

    kern = laad_kernwaarden(jaar)

    metric_row([
        {"label": "Bruikbaar", "value": format_count(kern.aantal_bruikbaar), "icon": "✅"},
        {"label": "Nog nakijken", "value": format_count(kern.aantal_ontbreekt), "icon": "⬜"},
        {
            "label": "Bron",
            "value": {"supabase": "Supabase", "json": "Bestand", "leeg": "Geen"}.get(
                kern.bron, kern.bron
            ),
            "icon": "🗄️",
        },
    ], columns=3)

    if kern.bron == "leeg":
        info_box(
            "Er zijn nog geen kernwaarden voor dit jaar. Alle waarden staan op "
            "niet vastgesteld. Zolang dat zo is geven berekeningen die deze "
            "waarden nodig hebben een duidelijke foutmelding in plaats van een "
            "uitkomst die op een aanname rust.",
            "warning",
        )
    elif kern.bron == "json":
        info_box(
            "Gelezen uit het terugvalbestand, niet uit Supabase. Stel "
            "SUPABASE_URL en SUPABASE_KEY in om de database te gebruiken.",
            "info",
        )

    if not kern.is_volledig:
        info_box(
            f"{kern.aantal_ontbreekt} van de {len(kern.waarden)} waarden zijn nog "
            f"niet nagekeken. Die worden niet gebruikt en leveren geen stille "
            f"aanname op, maar de bijbehorende controles kunnen dan ook niet lopen.",
            "warning",
        )

    divider()

    st.dataframe(
        kern.status_overzicht(),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Sleutel": st.column_config.TextColumn(width="medium"),
            "Waarde": st.column_config.TextColumn(width="small"),
            "Omschrijving": st.column_config.TextColumn(width="large"),
        },
    )

    divider()

    st.markdown("### Verversen")
    info_box(
        "Verversen kijkt elke waarde na tegen een officiele bron en levert "
        "voorstellen op. Er wordt niets doorgevoerd zonder jouw goedkeuring, en "
        "een voorstel zonder verwijzing naar een bron wordt geweigerd.",
        "info",
    )

    if not get_secret("google_api_key", "GEMINI_API_KEY"):
        info_box(
            "Verversen vraagt een Gemini-sleutel voor het opzoeken van de "
            "bronnen. Zonder sleutel kun je de waarden handmatig invullen in "
            "het bestand data/fiscale_kern.json.",
            "warning",
        )
        return

    info_box(
        "De nakijkfunctie is nog niet aangesloten. De structuur, de "
        "goedkeuringsstap en het opslaan werken; wat ontbreekt is de aanroep die "
        "een waarde bij de bron opzoekt. Die is bewust apart gehouden zodat de "
        "bron uitwisselbaar is, en wordt aangesloten zodra vaststaat welke "
        "bronnen je wilt gebruiken.",
        "info",
    )

    with st.expander("Handmatig invullen"):
        st.caption(
            "Bewerk de waarden hieronder en sla op. Naam en bron zijn verplicht: "
            "zonder die twee is de verificatie niet herleidbaar."
        )

        sleutel = st.selectbox(
            "Waarde",
            options=sorted(kern.waarden),
            format_func=lambda s: f"{s} — {kern.waarden[s].naam}",
        )
        gekozen = kern.waarden[sleutel]
        st.caption(gekozen.toelichting)

        kolom1, kolom2 = st.columns(2)
        with kolom1:
            if gekozen.eenheid == "tabel":
                nieuwe_waarde = st.text_area(
                    "Waarde (JSON)",
                    value="" if gekozen.waarde is None else str(gekozen.waarde),
                    height=120,
                )
            else:
                nieuwe_waarde = st.text_input(
                    f"Waarde ({gekozen.eenheid})",
                    value="" if gekozen.waarde is None else str(gekozen.waarde),
                )
            bron_naam = st.text_input("Bron", value=gekozen.bron_naam)
        with kolom2:
            bron_url = st.text_input("Verwijzing (URL)", value=gekozen.bron_url)
            door = st.text_input("Nagekeken door", value=gekozen.geverifieerd_door)

        if st.button("Opslaan", type="primary"):
            if not (nieuwe_waarde.strip() and bron_url.strip() and door.strip()):
                info_box("Waarde, verwijzing en naam zijn alle drie verplicht.", "error")
            else:
                try:
                    import json as _json
                    gekozen.waarde = (
                        _json.loads(nieuwe_waarde)
                        if gekozen.eenheid == "tabel"
                        else float(nieuwe_waarde.replace(",", "."))
                    )
                    gekozen.bron_naam = bron_naam.strip()
                    gekozen.bron_url = bron_url.strip()
                    gekozen.geverifieerd_door = door.strip()
                    gekozen.laatst_geverifieerd = date.today().isoformat()

                    if bewaar_in_json(kern):
                        info_box(f"{sleutel} opgeslagen en geverifieerd.", "success")
                        st.rerun()
                    else:
                        info_box("Opslaan mislukt. Zie de logregels.", "error")
                except (ValueError, TypeError) as exc:
                    info_box(f"De waarde is niet te lezen: {exc}", "error")

    if KERN_BESTAND.exists():
        with open(KERN_BESTAND, "rb") as bestand:
            st.download_button(
                "Kernwaardenbestand downloaden",
                data=bestand.read(),
                file_name="fiscale_kern.json",
                mime="application/json",
            )
        st.caption(
            "Commit dit bestand naar GitHub, anders verdwijnen de wijzigingen "
            "bij een herstart van de cloudomgeving."
        )


# ============================================================================
# TAB 2 - KOPPELINGEN
# ============================================================================

def render_koppelingen() -> None:
    """Status van de externe koppelingen."""
    st.markdown("## Koppelingen")
    st.caption(
        "Aanwezigheid van de sleutels. Dit zegt nog niet dat de dienst "
        "bereikbaar is; dat blijkt bij het eerste gebruik."
    )

    koppelingen = [
        ("Gemini", "documenten uitlezen", bool(get_secret(
            "google_api_key", "GEMINI_API_KEY", "GOOGLE_API_KEY")), True),
        ("Claude", "inhoudelijke weging", bool(get_secret(
            "anthropic_api_key", "Claude_api_key", "ANTHROPIC_API_KEY")), False),
        ("Supabase", "opslag en kennisbank", bool(
            get_secret("supabase_url", "SUPABASE_URL")
            and get_secret("supabase_key", "SUPABASE_KEY")), False),
    ]

    for naam, waarvoor, aanwezig, verplicht in koppelingen:
        with st.container(border=True):
            kolom1, kolom2 = st.columns([1, 3])
            with kolom1:
                if aanwezig:
                    st.markdown(f"🟢 **{naam}**")
                else:
                    st.markdown(f"{'🔴' if verplicht else '⚪'} **{naam}**")
            with kolom2:
                soort = "verplicht" if verplicht else "optioneel"
                if aanwezig:
                    st.caption(f"Sleutel aanwezig · {waarvoor}")
                else:
                    st.caption(f"Geen sleutel ({soort}) · {waarvoor}")

    divider()
    st.markdown("### Zonder Claude")
    st.caption(
        "De cijfermatige aansluiting en de omissiecontrole werken volledig "
        "zonder Claude. Wat dan ontbreekt is de inhoudelijke toelichting per "
        "bevinding en het conceptbericht."
    )


# ============================================================================
# TAB 3 - CONTROLEREGELS
# ============================================================================

def render_regels() -> None:
    """Wat de tool controleert, zichtbaar in plaats van verstopt in de code."""
    st.markdown("## Controleregels")
    st.caption(
        "Wat de tool nakijkt. Hier zichtbaar zodat je kunt zien wat er wel en "
        "niet wordt gedekt, in plaats van dat het in de code verborgen zit."
    )

    st.markdown("### Posten")
    per_soort = {}
    for post in POSTEN.values():
        per_soort.setdefault(post.soort, []).append(post)

    for soort in PostSoort:
        posten = per_soort.get(soort, [])
        if not posten:
            continue
        with st.expander(f"{soort.label} ({len(posten)})"):
            st.caption(f"Bij ontbreken: {soort.omissie_gevolg}")
            st.dataframe(
                [
                    {
                        "Sleutel": p.key,
                        "Post": p.naam,
                        "Labels in het rapport": ", ".join(p.aangifte_labels),
                        "Benadering": "ja" if p.is_benadering else "",
                    }
                    for p in posten
                ],
                use_container_width=True,
                hide_index=True,
            )

    divider()

    st.markdown("### Bijzondere situaties")
    st.caption(
        "Alleen bij deze situaties komt er een inhoudelijke toets aan te pas. "
        "Zonder een van deze situaties blijft het bij de cijfermatige "
        "aansluiting en kost een dossier geen modelaanroep."
    )

    per_rubriek = {}
    for soort in TriggerKind:
        definitie = TRIGGER_DEFINITIES[soort]
        per_rubriek.setdefault(definitie.rubriek, []).append((soort, definitie))

    for rubriek, situaties in per_rubriek.items():
        with st.expander(f"{rubriek} ({len(situaties)})"):
            for soort, definitie in situaties:
                st.markdown(f"**{definitie.label}** · {definitie.basisrisico.label}")
                st.caption("Wat er langs moet:")
                for punt in definitie.toets_punten:
                    st.markdown(f"- {punt}")
                if definitie.vereiste_stukken:
                    st.caption(
                        "Stukken die in het dossier horen: "
                        + ", ".join(definitie.vereiste_stukken)
                    )
                if definitie.raakt_volgend_jaar:
                    st.caption(
                        "Werkt door naar latere jaren; wordt vastgelegd voor "
                        "de controle van volgend jaar."
                    )
                st.markdown("")

    divider()

    st.markdown("### Perioderegels")
    st.caption(
        "Op welk jaar een document betrokken moet worden. Box 3 gaat over "
        "1 januari van het aangiftejaar, wat gelijk is aan het eindsaldo van "
        "31 december van het jaar ervoor. Inkomensstukken gaan over het "
        "aangiftejaar zelf."
    )
    st.dataframe(
        [
            {
                "Documentsoort": soort.label,
                "Jaar": (
                    "aangiftejaar" if regel.year_offset == 0
                    else f"aangiftejaar {regel.year_offset:+d}"
                ),
                "Soort": "stand op moment" if regel.is_point_in_time else "bedrag over periode",
                "Bevestigd": "ja" if regel.confirmed else "nog nakijken",
                "Reden": regel.toelichting,
            }
            for soort, regel in PERIOD_RULES.items()
        ],
        use_container_width=True,
        hide_index=True,
    )

    onbevestigd = [s.label for s, r in PERIOD_RULES.items() if not r.confirmed]
    if onbevestigd:
        info_box(
            "Nog na te kijken tegen de praktijk: " + ", ".join(onbevestigd)
            + ". Deze regels geven een zachtere melding zolang ze niet bevestigd zijn.",
            "warning",
        )


# ============================================================================
# HOOFDPROGRAMMA
# ============================================================================

def main() -> None:
    """Bouw de pagina op."""
    st.markdown("# Data Monitor")
    st.caption(
        "Beheer van de fiscale kernwaarden, de koppelingen en de controleregels."
    )

    tab_kern, tab_koppelingen, tab_regels = st.tabs(
        ["Fiscale kernwaarden", "Koppelingen", "Controleregels"]
    )

    with tab_kern:
        render_kernwaarden()
    with tab_koppelingen:
        render_koppelingen()
    with tab_regels:
        render_regels()


if __name__ == "__main__":
    main()

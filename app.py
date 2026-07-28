"""
FiscAudit AI - Geautomatiseerde fiscale aansluitcontrole

Leest brondocumenten uit met Gemini, sluit de aangegeven AG-codes zuiver in
Python aan op die documenten, en laat Claude de inhoudelijke risico's wegen.

Opzet van het dashboard: wat aansluit hoeft geen aandacht. De interface zet
daarom de afwijkingen en de posten zonder onderbouwing bovenaan, en houdt de
regels die kloppen samengevouwen.

Voertaal van de interface is Nederlands. Identifiers en docstrings zijn Engels,
conform de rest van de codebase.
"""

import os
import json
import logging
import tempfile
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

import streamlit as st

try:
    from src.anonymizer import DataAnonymizer
    from src.extractor import DocumentExtractor, ExtractedFinancialData
    from src.matcher import (
        AuditMatcher, MatchResult, AuditSummary, AuditStatus, AG_CODE_MAPPING,
    )
    from src.advisor import FiscalAdvisor, build_document_request_email
    from src.db import SupabaseClient
    from src.ui_components import (
        metric_card, metric_row, audit_summary_cards, audit_results_table,
        status_label, status_badge, risk_level_indicator,
        info_box, divider, spacer, progress_step,
        upload_pdf_section, copyable_text_area, export_buttons,
        format_currency, format_percentage, format_count,
    )
except ImportError as exc:
    st.error(f"Modules konden niet worden geladen: {exc}")
    st.stop()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# OPMAAK
# ============================================================================

def load_css() -> None:
    """Laad het externe stijlblad."""
    pad = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    try:
        with open(pad, "r", encoding="utf-8") as bestand:
            st.markdown(f"<style>{bestand.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        logger.warning("Stijlblad niet gevonden op %s", pad)
    except Exception as exc:
        logger.error("Stijlblad laden mislukt: %s", exc)


st.set_page_config(
    page_title="FiscAudit AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_css()


# ============================================================================
# SESSIESTATUS
# ============================================================================

def init_session_state() -> None:
    """Zet de sessievariabelen klaar."""
    standaard: Dict[str, Any] = {
        "extracted_data": None,
        "extracted_data_masked": None,
        "documentnaam": None,
        "ag_codes": {},
        "audit_results": None,
        "audit_summary": None,
        "risk_assessment": None,
        "anonymization_report": None,
        "klant_naam": "",
        "aangiftejaar": datetime.now().year - 1,
    }
    for sleutel, waarde in standaard.items():
        if sleutel not in st.session_state:
            st.session_state[sleutel] = waarde


init_session_state()


# ============================================================================
# CLIENTS
# ============================================================================

def get_secret(*names: str) -> Optional[str]:
    """Zoek een sleutel op, ongeacht de schrijfwijze.

    Kijkt eerst in st.secrets en daarna in de omgevingsvariabelen, zodat zowel
    Streamlit Cloud als een Docker-container werkt. De vergelijking negeert
    hoofdletters, dus GEMINI_API_KEY en gemini_api_key komen op hetzelfde uit.
    """
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


@st.cache_resource(show_spinner=False)
def get_extractor(api_key: str) -> DocumentExtractor:
    """Documentlezer, hergebruikt over herruns heen."""
    return DocumentExtractor(api_key=api_key)


@st.cache_resource(show_spinner=False)
def get_advisor(api_key: str) -> FiscalAdvisor:
    """Fiscaal adviseur, hergebruikt over herruns heen."""
    return FiscalAdvisor(api_key=api_key)


@st.cache_resource(show_spinner=False)
def get_database(url: str, key: str) -> SupabaseClient:
    """Databaseverbinding, hergebruikt over herruns heen."""
    return SupabaseClient(url=url, key=key)


def gemini_key() -> Optional[str]:
    return get_secret("google_api_key", "GEMINI_API_KEY", "GOOGLE_API_KEY")


def claude_key() -> Optional[str]:
    return get_secret("anthropic_api_key", "Claude_api_key", "ANTHROPIC_API_KEY")


def log_actie(actie: str, status: str, details: str = "") -> None:
    """Schrijf een regel naar het controlespoor."""
    logger.info("[CONTROLESPOOR] %s | %s | %s", actie, status, details)


# ============================================================================
# ZIJBALK
# ============================================================================

def render_sidebar() -> None:
    """Dossiergegevens en de status van de koppelingen."""
    with st.sidebar:
        st.markdown("### Dossier")

        st.session_state["klant_naam"] = st.text_input(
            "Naam klant",
            value=st.session_state["klant_naam"],
            placeholder="bijv. Jansen Holding BV",
        )
        st.session_state["aangiftejaar"] = st.number_input(
            "Aangiftejaar",
            value=int(st.session_state["aangiftejaar"]),
            min_value=2015,
            max_value=datetime.now().year,
            step=1,
        )

        divider(12)
        st.markdown("### Voortgang")

        stappen = [
            ("Document uitgelezen", st.session_state["extracted_data"] is not None),
            ("AG-codes ingevoerd", bool(st.session_state["ag_codes"])),
            ("Aansluiting uitgevoerd", st.session_state["audit_results"] is not None),
            ("Advies opgesteld", st.session_state["risk_assessment"] is not None),
        ]
        for tekst, gereed in stappen:
            st.markdown(f"{'✅' if gereed else '⬜'} {tekst}")

        divider(12)
        st.markdown("### Koppelingen")

        koppelingen = [
            ("Gemini (documenten)", bool(gemini_key()), "verplicht"),
            ("Claude (advies)", bool(claude_key()), "optioneel"),
            (
                "Supabase (opslag)",
                bool(get_secret("supabase_url", "SUPABASE_URL")
                     and get_secret("supabase_key", "SUPABASE_KEY")),
                "optioneel",
            ),
        ]
        for naam, actief, soort in koppelingen:
            teken = "🟢" if actief else ("🔴" if soort == "verplicht" else "⚪")
            st.markdown(
                f"{teken} {naam}"
                + ("" if actief else f" <span style='color:#94A3B8'>({soort})</span>"),
                unsafe_allow_html=True,
            )

        if not gemini_key():
            st.caption(
                "Zonder Gemini-sleutel kan er geen document worden uitgelezen. "
                "Zet de sleutel in de instellingen onder Secrets."
            )

        if st.session_state["anonymization_report"]:
            divider(12)
            st.markdown("### Privacy")
            st.caption(
                "Persoonsgegevens zijn gemaskeerd voordat het document naar een "
                "extern model ging."
            )
            st.json(st.session_state["anonymization_report"])


# ============================================================================
# TAB 1 - INVOER
# ============================================================================

def render_tab_invoer() -> None:
    """Brondocument uitlezen en AG-codes invoeren."""
    st.markdown("## Invoer")
    st.caption(
        "Lees eerst het brondocument uit, vul daarna de bedragen uit de aangifte in "
        "en start de aansluiting."
    )

    # ---------- stap 1: document ----------
    st.markdown("#### 1. Brondocument")

    bestand = upload_pdf_section()

    if bestand is not None:
        kolom1, kolom2 = st.columns([1, 2])
        with kolom1:
            uitlezen = st.button(
                "Document uitlezen",
                type="primary",
                use_container_width=True,
                disabled=not gemini_key(),
            )
        with kolom2:
            st.caption(f"{bestand.name} — {bestand.size / 1024:.0f} kB")

        if uitlezen:
            _lees_document_uit(bestand)

    if st.session_state["extracted_data"] is not None:
        _toon_uitgelezen_data()

    divider()

    # ---------- stap 2: AG-codes ----------
    st.markdown("#### 2. Bedragen uit de aangifte")
    st.caption(
        "Vul per AG-code het bedrag in dat in de aangifte staat. Laat een regel "
        "leeg om die code niet te controleren."
    )

    ag_codes = _ag_code_invoer()
    st.session_state["ag_codes"] = ag_codes

    divider()

    # ---------- stap 3: aansluiting ----------
    st.markdown("#### 3. Aansluiting")

    ontbreekt = []
    if st.session_state["extracted_data"] is None:
        ontbreekt.append("een uitgelezen brondocument")
    if not ag_codes:
        ontbreekt.append("minimaal een AG-code met bedrag")

    if ontbreekt:
        info_box("Nog nodig: " + " en ".join(ontbreekt) + ".", "warning")

    if st.button(
        "Aansluiting starten",
        type="primary",
        use_container_width=True,
        disabled=bool(ontbreekt),
    ):
        _voer_aansluiting_uit(ag_codes)


def _lees_document_uit(bestand) -> None:
    """Anonimiseer en lees het document uit."""
    sleutel = gemini_key()
    if not sleutel:
        info_box("Er is geen Gemini-sleutel ingesteld.", "error")
        return

    tijdelijk_pad = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tijdelijk:
            tijdelijk.write(bestand.getbuffer())
            tijdelijk_pad = tijdelijk.name

        progress_step(1, 2, "Document wordt gelezen")
        with st.spinner("Bezig met uitlezen…"):
            extractor = get_extractor(sleutel)
            data = extractor.extract_from_pdf(tijdelijk_pad)

        # Maskeer persoonsgegevens en bewaar die versie apart. De aansluiting
        # gebruikt de originele gegevens (die heeft de bedragen nodig), maar wat
        # naar een extern model gaat is de gemaskeerde versie. In de vorige
        # versie werd de gemaskeerde uitkomst weggegooid en ging het origineel
        # met rekeningnummers alsnog naar Claude.
        st.session_state["extracted_data"] = data
        st.session_state["extracted_data_masked"] = None
        try:
            anonymizer = DataAnonymizer()
            st.session_state["extracted_data_masked"] = anonymizer.anonymize_json(
                data.model_dump(mode="json")
            )
            st.session_state["anonymization_report"] = (
                anonymizer.get_anonymization_report_json()
            )
        except Exception as exc:
            logger.warning("Maskeren van persoonsgegevens mislukt: %s", exc)
        st.session_state["documentnaam"] = bestand.name
        progress_step(2, 2, "Gereed")

        info_box(f"{bestand.name} is uitgelezen.", "success")
        log_actie("DOCUMENT_UITLEZEN", "GELUKT",
                  f"betrouwbaarheid {data.extraction_confidence:.2f}")

    except Exception as exc:
        info_box(f"Het document kon niet worden uitgelezen: {exc}", "error")
        logger.exception("Uitlezen mislukt")
        log_actie("DOCUMENT_UITLEZEN", "MISLUKT", str(exc))

    finally:
        if tijdelijk_pad:
            try:
                os.unlink(tijdelijk_pad)
            except OSError:
                pass


def _toon_uitgelezen_data() -> None:
    """Kengetallen en ruwe data van het uitgelezen document."""
    data: ExtractedFinancialData = st.session_state["extracted_data"]

    betrouwbaarheid = data.extraction_confidence
    if betrouwbaarheid < 0.7:
        info_box(
            f"De betrouwbaarheid van het uitlezen is {format_percentage(betrouwbaarheid)}. "
            "Controleer de bedragen hieronder tegen het document voordat je verder gaat.",
            "warning",
        )

    metric_row([
        {"label": "Betrouwbaarheid", "value": format_percentage(betrouwbaarheid), "icon": "🎯"},
        {"label": "Rekeningen", "value": format_count(len(data.bank_accounts)), "icon": "🏦"},
        {"label": "Leningen", "value": format_count(len(data.mortgages)), "icon": "🏠"},
        {"label": "Panden", "value": format_count(len(data.real_estate)), "icon": "🏘️"},
    ], columns=4)

    with st.expander(f"Uitgelezen gegevens uit {st.session_state['documentnaam']}"):
        st.json(data.model_dump(mode="json"))


def _ag_code_invoer() -> Dict[str, float]:
    """Invoertabel voor de AG-codes.

    Een tabel met vaste regels per bekende code, in plaats van een vrij
    JSON-veld. Daarmee kan er geen onbekende code of ongeldige JSON meer
    worden ingevoerd, en is meteen zichtbaar welke posten er zijn.
    """
    bestaand = st.session_state.get("ag_codes", {})

    rijen = [
        {
            "AG-code": code,
            "Post": gegevens["name"],
            "Rubriek": gegevens.get("category", ""),
            "Bedrag volgens aangifte": float(bestaand.get(code, 0.0)) or None,
        }
        for code, gegevens in sorted(AG_CODE_MAPPING.items())
    ]

    bewerkt = st.data_editor(
        rijen,
        use_container_width=True,
        hide_index=True,
        disabled=["AG-code", "Post", "Rubriek"],
        column_config={
            "AG-code": st.column_config.TextColumn(width="small"),
            "Post": st.column_config.TextColumn(width="medium"),
            "Rubriek": st.column_config.TextColumn(width="small"),
            "Bedrag volgens aangifte": st.column_config.NumberColumn(
                format="%.2f",
                min_value=0.0,
                step=1.0,
                help="Laat leeg om deze code niet te controleren",
            ),
        },
        key="ag_editor",
    )

    ingevuld: Dict[str, float] = {}
    for rij in bewerkt:
        bedrag = rij.get("Bedrag volgens aangifte")
        if bedrag is not None and str(bedrag).strip() != "":
            try:
                ingevuld[rij["AG-code"]] = float(bedrag)
            except (TypeError, ValueError):
                continue

    if ingevuld:
        st.caption(f"{len(ingevuld)} code(s) worden gecontroleerd.")
    return ingevuld


def _voer_aansluiting_uit(ag_codes: Dict[str, float]) -> None:
    """Sluit de AG-codes aan op het uitgelezen document."""
    try:
        with st.spinner("Bezig met aansluiten…"):
            matcher = AuditMatcher()
            resultaten, samenvatting = matcher.match_ag_codes(
                extracted_data=st.session_state["extracted_data"],
                reported_amounts=ag_codes,
            )

        st.session_state["audit_results"] = resultaten
        st.session_state["audit_summary"] = samenvatting
        st.session_state["risk_assessment"] = None  # advies opnieuw opstellen

        aandacht = samenvatting.needs_attention_count
        if aandacht == 0:
            info_box(
                "Alle gecontroleerde codes sluiten aan. Er is geen uitzoekwerk.",
                "success",
            )
        else:
            info_box(
                f"{aandacht} van {samenvatting.total_ag_codes_checked} codes vragen "
                f"aandacht. Ga naar het tabblad Dashboard.",
                "warning",
            )

        log_actie("AANSLUITING", "GELUKT",
                  f"{samenvatting.matched}/{samenvatting.total_ag_codes_checked}")

    except Exception as exc:
        info_box(f"De aansluiting is mislukt: {exc}", "error")
        logger.exception("Aansluiting mislukt")
        log_actie("AANSLUITING", "MISLUKT", str(exc))


# ============================================================================
# TAB 2 - DASHBOARD
# ============================================================================

def render_tab_dashboard() -> None:
    """Resultaten van de aansluiting, met de uitzonderingen bovenaan."""
    st.markdown("## Dashboard")

    if not st.session_state["audit_results"]:
        info_box(
            "Er is nog geen aansluiting uitgevoerd. Begin bij het tabblad Invoer.",
            "info",
        )
        return

    resultaten: List[MatchResult] = st.session_state["audit_results"]
    samenvatting: AuditSummary = st.session_state["audit_summary"]

    st.caption(
        f"{st.session_state['klant_naam'] or 'Naamloos dossier'} · "
        f"aangiftejaar {st.session_state['aangiftejaar']} · "
        f"uitgevoerd in {samenvatting.duration_seconds:.2f} seconden"
    )

    audit_summary_cards(samenvatting)
    divider()

    # ---------- risico ----------
    kolom1, kolom2 = st.columns([1, 2])
    with kolom1:
        st.markdown("#### Dossierrisico")
        risk_level_indicator(samenvatting.overall_risk_level.value)
    with kolom2:
        st.markdown("#### Verdeling")
        _toon_verdeling(samenvatting)

    divider()

    # ---------- uitzonderingen ----------
    uitzonderingen = [r for r in resultaten if r.needs_attention]
    aansluitend = [r for r in resultaten if not r.needs_attention]

    st.markdown("#### Uit te zoeken")
    if uitzonderingen:
        st.caption(
            "Deze posten sluiten niet aan of missen onderbouwing. Gesorteerd op "
            "omvang van het verschil."
        )
        audit_results_table(_filter_resultaten(uitzonderingen))
    else:
        info_box("Geen uitzonderingen. Alle gecontroleerde posten sluiten aan.", "success")

    if aansluitend:
        with st.expander(f"Sluit aan ({len(aansluitend)}) — geen actie nodig"):
            audit_results_table(aansluitend)

    divider()

    # ---------- export ----------
    st.markdown("#### Exporteren")
    export_buttons(
        json.dumps(
            {
                "dossier": {
                    "klant": st.session_state["klant_naam"],
                    "aangiftejaar": st.session_state["aangiftejaar"],
                    "document": st.session_state["documentnaam"],
                },
                "samenvatting": samenvatting.model_dump(mode="json"),
                "resultaten": [r.model_dump(mode="json") for r in resultaten],
            },
            indent=2,
            ensure_ascii=False,
        ),
        file_name=f"controle_{st.session_state['klant_naam'] or 'dossier'}"
                  f"_{st.session_state['aangiftejaar']}",
    )

    _opslaan_in_database(resultaten)


def _toon_verdeling(samenvatting: AuditSummary) -> None:
    """Staafdiagram van de statussen."""
    verdeling = {
        "Akkoord": samenvatting.matched,
        "Klein verschil": samenvatting.minor_variance,
        "Afwijking": samenvatting.mismatched,
        "Geen bewijs": samenvatting.missing_proof,
        "Fout": samenvatting.errors,
    }
    aanwezig = {k: v for k, v in verdeling.items() if v > 0}
    if aanwezig:
        st.bar_chart(aanwezig, horizontal=True, height=180)


def _filter_resultaten(resultaten: List[MatchResult]) -> List[MatchResult]:
    """Filters op status en rubriek."""
    kolom1, kolom2 = st.columns(2)

    statussen = sorted({r.status for r in resultaten}, key=lambda s: s.value)
    with kolom1:
        gekozen_status = st.multiselect(
            "Filter op status",
            options=[s.value for s in statussen],
            default=[s.value for s in statussen],
            format_func=status_label,
            key="filter_status",
        )

    rubrieken = sorted({r.category for r in resultaten if r.category})
    with kolom2:
        gekozen_rubriek = st.multiselect(
            "Filter op rubriek",
            options=rubrieken,
            default=rubrieken,
            key="filter_rubriek",
        )

    gefilterd = [
        r for r in resultaten
        if r.status.value in gekozen_status
        and (not r.category or r.category in gekozen_rubriek)
    ]

    if not gefilterd:
        info_box("Geen regels passen bij deze filters.", "info")
    return gefilterd


def _opslaan_in_database(resultaten: List[MatchResult]) -> None:
    """Resultaten wegschrijven naar Supabase, als die is ingesteld."""
    url = get_secret("supabase_url", "SUPABASE_URL")
    sleutel = get_secret("supabase_key", "SUPABASE_KEY", "supabase_anon_key")

    if not (url and sleutel):
        return

    if not st.button("Resultaten opslaan in database", use_container_width=True):
        return

    if not st.session_state["klant_naam"]:
        info_box("Vul eerst de naam van de klant in de zijbalk in.", "warning")
        return

    try:
        database = get_database(url, sleutel)
        # create_dossier geeft de UUID als string terug, niet een record.
        dossier_id = database.create_dossier(
            klant_naam=st.session_state["klant_naam"],
            aangiftejaar=int(st.session_state["aangiftejaar"]),
        )

        if not dossier_id:
            info_box("Het dossier kon niet worden aangemaakt.", "error")
            return

        if database.save_audit_results(dossier_id, resultaten):
            info_box(f"Opgeslagen onder dossier {dossier_id}.", "success")
        else:
            info_box("Opslaan mislukt. Zie de logregels voor details.", "error")

    except Exception as exc:
        info_box(f"Opslaan mislukt: {exc}", "error")
        logger.exception("Opslaan in database mislukt")


# ============================================================================
# TAB 3 - ADVIES EN COMMUNICATIE
# ============================================================================

def render_tab_advies() -> None:
    """Risicoanalyse van Claude en het conceptbericht aan de klant."""
    st.markdown("## Advies en communicatie")

    if not st.session_state["audit_results"]:
        info_box(
            "Voer eerst een aansluiting uit. Het advies bouwt daarop voort.",
            "info",
        )
        return

    sleutel = claude_key()
    if not sleutel:
        info_box(
            "Er is geen Claude-sleutel ingesteld, dus de inhoudelijke analyse is "
            "niet beschikbaar. De cijfermatige aansluiting op het tabblad "
            "Dashboard werkt hier onafhankelijk van.",
            "warning",
        )
        return

    if st.session_state["risk_assessment"] is None:
        if not st.button("Analyse opstellen", type="primary"):
            st.caption(
                "De analyse weegt de gevonden afwijkingen fiscaal en stelt een "
                "conceptbericht op. Dit kost een Claude-aanroep."
            )
            return
        _stel_analyse_op(sleutel)

    analyse = st.session_state["risk_assessment"]
    if analyse is None:
        return

    # Een mislukte aanroep is hier zichtbaar en wordt niet als inschatting
    # gepresenteerd. De cijfermatige aansluiting staat er onafhankelijk van.
    if not analyse.analysis_available:
        info_box(
            "De inhoudelijke weging is niet gelukt"
            + (f": {analyse.failure_reason}. " if analyse.failure_reason else ". ")
            + "Het risiconiveau hieronder komt uit de cijfermatige aansluiting, "
              "niet uit een inhoudelijke beoordeling.",
            "error",
        )
        if st.button("Opnieuw proberen"):
            st.session_state["risk_assessment"] = None
            st.rerun()

    st.markdown("#### Inschatting")
    risk_level_indicator(analyse.overall_risk.value)
    if analyse.analysis_available:
        st.caption(f"Gewogen door {analyse.model}.")

    divider()

    if analyse.risico_punten:
        st.markdown("#### Bevindingen")
        for nummer, punt in enumerate(analyse.risico_punten, start=1):
            codes = f"  ·  {', '.join(punt.ag_codes)}" if punt.ag_codes else ""
            kop = f"{nummer}. {punt.titel}  ·  {punt.impact.label}{codes}"
            with st.expander(kop):
                if punt.beschrijving:
                    st.markdown(punt.beschrijving)
                if punt.aanbevolen_actie:
                    st.markdown(f"**Vervolgstap:** {punt.aanbevolen_actie}")
                if punt.referentie:
                    st.caption(f"Verwijzing: {punt.referentie}")

    if analyse.ontbrekende_stukken:
        st.markdown("#### Op te vragen stukken")
        for stuk in analyse.ontbrekende_stukken:
            st.markdown(f"- {stuk}")

        kolom1, _ = st.columns([1, 2])
        with kolom1:
            st.download_button(
                "Bericht om stukken op te vragen",
                data=build_document_request_email(
                    klant_naam=st.session_state["klant_naam"],
                    ontbrekende_stukken=analyse.ontbrekende_stukken,
                    aangiftejaar=int(st.session_state["aangiftejaar"]),
                ),
                file_name="opvragen_stukken.txt",
                mime="text/plain",
                use_container_width=True,
            )

    if analyse.aanbevelingen:
        st.markdown("#### Aanbevelingen")
        for aanbeveling in analyse.aanbevelingen:
            st.markdown(f"- {aanbeveling}")

    if analyse.sterke_punten:
        with st.expander("Wat wel goed is onderbouwd"):
            for punt in analyse.sterke_punten:
                st.markdown(f"- {punt}")

    for waarschuwing in analyse.waarschuwingen:
        info_box(waarschuwing, "warning")

    divider()

    st.markdown("#### Conceptbericht aan de klant")
    info_box(
        "De bedragen in dit bericht komen rechtstreeks uit de aansluiting, niet "
        "uit een taalmodel. De formulering is een concept: lees het na en pas het "
        "aan voordat je het verstuurt.",
        "info",
    )

    tekst = copyable_text_area(
        "Bericht", value=analyse.klant_email_concept or "", height=400, key="concept"
    )

    kolom1, kolom2 = st.columns(2)
    with kolom1:
        st.download_button(
            "Bericht downloaden",
            data=tekst,
            file_name=f"bericht_{st.session_state['klant_naam'] or 'klant'}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with kolom2:
        if st.button("Analyse opnieuw opstellen", use_container_width=True):
            st.session_state["risk_assessment"] = None
            st.rerun()


def _stel_analyse_op(sleutel: str) -> None:
    """Roep Claude aan voor de risicoanalyse."""
    try:
        with st.spinner("De bevindingen worden fiscaal gewogen…"):
            advisor = get_advisor(sleutel)
            analyse = advisor.analyze_audit(
                results=st.session_state["audit_results"],
                summary=st.session_state["audit_summary"],
                # Uitsluitend de gemaskeerde versie. Hiervan gebruikt de
                # adviseur alleen het documenttype; de bedragen zitten al in
                # results.
                extracted_data=st.session_state.get("extracted_data_masked"),
                klant_naam=st.session_state["klant_naam"] or "de klant",
                aangiftejaar=int(st.session_state["aangiftejaar"]),
            )
        st.session_state["risk_assessment"] = analyse
        log_actie("ADVIES", "GELUKT", analyse.overall_risk.value)

    except Exception as exc:
        info_box(f"De analyse kon niet worden opgesteld: {exc}", "error")
        logger.exception("Analyse mislukt")
        log_actie("ADVIES", "MISLUKT", str(exc))


# ============================================================================
# HOOFDPROGRAMMA
# ============================================================================

def main() -> None:
    """Bouw de pagina op."""
    render_sidebar()

    st.markdown("# FiscAudit AI")
    st.caption(
        "Sluit de aangegeven AG-codes aan op de brondocumenten. De cijfermatige "
        "controle gebeurt in Python en is reproduceerbaar; alleen het uitlezen en "
        "de inhoudelijke weging gebruiken een taalmodel."
    )

    tab_invoer, tab_dashboard, tab_advies = st.tabs(
        ["Invoer", "Dashboard", "Advies en communicatie"]
    )

    with tab_invoer:
        render_tab_invoer()
    with tab_dashboard:
        render_tab_dashboard()
    with tab_advies:
        render_tab_advies()


if __name__ == "__main__":
    main()

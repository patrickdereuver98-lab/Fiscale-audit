"""
FiscAudit AI - Controle van een ingevulde aangifte tegen de brondocumenten

Twee invoeren: de brondocumenten die de klant heeft aangeleverd, en het
aangifterapport dat de adviseur heeft opgesteld. De tool legt die naast elkaar.

De uitvoer is een werkprogramma: een lijst met wat er niet aansluit, op volgorde
van gevolg, die de reviewer afwerkt. Wat klopt hoeft geen aandacht en staat
samengevouwen.

Drie soorten bevinding, met elk een andere vervolgactie:
    onjuist overgenomen   bron en aangifte wijken af
    niet verwerkt         staat in de bron, niet in de aangifte
    geen onderbouwing     staat in de aangifte, geen bron
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

try:
    from src.domain import (
        AuditStatus, DocumentKind, FindingKind, ReviewStatus, RiskLevel,
    )
    from src.anonymizer import DataAnonymizer
    from src.extractor import DocumentExtractor, ExtractedFinancialData
    from src.aangifte_lezer import Aangifte, lees_aangifte, koppel_aan_posten
    from src.posten import POSTEN, PostSoort
    from src.matcher import AuditMatcher, MatchResult, AuditSummary
    from src.omissions import check_omissies, OmissieRapport
    from src.peildatum import check_document_period, PERIOD_RULES
    from src.triggers import TRIGGER_DEFINITIES, TriggerKind, Trigger, TriggerReport
    from src.advisor import FiscalAdvisor, build_document_request_email
    from src.layout import stel_pagina_in, sectie
    from src.ui_components import (
        dossierband, bevinding_kaart, alles_akkoord, documentregel,
        info_box, divider, uitkomstband, copyable_text_area,
        format_currency, format_count, format_percentage, risk_level_indicator,
    )
except ImportError as exc:
    st.error(f"Modules konden niet worden geladen: {exc}")
    st.stop()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Paginaopzet en opmaak in één aanroep. Moet voor elke andere
# Streamlit-aanroep staan.
stel_pagina_in(titel="Controle", icoon="📋")


# ============================================================================
# SESSIE
# ============================================================================

def init_session_state() -> None:
    """Zet de sessievariabelen klaar."""
    standaard: Dict[str, Any] = {
        "brondocumenten": [],        # [{naam, data, jaar, soort}]
        "aangifte": None,            # Aangifte
        "aangifte_posten": {},       # postsleutel -> bedrag
        "onbekende_regels": [],      # [(label, bedrag)]
        "match_resultaten": None,
        "match_samenvatting": None,
        "omissie_rapport": None,
        "periode_meldingen": [],
        "triggers": None,
        "analyse": None,
        "signoff": {},               # bevindingsleutel -> dict
        "klant_naam": "",
        "aangiftejaar": datetime.now().year - 1,
        "reviewer": "",
        "gecontroleerd_op": None,
    }
    for sleutel, waarde in standaard.items():
        if sleutel not in st.session_state:
            st.session_state[sleutel] = waarde


init_session_state()


def get_secret(*names: str) -> Optional[str]:
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


def gemini_key() -> Optional[str]:
    return get_secret("google_api_key", "GEMINI_API_KEY", "GOOGLE_API_KEY")


def claude_key() -> Optional[str]:
    return get_secret("anthropic_api_key", "Claude_api_key", "ANTHROPIC_API_KEY")


@st.cache_resource(show_spinner=False)
def get_extractor(api_key: str) -> DocumentExtractor:
    """Documentlezer, hergebruikt over herruns heen."""
    return DocumentExtractor(api_key=api_key)


@st.cache_resource(show_spinner=False)
def get_advisor(api_key: str) -> FiscalAdvisor:
    """Adviseur, hergebruikt over herruns heen."""
    return FiscalAdvisor(api_key=api_key)


# ============================================================================
# BEVINDINGEN SAMENVOEGEN
# ============================================================================

def _alle_bevindingen() -> List[Dict[str, Any]]:
    """Bundel alles wat aandacht vraagt tot één lijst, zwaarste eerst.

    De drie bronnen meten verschillende dingen en horen toch in één lijst: de
    reviewer werkt namelijk één lijst af en niet drie tabbladen.
    """
    bevindingen: List[Dict[str, Any]] = []

    # verkeerd overgenomen of zonder onderbouwing
    for resultaat in st.session_state["match_resultaten"] or []:
        if not resultaat.needs_attention:
            continue
        soort = (
            FindingKind.UNSUPPORTED
            if resultaat.status == AuditStatus.MISSING_PROOF
            else FindingKind.TRANSFER_ERROR
        )
        bevindingen.append({
            "sleutel": f"{soort.value.lower()}:{resultaat.ag_code}",
            "soort": soort,
            "post": resultaat.ag_name,
            "ref": resultaat.ag_code,
            "ernst": resultaat.risk_level().value,
            "aangegeven": resultaat.reported_amount_eur,
            "stukken": resultaat.extracted_amount_eur,
            "verschil": resultaat.difference_eur,
            "uitleg": resultaat.notes,
            "gevolg": "",
            "sorteer": abs(resultaat.difference_eur or resultaat.reported_amount_eur),
        })

    # niet verwerkt in de aangifte
    rapport: Optional[OmissieRapport] = st.session_state["omissie_rapport"]
    for omissie in (rapport.omissies if rapport else []):
        bevindingen.append({
            "sleutel": omissie.bevinding_sleutel,
            "soort": FindingKind.OMISSION,
            "post": omissie.naam,
            "ref": omissie.post_key,
            "ernst": omissie.risico.value,
            "aangegeven": omissie.bedrag_in_aangifte_eur,
            "stukken": omissie.bedrag_uit_bron_eur,
            "verschil": None,
            "uitleg": omissie.toelichting,
            "gevolg": omissie.soort.omissie_gevolg.capitalize() + ".",
            "sorteer": abs(omissie.bedrag_uit_bron_eur),
        })

    # verkeerde periode
    for melding in st.session_state["periode_meldingen"]:
        bevindingen.append({
            "sleutel": f"periode:{melding['bestand']}",
            "soort": FindingKind.PERIOD_MISMATCH,
            "post": melding["soort"],
            "ref": melding["bestand"][:28],
            "ernst": RiskLevel.MEDIUM.value if melding["zeker"] else RiskLevel.LOW.value,
            "aangegeven": None,
            "stukken": None,
            "verschil": None,
            "uitleg": melding["melding"],
            "gevolg": "",
            "sorteer": 0,
        })

    # bijzondere situaties
    rapport_triggers: Optional[TriggerReport] = st.session_state["triggers"]
    for trigger in (rapport_triggers.triggers if rapport_triggers else []):
        ontbreekt = trigger.ontbrekende_stukken
        bevindingen.append({
            "sleutel": f"situatie:{trigger.kind.value}",
            "soort": FindingKind.SPECIAL_SITUATION,
            "post": trigger.definitie.label,
            "ref": trigger.definitie.rubriek,
            "ernst": trigger.risico.value,
            "aangegeven": None,
            "stukken": None,
            "verschil": None,
            "uitleg": trigger.reden,
            "gevolg": (
                "Ontbrekende stukken: " + ", ".join(ontbreekt)
                if ontbreekt else ""
            ),
            "sorteer": 0,
        })

    rang = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return sorted(
        bevindingen,
        key=lambda b: (rang.get(b["ernst"], 9), -b["sorteer"]),
    )


def _is_afgehandeld(sleutel: str) -> bool:
    """Of deze bevinding is afgetekend."""
    afspraak = st.session_state["signoff"].get(sleutel)
    if not afspraak:
        return False
    return ReviewStatus(afspraak["status"]).is_resolved


# ============================================================================
# SECTIE 1 - STUKKEN EN AANGIFTE
# ============================================================================

def render_sectie_invoer() -> None:
    """Sectie 1: brondocumenten en aangifterapport inlezen."""
    sectie(
        1, "Stukken en aangifte",
        "Lever beide kanten aan. De tool legt ze naast elkaar.",
    )

    kolom_bron, kolom_aangifte = st.columns(2)

    # ---------- brondocumenten ----------
    with kolom_bron:
        st.markdown("#### Stukken van de klant")
        st.caption("Jaaropgaven, AOV-premie, bankoverzichten, WOZ, hypotheek.")

        bestanden = st.file_uploader(
            "Sleep de stukken hierheen",
            type=["pdf"],
            accept_multiple_files=True,
            key="upload_bron",
            label_visibility="collapsed",
        )

        if bestanden:
            st.caption(f"{len(bestanden)} bestand(en) klaar om te lezen.")
            if st.button(
                "Stukken lezen",
                type="primary",
                use_container_width=True,
                disabled=not gemini_key(),
            ):
                _lees_brondocumenten(bestanden)

        if st.session_state["brondocumenten"]:
            st.markdown("")
            for doc in st.session_state["brondocumenten"]:
                documentregel(doc.get("jaar"), doc["naam"])

    # ---------- aangifterapport ----------
    with kolom_aangifte:
        st.markdown("#### Aangifterapport")
        st.caption(
            "Word geeft een exacte uitlezing zonder model. Bij PDF leest een "
            "model mee en kan een verschil ook een leesfout zijn."
        )

        rapport = st.file_uploader(
            "Sleep het rapport hierheen",
            type=["docx", "rtf", "pdf"],
            key="upload_aangifte",
            label_visibility="collapsed",
        )

        if rapport is not None:
            is_exact = rapport.name.lower().endswith((".docx", ".rtf"))
            if is_exact:
                info_box(
                    "Word of RTF: exacte uitlezing zonder model, dus geen "
                    "leesfout aan de aangiftekant.",
                    "success",
                )
            else:
                info_box(
                    "PDF: een model leest het rapport. Weeg een verschil met "
                    "die onzekerheid mee, of exporteer als Word.",
                    "warning",
                )

            if st.button(
                "Rapport lezen",
                type="primary",
                use_container_width=True,
                disabled=not (is_exact or gemini_key()),
            ):
                _lees_aangifterapport(rapport, is_exact)

        if st.session_state["aangifte"] is not None:
            _toon_aangifte()

    divider()
    _render_situaties()
    divider()
    _render_start_controle()


def _lees_brondocumenten(bestanden) -> None:
    """Lees de aangeleverde stukken uit met Gemini."""
    sleutel = gemini_key()
    if not sleutel:
        info_box("Er is geen Gemini-sleutel ingesteld.", "error")
        return

    gelezen: List[Dict[str, Any]] = []
    balk = st.progress(0.0, text="Bezig met lezen")

    for nummer, bestand in enumerate(bestanden, start=1):
        balk.progress(nummer / len(bestanden), text=f"{bestand.name} lezen")
        tijdelijk_pad = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tijdelijk:
                tijdelijk.write(bestand.getbuffer())
                tijdelijk_pad = tijdelijk.name

            data = get_extractor(sleutel).extract_from_pdf(tijdelijk_pad)
            gelezen.append({
                "naam": bestand.name,
                "data": data,
                "jaar": _bepaal_jaar(data),
                "soort": data.document_type or "",
            })
        except Exception as exc:
            logger.exception("Lezen van %s mislukt", bestand.name)
            info_box(f"{bestand.name} kon niet worden gelezen: {exc}", "error")
        finally:
            if tijdelijk_pad:
                try:
                    os.unlink(tijdelijk_pad)
                except OSError:
                    pass

    balk.empty()
    st.session_state["brondocumenten"] = gelezen
    if gelezen:
        info_box(f"{len(gelezen)} van {len(bestanden)} stukken gelezen.", "success")
        st.rerun()


def _bepaal_jaar(data: ExtractedFinancialData) -> Optional[int]:
    """Haal het jaar uit de uitgelezen gegevens.

    Kijkt naar de velden die een jaar noemen. Wordt er niets gevonden, dan komt
    er None terug en meldt de periodecontrole dat het jaar niet is vastgesteld,
    in plaats van stilzwijgend iets aan te nemen.
    """
    for lijst in ("employment_income", "insurance_premiums", "annuities"):
        for item in getattr(data, lijst, []) or []:
            if getattr(item, "year", None):
                return int(item.year)
    for pand in getattr(data, "real_estate", []) or []:
        if getattr(pand, "year_valued", None):
            return int(pand.year_valued)
    return None


def _lees_aangifterapport(bestand, is_exact: bool) -> None:
    """Lees het aangifterapport en koppel de regels aan de posten."""
    if not is_exact:
        info_box(
            "Het lezen van een PDF-rapport is nog niet aangesloten. Exporteer "
            "het rapport als Word of RTF; dat gaat bovendien exact, zonder "
            "leesonzekerheid aan de aangiftekant.",
            "warning",
        )
        return

    tijdelijk_pad = None
    try:
        achtervoegsel = Path(bestand.name).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=achtervoegsel) as tijdelijk:
            tijdelijk.write(bestand.getbuffer())
            tijdelijk_pad = tijdelijk.name

        aangifte = lees_aangifte(tijdelijk_pad)
        aangifte.bestandsnaam = bestand.name
        per_post, onbekend = koppel_aan_posten(aangifte)

        st.session_state["aangifte"] = aangifte
        st.session_state["aangifte_posten"] = per_post
        st.session_state["onbekende_regels"] = onbekend

        if aangifte.aangiftejaar:
            st.session_state["aangiftejaar"] = aangifte.aangiftejaar

        info_box(
            f"{aangifte.aantal_regels} regels gelezen, {len(per_post)} gekoppeld "
            f"aan een bekende post.",
            "success",
        )
        st.rerun()

    except Exception as exc:
        logger.exception("Rapport lezen mislukt")
        info_box(f"Het rapport kon niet worden gelezen: {exc}", "error")
    finally:
        if tijdelijk_pad:
            try:
                os.unlink(tijdelijk_pad)
            except OSError:
                pass


def _toon_aangifte() -> None:
    """Gelezen aangifteregels en wat er niet te koppelen was."""
    aangifte: Aangifte = st.session_state["aangifte"]
    per_post: Dict[str, float] = st.session_state["aangifte_posten"]
    onbekend: List[Tuple[str, float]] = st.session_state["onbekende_regels"]

    st.markdown("")
    with st.expander(f"{len(per_post)} gekoppelde posten", expanded=False):
        st.dataframe(
            [
                {
                    "Post": POSTEN[k].naam if k in POSTEN else k,
                    "Bedrag": format_currency(v),
                    "Rubriek": POSTEN[k].soort.label if k in POSTEN else "",
                }
                for k, v in sorted(per_post.items())
            ],
            use_container_width=True,
            hide_index=True,
        )

    if onbekend:
        with st.expander(f"{len(onbekend)} regels niet gekoppeld", expanded=True):
            st.caption(
                "Deze regels staan in het rapport maar horen bij geen bekende "
                "post. Ze blijven buiten de controle. Kloppen er posten tussen "
                "die wel gecontroleerd moeten worden, dan moet het label worden "
                "toegevoegd in src/posten.py."
            )
            for label, bedrag in onbekend:
                documentregel(None, label, format_currency(bedrag))


def _render_situaties() -> None:
    """Bijzondere situaties aanvinken."""
    st.markdown("#### Bijzondere situaties")
    st.caption(
        "Vink aan wat er dit jaar is gebeurd. Alleen bij deze situaties komt er "
        "een inhoudelijke toets aan te pas; zonder aangevinkte situatie blijft "
        "het bij de cijfermatige controle en kost het dossier geen modelaanroep."
    )

    per_rubriek: Dict[str, List[TriggerKind]] = {}
    for soort in TriggerKind:
        per_rubriek.setdefault(TRIGGER_DEFINITIES[soort].rubriek, []).append(soort)

    aangevinkt: List[TriggerKind] = []
    kolommen = st.columns(len(per_rubriek))

    for kolom, (rubriek, soorten) in zip(kolommen, per_rubriek.items()):
        with kolom:
            st.markdown(f"**{rubriek}**")
            for soort in soorten:
                if st.checkbox(
                    TRIGGER_DEFINITIES[soort].label,
                    key=f"trig_{soort.value}",
                ):
                    aangevinkt.append(soort)

    if aangevinkt:
        bestandsnamen = [d["naam"] for d in st.session_state["brondocumenten"]]
        from src.triggers import missing_documents

        st.session_state["triggers"] = TriggerReport(triggers=[
            Trigger(
                kind=soort,
                reden="aangevinkt bij de invoer",
                ontbrekende_stukken=missing_documents(soort, bestandsnamen),
            )
            for soort in aangevinkt
        ])
    else:
        st.session_state["triggers"] = None


def _render_start_controle() -> None:
    """De startknop, met wat er nog ontbreekt."""
    st.markdown("#### Controle")

    ontbreekt = []
    if not st.session_state["brondocumenten"]:
        ontbreekt.append("stukken van de klant")
    if not st.session_state["aangifte_posten"]:
        ontbreekt.append("een gelezen aangifterapport")

    if ontbreekt:
        info_box("Nog nodig: " + " en ".join(ontbreekt) + ".", "warning")

    if st.button(
        "Controle uitvoeren",
        type="primary",
        use_container_width=True,
        disabled=bool(ontbreekt),
    ):
        _voer_controle_uit()


def _voer_controle_uit() -> None:
    """Voer de cijfermatige controle, de omissiecontrole en de periodecheck uit."""
    try:
        gecombineerd = _combineer_documenten()
        aangifte_posten: Dict[str, float] = st.session_state["aangifte_posten"]

        with st.spinner("Bezig met controleren"):
            resultaten, samenvatting = AuditMatcher().match_ag_codes(
                extracted_data=gecombineerd,
                reported_amounts=aangifte_posten,
            )
            omissies = check_omissies(gecombineerd, aangifte_posten)

        st.session_state["match_resultaten"] = resultaten
        st.session_state["match_samenvatting"] = samenvatting
        st.session_state["omissie_rapport"] = omissies
        st.session_state["periode_meldingen"] = _controleer_periodes()
        st.session_state["analyse"] = None
        st.session_state["gecontroleerd_op"] = datetime.now().strftime("%d-%m %H:%M")

        aandacht = (
            samenvatting.needs_attention_count
            + len(omissies.omissies)
            + len(st.session_state["periode_meldingen"])
        )
        if aandacht == 0:
            info_box("Alles sluit aan. Er is geen uitzoekwerk.", "success")
        else:
            info_box(
                f"{aandacht} punten vragen aandacht. Ze staan hieronder.",
                "warning",
            )
        st.rerun()

    except Exception as exc:
        logger.exception("Controle mislukt")
        info_box(f"De controle is mislukt: {exc}", "error")


def _combineer_documenten() -> ExtractedFinancialData:
    """Voeg de losse documenten samen tot één beeld.

    Een dossier bestaat uit meerdere stukken en de aansluiting werkt op het
    geheel. Lijsten worden samengevoegd; losse getalvelden worden opgeteld
    zolang minstens een document er een waarde voor geeft, zodat een veld dat
    nergens voorkomt None blijft en dus als ontbrekend bewijs telt.
    """
    documenten = [d["data"] for d in st.session_state["brondocumenten"]]
    if len(documenten) == 1:
        return documenten[0]

    samen = ExtractedFinancialData(
        extraction_confidence=min(d.extraction_confidence for d in documenten),
        document_type="meerdere documenten",
    )

    for lijstveld in ("bank_accounts", "mortgages", "real_estate",
                      "employment_income", "insurance_premiums", "annuities"):
        samengevoegd = []
        for document in documenten:
            samengevoegd.extend(getattr(document, lijstveld, []) or [])
        setattr(samen, lijstveld, samengevoegd)

    for getalveld in ("other_assets_eur", "deductible_items_eur", "kia_profit_eur"):
        waarden = [
            getattr(d, getalveld) for d in documenten
            if getattr(d, getalveld, None) is not None
        ]
        setattr(samen, getalveld, sum(waarden) if waarden else None)

    for document in documenten:
        if document.business_income is not None:
            samen.business_income = document.business_income
            break

    return samen


def _controleer_periodes() -> List[Dict[str, Any]]:
    """Kijk per document na of het bij het aangiftejaar hoort."""
    jaar = int(st.session_state["aangiftejaar"])
    meldingen: List[Dict[str, Any]] = []

    for doc in st.session_state["brondocumenten"]:
        soort = _herken_documentsoort(doc)
        uitkomst = check_document_period(soort, jaar, doc.get("jaar"))
        if uitkomst.needs_attention:
            meldingen.append({
                "bestand": doc["naam"],
                "soort": soort.label,
                "melding": uitkomst.message,
                "zeker": uitkomst.is_certain,
            })
    return meldingen


def _herken_documentsoort(doc: Dict[str, Any]) -> DocumentKind:
    """Bepaal de documentsoort uit het documenttype of de bestandsnaam."""
    tekst = f"{doc.get('soort', '')} {doc['naam']}".lower()
    patronen = [
        (("woz",), DocumentKind.WOZ_BESCHIKKING),
        (("hypothe",), DocumentKind.HYPOTHEEK_JAAROPGAVE),
        (("aov", "arbeidsongeschikt"), DocumentKind.AOV_PREMIE),
        (("lijfrente",), DocumentKind.LIJFRENTE),
        (("afrekening", "notaris"), DocumentKind.NOTA_VAN_AFREKENING),
        (("jaarrekening", "balans"), DocumentKind.JAARREKENING),
        (("uitkering", "uwv", "pensioen"), DocumentKind.JAAROPGAVE_UITKERING),
        (("bank", "spaar", "rekening"), DocumentKind.BANKOVERZICHT),
        (("jaaropgave", "loon", "salaris"), DocumentKind.JAAROPGAVE_LOON),
    ]
    for woorden, soort in patronen:
        if any(woord in tekst for woord in woorden):
            return soort
    return DocumentKind.OVERIG


# ============================================================================
# SECTIE 3 - WAT ER MOET GEBEUREN
# ============================================================================

def render_sectie_bevindingen() -> None:
    """Sectie 3: de lijst die de reviewer afwerkt."""
    bevindingen = _alle_bevindingen()
    afgehandeld = sum(1 for b in bevindingen if _is_afgehandeld(b["sleutel"]))

    dossierband(
        klant=st.session_state["klant_naam"],
        aangiftejaar=int(st.session_state["aangiftejaar"]),
        uitgevoerd_op=st.session_state["gecontroleerd_op"] or "",
        totaal=len(bevindingen),
        afgehandeld=afgehandeld,
        open_punten=len(bevindingen) - afgehandeld,
    )

    _render_cijfers()

    if not bevindingen:
        alles_akkoord(
            "Alle posten in het rapport sluiten aan op de stukken en er staat "
            "niets in de stukken dat in de aangifte ontbreekt."
        )
        return

    alleen_open = st.toggle("Alleen openstaande punten", value=True)

    for bevinding in bevindingen:
        klaar = _is_afgehandeld(bevinding["sleutel"])
        if alleen_open and klaar:
            continue
        _render_bevinding(bevinding, klaar)

    if alleen_open and afgehandeld:
        st.caption(f"{afgehandeld} afgehandelde punten verborgen.")

    divider()
    _render_export(bevindingen)


def _render_cijfers() -> None:
    """De kerncijfers als compacte band.

    Kleur volgt de betekenis en niet de opmaak: een bedrag van nul bij gemiste
    aftrek is goed nieuws en hoort niet rood te zijn.
    """
    samenvatting: AuditSummary = st.session_state["match_samenvatting"]
    omissies: OmissieRapport = st.session_state["omissie_rapport"]

    uitkomstband([
        {
            "label": "Sluit aan",
            "waarde": format_percentage(samenvatting.match_rate),
            "onder": f"{samenvatting.matched + samenvatting.minor_variance} van "
                     f"{samenvatting.total_ag_codes_checked} posten",
            "toon": "goed" if samenvatting.match_rate >= 100 else "",
        },
        {
            "label": "Bruto afwijking",
            "waarde": format_currency(samenvatting.gross_difference_eur),
            "onder": f"saldo {format_currency(samenvatting.net_difference_eur)}",
            "toon": "fout" if samenvatting.gross_difference_eur > 0 else "goed",
        },
        {
            "label": "Gemiste aftrek",
            "waarde": format_currency(omissies.gemiste_aftrek_eur),
            "onder": "klant betaalt te veel",
            "toon": "let-op" if omissies.gemiste_aftrek_eur > 0 else "goed",
        },
        {
            "label": "Te laag aangegeven",
            "waarde": format_currency(omissies.te_laag_aangegeven_eur),
            "onder": "risico op correctie",
            "toon": "fout" if omissies.te_laag_aangegeven_eur > 0 else "goed",
        },
    ])


def _render_bevinding(bevinding: Dict[str, Any], afgehandeld: bool) -> None:
    """Eén bevinding met de sign-off eronder."""
    afspraak = st.session_state["signoff"].get(bevinding["sleutel"], {})

    bevinding_kaart(
        soort_label=bevinding["soort"].label,
        post_naam=bevinding["post"],
        referentie=bevinding["ref"],
        ernst=bevinding["ernst"],
        aangegeven=bevinding["aangegeven"],
        uit_stukken=bevinding["stukken"],
        verschil=bevinding["verschil"],
        uitleg=bevinding["uitleg"],
        gevolg=bevinding["gevolg"],
        afgehandeld=afgehandeld,
        signoff_status=(
            ReviewStatus(afspraak["status"]).label if afspraak else ""
        ),
        signoff_door=afspraak.get("door", ""),
        signoff_reden=afspraak.get("reden", ""),
    )

    if afgehandeld:
        if st.button(
            "Heropenen",
            key=f"open_{bevinding['sleutel']}",
            help="Zet dit punt terug op open",
        ):
            st.session_state["signoff"].pop(bevinding["sleutel"], None)
            st.rerun()
        return

    with st.expander("Aftekenen", expanded=False):
        reden = st.text_input(
            "Onderbouwing",
            key=f"reden_{bevinding['sleutel']}",
            placeholder="Waarom is dit akkoord, of wat moet er worden gecorrigeerd",
        )
        kolom1, kolom2 = st.columns(2)

        with kolom1:
            if st.button(
                "Akkoord",
                key=f"ok_{bevinding['sleutel']}",
                use_container_width=True,
            ):
                # Akkoord zonder reden is een klik en geen beoordeling; de
                # database weigert het ook, dus hier al tegenhouden.
                if not reden.strip():
                    info_box("Akkoord vraagt een onderbouwing.", "error")
                elif not st.session_state["reviewer"].strip():
                    info_box("Vul je initialen in de zijbalk in.", "error")
                else:
                    _teken_af(bevinding["sleutel"], ReviewStatus.ACCEPTED, reden)

        with kolom2:
            if st.button(
                "Correctie vereist",
                key=f"fix_{bevinding['sleutel']}",
                use_container_width=True,
            ):
                if not st.session_state["reviewer"].strip():
                    info_box("Vul je initialen in de zijbalk in.", "error")
                else:
                    _teken_af(
                        bevinding["sleutel"],
                        ReviewStatus.CORRECTION_REQUIRED,
                        reden,
                    )


def _teken_af(sleutel: str, status: ReviewStatus, reden: str) -> None:
    """Leg de behandeling vast."""
    st.session_state["signoff"][sleutel] = {
        "status": status.value,
        "door": st.session_state["reviewer"].strip(),
        "reden": reden.strip(),
        "op": datetime.now().isoformat(timespec="seconds"),
    }
    logger.info("Bevinding %s afgetekend als %s", sleutel, status.value)
    st.rerun()


def _render_export(bevindingen: List[Dict[str, Any]]) -> None:
    """Werkprogramma exporteren."""
    st.markdown("#### Vastleggen")

    uitvoer = {
        "dossier": {
            "klant": st.session_state["klant_naam"],
            "aangiftejaar": st.session_state["aangiftejaar"],
            "gecontroleerd_op": st.session_state["gecontroleerd_op"],
            "reviewer": st.session_state["reviewer"],
        },
        "stukken": [
            {"naam": d["naam"], "jaar": d.get("jaar"), "soort": d.get("soort")}
            for d in st.session_state["brondocumenten"]
        ],
        "aangifte": {
            "bestand": getattr(st.session_state["aangifte"], "bestandsnaam", ""),
            "exact_gelezen": not getattr(
                st.session_state["aangifte"], "is_modelgelezen", True
            ),
            "niet_gekoppeld": st.session_state["onbekende_regels"],
        },
        "bevindingen": [
            {
                "sleutel": b["sleutel"],
                "soort": b["soort"].value,
                "post": b["post"],
                "ernst": b["ernst"],
                "aangegeven": b["aangegeven"],
                "uit_stukken": b["stukken"],
                "verschil": b["verschil"],
                "behandeling": st.session_state["signoff"].get(b["sleutel"]),
            }
            for b in bevindingen
        ],
    }

    kolom1, kolom2 = st.columns(2)
    with kolom1:
        st.download_button(
            "Werkprogramma downloaden",
            data=json.dumps(uitvoer, indent=2, ensure_ascii=False, default=str),
            file_name=f"werkprogramma_{st.session_state['klant_naam'] or 'dossier'}"
                      f"_{st.session_state['aangiftejaar']}.json",
            mime="application/json",
            use_container_width=True,
        )
    with kolom2:
        if st.button("Controle opnieuw uitvoeren", use_container_width=True):
            _voer_controle_uit()


# ============================================================================
# SECTIE 4 - TOELICHTING EN BERICHT
# ============================================================================

def render_sectie_toelichting() -> None:
    """Sectie 4: inhoudelijke weging en het bericht aan de klant."""
    sectie(4, "Toelichting en bericht",
           "Fiscale weging van de bijzondere situaties, en het concept aan de klant.")

    triggers: Optional[TriggerReport] = st.session_state["triggers"]
    heeft_situatie = bool(triggers and triggers.needs_fiscal_analysis)

    if not heeft_situatie:
        info_box(
            "Er is geen bijzondere situatie aangevinkt, dus er is geen "
            "inhoudelijke toets nodig. De cijfermatige controle in het "
            "werkprogramma is volledig. Vink bij Invoer een situatie aan als er "
            "dit jaar iets is gebeurd dat fiscale weging vraagt.",
            "info",
        )

    sleutel = claude_key()
    if not sleutel:
        info_box(
            "Geen Claude-sleutel ingesteld. Het werkprogramma werkt hier "
            "onafhankelijk van; alleen de toelichting per bevinding ontbreekt.",
            "warning",
        )
        return

    if st.session_state["analyse"] is None:
        if heeft_situatie:
            st.caption("Toets de aangevinkte situaties en de bevindingen.")
            for punt in triggers.alle_toets_punten:
                st.markdown(f"- {punt}")
        if st.button("Toelichting opstellen", type="primary"):
            _stel_toelichting_op(sleutel)
        return

    analyse = st.session_state["analyse"]

    if not analyse.analysis_available:
        info_box(
            "De toelichting is niet gelukt"
            + (f": {analyse.failure_reason}." if analyse.failure_reason else ".")
            + " Het werkprogramma is er niet van afhankelijk.",
            "error",
        )
        if st.button("Opnieuw proberen"):
            st.session_state["analyse"] = None
            st.rerun()
        return

    risk_level_indicator(analyse.overall_risk.value)
    st.caption(f"Gewogen door {analyse.model}.")
    divider()

    for nummer, punt in enumerate(analyse.risico_punten, start=1):
        codes = f" · {', '.join(punt.ag_codes)}" if punt.ag_codes else ""
        with st.expander(f"{nummer}. {punt.titel} · {punt.impact.label}{codes}"):
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
        st.download_button(
            "Bericht om stukken op te vragen",
            data=build_document_request_email(
                klant_naam=st.session_state["klant_naam"],
                ontbrekende_stukken=analyse.ontbrekende_stukken,
                aangiftejaar=int(st.session_state["aangiftejaar"]),
            ),
            file_name="opvragen_stukken.txt",
            mime="text/plain",
        )

    for waarschuwing in analyse.waarschuwingen:
        info_box(waarschuwing, "warning")

    divider()
    st.markdown("#### Bericht aan de klant")
    info_box(
        "De bedragen komen uit de controle, niet uit een taalmodel. De "
        "formulering is een concept.",
        "info",
    )
    tekst = copyable_text_area(
        "Bericht", value=analyse.klant_email_concept or "", height=360, key="concept"
    )
    st.download_button(
        "Bericht downloaden",
        data=tekst,
        file_name=f"bericht_{st.session_state['klant_naam'] or 'klant'}.txt",
        mime="text/plain",
    )


def _stel_toelichting_op(sleutel: str) -> None:
    """Roep de adviseur aan."""
    try:
        with st.spinner("Bezig met wegen"):
            analyse = get_advisor(sleutel).analyze_audit(
                results=st.session_state["match_resultaten"],
                summary=st.session_state["match_samenvatting"],
                extracted_data=_gemaskeerde_data(),
                klant_naam=st.session_state["klant_naam"] or "de klant",
                aangiftejaar=int(st.session_state["aangiftejaar"]),
            )
        st.session_state["analyse"] = analyse
        st.rerun()
    except Exception as exc:
        logger.exception("Toelichting mislukt")
        info_box(f"De toelichting kon niet worden opgesteld: {exc}", "error")


def _gemaskeerde_data() -> Optional[Dict[str, Any]]:
    """Gemaskeerde documentgegevens voor de externe aanroep.

    Persoonsgegevens worden gemaskeerd voordat er iets naar een extern model
    gaat. De adviseur gebruikt hiervan alleen het documenttype; de bedragen
    zitten al in de resultaten.
    """
    if not st.session_state["brondocumenten"]:
        return None
    try:
        eerste = st.session_state["brondocumenten"][0]["data"]
        return DataAnonymizer().anonymize_json(eerste.model_dump(mode="json"))
    except Exception as exc:
        logger.warning("Maskeren mislukt, gegevens worden niet meegestuurd: %s", exc)
        return None


# ============================================================================
# ZIJBALK
# ============================================================================

def render_sidebar() -> None:
    """Dossier, reviewer en koppelingen."""
    with st.sidebar:
        st.markdown("### Dossier")
        st.session_state["klant_naam"] = st.text_input(
            "Klant",
            value=st.session_state["klant_naam"],
            placeholder="Jansen Holding BV",
        )
        st.session_state["aangiftejaar"] = st.number_input(
            "Aangiftejaar",
            value=int(st.session_state["aangiftejaar"]),
            min_value=2015,
            max_value=datetime.now().year,
            step=1,
        )
        st.session_state["reviewer"] = st.text_input(
            "Jouw initialen",
            value=st.session_state["reviewer"],
            placeholder="PdR",
            help="Wordt vastgelegd bij elk punt dat je aftekent",
        )

        divider(12)
        st.markdown("### Invoer")
        for tekst, gereed in [
            (f"{len(st.session_state['brondocumenten'])} stukken gelezen",
             bool(st.session_state["brondocumenten"])),
            (f"{len(st.session_state['aangifte_posten'])} posten uit het rapport",
             bool(st.session_state["aangifte_posten"])),
            ("Controle uitgevoerd", st.session_state["match_resultaten"] is not None),
        ]:
            st.markdown(f"{'✓' if gereed else '·'} {tekst}")

        divider(12)
        st.markdown("### Koppelingen")
        for naam, aanwezig, verplicht in [
            ("Gemini", bool(gemini_key()), True),
            ("Claude", bool(claude_key()), False),
        ]:
            teken = "🟢" if aanwezig else ("🔴" if verplicht else "⚪")
            achtervoegsel = "" if aanwezig else (
                " (verplicht)" if verplicht else " (optioneel)"
            )
            st.markdown(f"{teken} {naam}{achtervoegsel}")

        st.caption("Beheer de fiscale kernwaarden in de Data Monitor.")


# ============================================================================
# HOOFDPROGRAMMA
# ============================================================================

def main() -> None:
    """Bouw de pagina op.

    Eén doorlopende pagina in plaats van tabbladen. Een sectie verschijnt pas
    wanneer er iets te zien is, dus bij het openen staan alleen de uploadvakken
    en niet een leeg dashboard met vier nullen. Zodra de controle heeft gelopen
    staat de hele uitkomst onder elkaar en hoef je nergens op te klikken om te
    zien wat er aan de hand is.

    De Data Monitor blijft een aparte pagina: dat is beheer en geen onderdeel
    van deze doorloop.
    """
    render_sidebar()

    st.markdown("# FiscAudit AI")
    st.caption(
        "Controleert een ingevulde aangifte tegen de onderliggende stukken. "
        "De cijfermatige vergelijking gebeurt in Python en is reproduceerbaar; "
        "een model leest alleen de documenten en weegt de bijzondere situaties."
    )

    # 1. altijd zichtbaar: hier begint het werk
    render_sectie_invoer()

    is_gecontroleerd = st.session_state["match_resultaten"] is not None

    if not is_gecontroleerd:
        # Geen lege secties met nullen eronder; die suggereren een uitkomst die
        # er niet is.
        return

    # 2 en 3: uitkomst en wat er moet gebeuren
    sectie(2, "Uitkomst",
           f"Gecontroleerd op {st.session_state['gecontroleerd_op']}.")
    _render_cijfers()

    bevindingen = _alle_bevindingen()
    afgehandeld = sum(1 for b in bevindingen if _is_afgehandeld(b["sleutel"]))

    sectie(
        3, "Wat er moet gebeuren",
        f"{len(bevindingen) - afgehandeld} open, {afgehandeld} afgehandeld."
        if bevindingen else "Niets. Alles sluit aan.",
    )
    render_sectie_bevindingen()

    # 4: alleen relevant wanneer er een bijzondere situatie is aangevinkt
    render_sectie_toelichting()


if __name__ == "__main__":
    main()

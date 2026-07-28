"""
FiscAudit AI - Herbruikbare interfacecomponenten

Alle opmaak loopt via assets/style.css. Deze module bevat geen logica, alleen
presentatie. Teksten zijn Nederlands; identifiers Engels conform de rest van
de codebase.
"""

from typing import Optional, List, Dict, Any

import streamlit as st


# ============================================================================
# OPMAAK VAN GETALLEN (Nederlandse notatie)
# ============================================================================

LEEG = "—"


def format_currency(value: Optional[float], symbol: str = "€") -> str:
    """Bedrag in Nederlandse notatie: punt als duizendscheiding, komma als decimaal.

    De standaard Python-opmaak levert de Engelse notatie (50,000.00) op. Voor
    een Nederlandse aangifte is dat verwarrend en bij bedragen als 1.234,56
    zelfs misleidend.

    Args:
        value: Bedrag, of None wanneer er geen bedrag bekend is.
        symbol: Valutateken.

    Returns:
        Bijvoorbeeld "€ 50.000,00", of "—" bij None.
    """
    if value is None:
        return LEEG

    getal = f"{abs(value):,.2f}"
    # eerst komma's parkeren, dan punten naar komma's, dan parkeerplaats naar punt
    getal = getal.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    teken = "-" if value < 0 else ""
    return f"{teken}{symbol} {getal}"


def format_percentage(value: Optional[float], decimals: int = 1) -> str:
    """Percentage in Nederlandse notatie met komma als decimaalteken.

    Args:
        value: Percentage. Waarden tot en met 1 worden als fractie opgevat.
        decimals: Aantal decimalen.
    """
    if value is None:
        return LEEG
    if 0 < value <= 1:
        value *= 100
    return f"{value:.{decimals}f}".replace(".", ",") + "%"


def format_count(value: Optional[int]) -> str:
    """Aantal met punt als duizendscheiding."""
    if value is None:
        return LEEG
    return f"{value:,}".replace(",", ".")


# ============================================================================
# KENGETALLEN
# ============================================================================

def metric_card(
    label: str,
    value: Any,
    delta: Optional[str] = None,
    icon: str = "",
    tooltip: Optional[str] = None,
) -> None:
    """Kengetalblok met label, waarde en optionele toelichting."""
    icoon = f"{icon} " if icon else ""
    hint = f'<div class="metric-card-hint">{tooltip}</div>' if tooltip else ""
    onder = f'<div class="metric-card-delta">{delta}</div>' if delta else ""

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-label">{label}</div>
            <div class="metric-card-value">{icoon}{value}</div>
            {onder}
            {hint}
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_row(metrics: List[Dict[str, Any]], columns: int = 4) -> None:
    """Rij kengetallen naast elkaar."""
    kolommen = st.columns(min(columns, max(1, len(metrics))))
    for i, metric in enumerate(metrics):
        with kolommen[i % len(kolommen)]:
            metric_card(
                label=metric.get("label", ""),
                value=metric.get("value", LEEG),
                delta=metric.get("delta"),
                icon=metric.get("icon", ""),
                tooltip=metric.get("tooltip"),
            )


# ============================================================================
# STATUS
# ============================================================================

STATUS_CONFIG = {
    "MATCH":          {"icon": "✅", "label": "Akkoord",       "class": "badge-match"},
    "MINOR_VARIANCE": {"icon": "🟡", "label": "Klein verschil", "class": "badge-minor"},
    "MISMATCH":       {"icon": "❌", "label": "Afwijking",     "class": "badge-mismatch"},
    "MISSING_PROOF":  {"icon": "❓", "label": "Geen bewijs",   "class": "badge-missing"},
    "ERROR":          {"icon": "⚠️", "label": "Fout",          "class": "badge-error"},
    "PENDING":        {"icon": "⏳", "label": "In wachtrij",    "class": "badge-pending"},
}


def status_label(status: str) -> str:
    """Nederlandse status met icoon, geschikt voor een tabelcel."""
    cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["ERROR"])
    return f"{cfg['icon']} {cfg['label']}"


def status_badge(status: str) -> str:
    """Status als gekleurde pil (HTML)."""
    cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["ERROR"])
    return f'<span class="badge {cfg["class"]}">{cfg["icon"]} {cfg["label"]}</span>'


RISK_CONFIG = {
    "LOW":      {"icon": "🟢", "label": "Laag risico",    "color": "#059669"},
    "MEDIUM":   {"icon": "🟡", "label": "Middelmatig risico", "color": "#D97706"},
    "HIGH":     {"icon": "🟠", "label": "Hoog risico",    "color": "#EA580C"},
    "CRITICAL": {"icon": "🔴", "label": "Kritiek risico", "color": "#DC2626"},
}


def risk_level_indicator(risk_level: str) -> None:
    """Risiconiveau als gekleurd blok."""
    cfg = RISK_CONFIG.get(risk_level, RISK_CONFIG["HIGH"])
    kleur = cfg["color"]
    r, g, b = int(kleur[1:3], 16), int(kleur[3:5], 16), int(kleur[5:7], 16)

    st.markdown(
        f"""
        <div style="display:inline-flex;align-items:center;gap:8px;
                    padding:12px 20px;border-radius:8px;
                    background:rgba({r},{g},{b},0.12);
                    border:1px solid {kleur};color:{kleur};
                    font-weight:600;font-size:1.05rem;">
            {cfg['icon']} {cfg['label']}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================================
# MELDINGEN
# ============================================================================

def info_box(message: str, box_type: str = "info") -> None:
    """Melding met kleurcode en icoon."""
    config = {
        "info":    ("ℹ️", "info-alert"),
        "success": ("✅", "success-alert"),
        "warning": ("⚠️", "warning-alert"),
        "error":   ("❌", "error-alert"),
    }
    icoon, css = config.get(box_type, config["info"])
    st.markdown(
        f'<div class="stAlert {css}"><p style="margin:0;">'
        f"<strong>{icoon}</strong> {message}</p></div>",
        unsafe_allow_html=True,
    )


def divider(spacing: int = 20) -> None:
    """Scheidingslijn."""
    st.markdown(
        f'<div style="margin:{spacing}px 0;border-top:1px solid #1E293B;"></div>',
        unsafe_allow_html=True,
    )


def spacer(height: int = 20) -> None:
    """Verticale ruimte."""
    st.markdown(f'<div style="height:{height}px;"></div>', unsafe_allow_html=True)


# ============================================================================
# VOORTGANG
# ============================================================================

def progress_step(current: int, total: int, label: str = "") -> None:
    """Voortgangsbalk met stapaanduiding."""
    fractie = 0 if total == 0 else max(0.0, min(1.0, current / total))
    st.markdown(
        f"""
        <div style="margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:0.875rem;color:#CBD5E1;">
                    Stap {current} van {total}
                </span>
                <span style="font-size:0.875rem;color:#94A3B8;">{label}</span>
            </div>
            <div style="width:100%;height:6px;background:#1E293B;
                        border-radius:3px;overflow:hidden;">
                <div style="width:{fractie * 100:.0f}%;height:100%;
                            background:linear-gradient(90deg,#2563EB,#3B82F6);
                            border-radius:3px;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================================
# SAMENVATTING VAN DE CONTROLE
# ============================================================================

def audit_summary_cards(summary: Any) -> None:
    """Kengetallen van een afgeronde controle.

    Verwacht een AuditSummary. De drie geldbedragen meten verschillende dingen
    en worden daarom apart getoond, met toelichting: bruto is de omvang van het
    uitzoekwerk, netto het saldo-effect op de aangifte, en niet-verifieerbaar
    het bedrag waarvoor een brondocument ontbreekt.
    """
    metrics = [
        {
            "label": "Aangesloten",
            "value": format_percentage(summary.match_rate),
            "delta": f"{summary.matched + summary.minor_variance} van "
                     f"{summary.total_ag_codes_checked} codes",
            "icon": "📊",
        },
        {
            "label": "Uit te zoeken",
            "value": format_count(summary.needs_attention_count),
            "delta": f"{summary.mismatched} afwijkingen, "
                     f"{summary.missing_proof} zonder bewijs",
            "icon": "🔍",
        },
        {
            "label": "Bruto afwijking",
            "value": format_currency(summary.gross_difference_eur),
            "delta": f"saldo-effect {format_currency(summary.net_difference_eur)}",
            "icon": "💰",
            "tooltip": "Som van de absolute verschillen",
        },
        {
            "label": "Niet verifieerbaar",
            "value": format_currency(summary.unverified_amount_eur),
            "delta": "brondocument ontbreekt",
            "icon": "📄",
        },
    ]
    metric_row(metrics, columns=4)


# ============================================================================
# RESULTATENTABEL
# ============================================================================

def audit_results_table(results: List[Any]) -> None:
    """Resultaten als tabel, gesorteerd op wat aandacht vraagt.

    Sorteert afwijkingen en ontbrekend bewijs naar boven: dat is het werk dat
    overblijft. Regels die aansluiten hoeven niet bovenaan.
    """
    if not results:
        info_box("Geen resultaten om te tonen.", "info")
        return

    prioriteit = {
        "ERROR": 0, "MISMATCH": 1, "MISSING_PROOF": 2,
        "MINOR_VARIANCE": 3, "MATCH": 4, "PENDING": 5,
    }
    gesorteerd = sorted(
        results,
        key=lambda r: (
            prioriteit.get(r.status.value, 9),
            -abs(r.difference_eur or 0),
        ),
    )

    rijen = []
    for r in gesorteerd:
        naam = r.ag_name
        if getattr(r, "is_approximate", False):
            naam += " *"
        rijen.append({
            "Status": status_label(r.status.value),
            "AG-code": r.ag_code,
            "Post": naam,
            "Rubriek": getattr(r, "category", "") or LEEG,
            "Aangegeven": format_currency(r.reported_amount_eur),
            "Uit document": format_currency(r.extracted_amount_eur),
            "Verschil": format_currency(r.difference_eur),
            "Toelichting": r.notes,
        })

    st.dataframe(
        rijen,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(width="small"),
            "AG-code": st.column_config.TextColumn(width="small"),
            "Post": st.column_config.TextColumn(width="medium"),
            "Toelichting": st.column_config.TextColumn(width="large"),
        },
    )

    if any(getattr(r, "is_approximate", False) for r in gesorteerd):
        st.caption(
            "* Het bedrag uit het document is een benadering. Controleer de "
            "jaaropgave voordat je hierop een conclusie baseert."
        )


# ============================================================================
# INVOER
# ============================================================================

def upload_pdf_section() -> Optional[Any]:
    """Uploadveld voor brondocumenten."""
    return st.file_uploader(
        "Sleep een brondocument hierheen of kies een bestand",
        type=["pdf"],
        help="WOZ-beschikking, bankjaaropgave, hypotheekjaaropgave of jaarrekening",
        key="pdf_uploader",
    )


def copyable_text_area(
    label: str,
    value: str,
    height: int = 300,
    key: Optional[str] = None,
) -> str:
    """Tekstvak waarvan de inhoud te selecteren en te kopieren is.

    Streamlit kan niet rechtstreeks naar het klembord schrijven zonder
    losse component. Het tekstvak zelf is daarom de kopieerfunctie: klikken,
    alles selecteren, kopieren. Daarnaast staat er een downloadknop.
    """
    tekst = st.text_area(label, value=value, height=height, key=key)
    st.caption("Klik in het vak en gebruik Ctrl+A en Ctrl+C om alles te kopieren.")
    return tekst


def export_buttons(json_data: str, file_name: str = "controle") -> None:
    """Exportknoppen voor de resultaten."""
    kolom1, kolom2 = st.columns(2)
    with kolom1:
        st.download_button(
            label="Resultaten downloaden (JSON)",
            data=json_data,
            file_name=f"{file_name}.json",
            mime="application/json",
            use_container_width=True,
        )
    with kolom2:
        if st.button("Opnieuw laden", use_container_width=True):
            st.rerun()


# ============================================================================
# WERKPROGRAMMA
# ============================================================================
# De reviewer werkt een lijst af. Deze componenten renderen die lijst in de
# vormtaal van een controledossier: een sign-off-rail in de kantlijn, een
# werkpapierverwijzing, en bedragen die cijfer voor cijfer uitlijnen.

_ERNST_KLASSE = {
    "CRITICAL": "ernst-kritiek",
    "HIGH": "ernst-hoog",
    "MEDIUM": "ernst-middel",
    "LOW": "ernst-laag",
}


def dossierband(
    klant: str,
    aangiftejaar: int,
    uitgevoerd_op: str,
    totaal: int,
    afgehandeld: int,
    open_punten: int,
) -> None:
    """Kopband met dossier en voortgang.

    Voortgang staat er als een dunne streep en niet als gevierd percentage:
    dit is gereedschap, geen prestatie.
    """
    fractie = 0 if totaal == 0 else afgehandeld / totaal

    st.markdown(
        f"""
        <div class="dossierband">
            <div>
                <div class="dossierband-naam">{klant or "Naamloos dossier"}</div>
                <div class="dossierband-meta">aangiftejaar {aangiftejaar} ·
                    gecontroleerd {uitgevoerd_op}</div>
            </div>
            <div class="voortgang">
                <div class="voortgang-vol" style="width:{fractie * 100:.0f}%"></div>
            </div>
            <div class="band-cijfer">
                <strong>{afgehandeld}</strong> van {totaal} afgehandeld
            </div>
            <div class="band-cijfer">
                <strong>{open_punten}</strong> open
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def bevinding_kaart(
    soort_label: str,
    post_naam: str,
    referentie: str,
    ernst: str,
    aangegeven: Optional[float] = None,
    uit_stukken: Optional[float] = None,
    verschil: Optional[float] = None,
    uitleg: str = "",
    gevolg: str = "",
    afgehandeld: bool = False,
    signoff_status: str = "",
    signoff_door: str = "",
    signoff_reden: str = "",
) -> None:
    """Eén bevinding als regel in het werkprogramma.

    Args:
        soort_label: Aard van de bevinding, als eyebrow boven de post.
        post_naam: Omschrijving van de aangiftepost.
        referentie: Werkpapierverwijzing, bijvoorbeeld de postsleutel.
        ernst: LOW, MEDIUM, HIGH of CRITICAL; bepaalt de kleur van de rail.
        aangegeven: Bedrag volgens de aangifte.
        uit_stukken: Bedrag volgens de brondocumenten.
        verschil: Het verschil, apart uitgelicht.
        uitleg: Toelichting op de bevinding.
        gevolg: Wat het voor de klant betekent.
        afgehandeld: Of de bevinding is afgedaan; dempt de hele regel.
        signoff_status: Nederlandse status, bijvoorbeeld "Akkoord".
        signoff_door: Initialen of naam van wie heeft afgetekend.
        signoff_reden: Onderbouwing bij het accorderen.
    """
    ernst_klasse = "afgehandeld" if afgehandeld else _ERNST_KLASSE.get(ernst, "")
    gedempt = " afgehandeld" if afgehandeld else ""

    blokken = []
    if aangegeven is not None or uit_stukken is not None:
        blokken.append(
            '<div class="vergelijk-blok"><span class="vergelijk-kop">Aangifte</span>'
            f'<span class="vergelijk-waarde{"" if aangegeven is not None else " leeg"}">'
            f'{format_currency(aangegeven) if aangegeven is not None else "niet ingevuld"}'
            "</span></div>"
        )
        blokken.append(
            '<div class="vergelijk-blok"><span class="vergelijk-kop">Stukken</span>'
            f'<span class="vergelijk-waarde{"" if uit_stukken is not None else " leeg"}">'
            f'{format_currency(uit_stukken) if uit_stukken is not None else "geen bewijs"}'
            "</span></div>"
        )
    if verschil is not None:
        blokken.append(
            '<div class="vergelijk-blok verschil"><span class="vergelijk-kop">Verschil</span>'
            f'<span class="vergelijk-waarde">{format_currency(verschil)}</span></div>'
        )

    vergelijking = (
        f'<div class="vergelijk">{"".join(blokken)}</div>' if blokken else ""
    )

    signoff = ""
    if signoff_status:
        klasse = {"Akkoord": "akkoord", "Correctie vereist": "correctie"}.get(
            signoff_status, ""
        )
        reden = (
            f'<span class="signoff-reden">{signoff_reden}</span>'
            if signoff_reden else ""
        )
        initialen = (
            f'<span class="signoff-initialen">{signoff_door}</span>'
            if signoff_door else ""
        )
        vink = "✓" if klasse == "akkoord" else "!"
        signoff = (
            f'<div class="signoff {klasse}"><span class="signoff-vink">{vink}</span>'
            f"{initialen}<span>{signoff_status}</span>{reden}</div>"
        )

    st.markdown(
        f"""
        <div class="bevinding{gedempt}">
            <div class="bevinding-rail {ernst_klasse}"></div>
            <div class="bevinding-body">
                <div class="bevinding-kop">
                    <span class="bevinding-soort {ernst_klasse}">{soort_label}</span>
                    <span class="bevinding-post">{post_naam}</span>
                    <span class="bevinding-ref">{referentie}</span>
                </div>
                {vergelijking}
                {f'<div class="bevinding-uitleg">{uitleg}</div>' if uitleg else ""}
                {f'<div class="bevinding-gevolg">{gevolg}</div>' if gevolg else ""}
                {signoff}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def alles_akkoord(bericht: str) -> None:
    """Rustige melding wanneer er niets uit te zoeken valt."""
    st.markdown(
        f'<div class="alles-akkoord"><span class="alles-akkoord-vink">✓</span>'
        f"{bericht}</div>",
        unsafe_allow_html=True,
    )


def documentregel(jaar: Optional[int], naam: str, melding: str = "") -> None:
    """Eén aangeleverd document, met een melding als de periode niet klopt."""
    st.markdown(
        f"""
        <div class="docregel">
            <span class="docregel-jaar">{jaar if jaar else "—"}</span>
            <span class="docregel-naam">{naam}</span>
            {f'<span class="docregel-melding">{melding}</span>' if melding else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )

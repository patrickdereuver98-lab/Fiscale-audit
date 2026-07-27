"""
FiscAudit AI - Reusable UI Components

Professional, modern components for the Executive Fiscal Dashboard.
All styling is coordinated through the central CSS system.

Components:
- metric_card() - KPI display cards
- status_badge() - Colored status indicators
- sidebar_section() - Organized sidebar layout
- table_result() - Professional data display
- code_block() - Monospace code/results display
"""

import streamlit as st
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def format_currency(value: float, symbol: str = "€") -> str:
    """Format number as currency with proper spacing.
    
    Args:
        value: Number to format
        symbol: Currency symbol (default: €)
        
    Returns:
        Formatted currency string
    """
    return f"{symbol}{value:,.2f}"


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format number as percentage.
    
    Args:
        value: Number to format (0-100 or 0-1)
        decimals: Number of decimal places
        
    Returns:
        Formatted percentage string
    """
    if value <= 1:
        value = value * 100
    return f"{value:.{decimals}f}%"


def format_count(value: int) -> str:
    """Format large numbers with thousands separator.
    
    Args:
        value: Number to format
        
    Returns:
        Formatted number string
    """
    return f"{value:,}"


# ============================================================================
# METRIC CARDS
# ============================================================================

def metric_card(
    label: str,
    value: Any,
    delta: Optional[str] = None,
    icon: str = "📊",
    color: str = "primary",
    width: Optional[float] = None
) -> None:
    """Display a professional metric card (KPI).
    
    Args:
        label: Card title/label (e.g., "Match Rate")
        value: Main value to display (e.g., "95%")
        delta: Optional delta/change text (e.g., "+5%")
        icon: Optional emoji icon
        color: Color scheme (primary, success, error, warning)
        width: Optional column width factor
    """
    # HTML structure
    html = f"""
    <div class="metric-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
                <div class="metric-card-label">{label}</div>
                <div class="metric-card-value">{icon} {value}</div>
                {f'<div class="metric-card-delta">{delta}</div>' if delta else ''}
            </div>
        </div>
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)


def metric_row(metrics: List[Dict[str, Any]], columns: int = 4) -> None:
    """Display multiple metric cards in a row.
    
    Args:
        metrics: List of metric dicts with keys: label, value, delta, icon
        columns: Number of columns (1-4)
    """
    cols = st.columns(columns)
    
    for i, metric in enumerate(metrics):
        with cols[i % columns]:
            metric_card(
                label=metric.get("label", ""),
                value=metric.get("value", "-"),
                delta=metric.get("delta"),
                icon=metric.get("icon", "📊"),
            )


# ============================================================================
# STATUS BADGES
# ============================================================================

def status_badge(status: str, size: str = "normal") -> str:
    """Generate a status badge HTML.
    
    Args:
        status: Status value (MATCH, MISMATCH, MINOR_VARIANCE, MISSING_PROOF)
        size: Badge size (small, normal, large)
        
    Returns:
        HTML string for status badge
    """
    status_config = {
        "MATCH": {
            "icon": "✅",
            "label": "MATCH",
            "class": "badge-match"
        },
        "MISMATCH": {
            "icon": "❌",
            "label": "MISMATCH",
            "class": "badge-mismatch"
        },
        "MINOR_VARIANCE": {
            "icon": "⚠️",
            "label": "MINOR",
            "class": "badge-minor"
        },
        "MISSING_PROOF": {
            "icon": "❓",
            "label": "MISSING",
            "class": "badge-missing"
        },
        "ERROR": {
            "icon": "⚠️",
            "label": "ERROR",
            "class": "badge-missing"
        },
    }
    
    config = status_config.get(status, status_config["ERROR"])
    
    return f"""
    <span class="badge {config['class']}">
        {config['icon']} {config['label']}
    </span>
    """


def status_indicator(status: str, label: Optional[str] = None) -> None:
    """Display a status indicator with optional label.
    
    Args:
        status: Status value (success, error, warning)
        label: Optional additional label
    """
    status_config = {
        "success": {"icon": "✅", "class": "status-success", "text": "Success"},
        "error": {"icon": "❌", "class": "status-error", "text": "Error"},
        "warning": {"icon": "⚠️", "class": "status-warning", "text": "Warning"},
    }
    
    config = status_config.get(status, status_config["error"])
    final_label = label or config["text"]
    
    html = f"""
    <div class="status-indicator {config['class']}">
        {config['icon']} {final_label}
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)


# ============================================================================
# SIDEBAR COMPONENTS
# ============================================================================

def sidebar_header(title: str, icon: str = "📁") -> None:
    """Display a sidebar section header.
    
    Args:
        title: Section title
        icon: Icon emoji
    """
    st.markdown(f"### {icon} {title}")


def sidebar_section(title: str, content_fn, icon: str = "⚙️") -> None:
    """Create an organized sidebar section with header and collapsible content.
    
    Args:
        title: Section title
        content_fn: Callback function that renders the content
        icon: Icon emoji
    """
    with st.sidebar:
        st.markdown(f"#### {icon} {title}")
        content_fn()
        st.divider()


# ============================================================================
# TABLE & DATA DISPLAY
# ============================================================================

def audit_results_table(results: List[Dict[str, Any]]) -> None:
    """Display audit results in a professional table.
    
    Args:
        results: List of result dicts with keys:
            ag_code, name, reported, extracted, difference, status, confidence
    """
    # Format data for display
    display_data = []
    
    for result in results:
        display_data.append({
            "AG-Code": result.get("ag_code", ""),
            "Description": result.get("name", ""),
            "Reported": result.get("reported", ""),
            "Extracted": result.get("extracted", ""),
            "Difference": result.get("difference", ""),
            "Status": status_badge(result.get("status", "ERROR")),
            "Confidence": result.get("confidence", ""),
        })
    
    # Use Streamlit's native dataframe
    st.dataframe(
        display_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(width="medium"),
        }
    )


# ============================================================================
# CODE BLOCKS & TEXT DISPLAY
# ============================================================================

def code_block(
    content: str,
    language: str = "json",
    height: int = 300,
    copy_button: bool = True
) -> None:
    """Display code/text in a monospace, copyable block.
    
    Args:
        content: Content to display
        language: Language for syntax highlighting (json, python, sql, etc.)
        height: Height in pixels
        copy_button: Show copy button
    """
    col1, col2 = st.columns([1, 0.15]) if copy_button else (st.columns([1])[0], None)
    
    with col1:
        st.code(content, language=language, line_numbers=False)
    
    if copy_button and col2:
        with col2:
            if st.button("📋", key=f"copy_{id(content)}", help="Copy to clipboard"):
                st.toast("Copied to clipboard!", icon="✅")


def copyable_text_area(
    label: str,
    value: str,
    height: int = 300,
    key: Optional[str] = None
) -> str:
    """Display a text area with copy button.
    
    Args:
        label: Text area label
        value: Initial value
        height: Height in pixels
        key: Unique key for Streamlit
        
    Returns:
        Current text value
    """
    col1, col2 = st.columns([1, 0.12])
    
    with col1:
        text_value = st.text_area(
            label,
            value=value,
            height=height,
            key=key,
            disabled=False
        )
    
    with col2:
        st.write("")  # Spacer
        if st.button("📋", key=f"copy_{key}", help="Copy to clipboard"):
            st.toast("Copied! You can paste it now.", icon="✅")
    
    return text_value


# ============================================================================
# SECTION CONTAINERS
# ============================================================================

def section_container(title: str, icon: str = "📋") -> None:
    """Create a styled section container.
    
    Args:
        title: Section title
        icon: Icon emoji
    """
    st.markdown(f"## {icon} {title}")


def info_box(message: str, box_type: str = "info") -> None:
    """Display an informational box.
    
    Args:
        message: Message text
        box_type: Type of box (info, success, warning, error)
    """
    box_config = {
        "info": ("ℹ️", "info-alert"),
        "success": ("✅", "success-alert"),
        "warning": ("⚠️", "warning-alert"),
        "error": ("❌", "error-alert"),
    }
    
    icon, css_class = box_config.get(box_type, box_config["info"])
    
    html = f"""
    <div class="stAlert {css_class}">
        <p style="margin: 0;">
            <strong>{icon}</strong> {message}
        </p>
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)


# ============================================================================
# DIVIDERS & LAYOUT
# ============================================================================

def divider(spacing: int = 20) -> None:
    """Display a styled divider.
    
    Args:
        spacing: Spacing before/after divider in pixels
    """
    st.markdown(f'<div style="margin: {spacing}px 0; border-top: 1px solid #1E293B;"></div>', 
                unsafe_allow_html=True)


def spacer(height: int = 20) -> None:
    """Add vertical spacing.
    
    Args:
        height: Height in pixels
    """
    st.markdown(f'<div style="height: {height}px;"></div>', unsafe_allow_html=True)


# ============================================================================
# LOADING & PROGRESS
# ============================================================================

def loading_spinner(text: str = "Processing...") -> None:
    """Display a loading spinner with text.
    
    Args:
        text: Loading message
    """
    with st.spinner(text):
        pass


def progress_step(current: int, total: int, label: str = "") -> None:
    """Display a progress indicator showing current step.
    
    Args:
        current: Current step (1-indexed)
        total: Total steps
        label: Optional label for current step
    """
    progress = current / total
    
    html = f"""
    <div style="margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span style="font-size: 0.875rem; color: #CBD5E1;">
                Step {current} of {total}
            </span>
            <span style="font-size: 0.875rem; color: #94A3B8;">
                {label}
            </span>
        </div>
        <div style="width: 100%; height: 6px; background: #1E293B; border-radius: 3px; overflow: hidden;">
            <div style="width: {progress * 100}%; height: 100%; background: linear-gradient(90deg, #2563EB, #3B82F6); 
                        border-radius: 3px; box-shadow: 0 0 8px rgba(37, 99, 235, 0.4);"></div>
        </div>
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)


# ============================================================================
# AUDIT RESULT SUMMARY
# ============================================================================

def audit_summary_cards(summary: Dict[str, Any]) -> None:
    """Display audit summary with KPI cards.
    
    Args:
        summary: Summary dict with keys:
            match_rate, matched, mismatched, missing, total_difference, risk_level
    """
    metrics = [
        {
            "label": "Match Rate",
            "value": format_percentage(summary.get("match_rate", 0)),
            "delta": f"{summary.get('matched', 0)} matched",
            "icon": "📊"
        },
        {
            "label": "Total Variance",
            "value": format_currency(summary.get("total_difference", 0)),
            "delta": f"{summary.get('mismatched', 0)} mismatches",
            "icon": "💰"
        },
        {
            "label": "Risk Level",
            "value": summary.get("risk_level", "UNKNOWN"),
            "delta": f"{summary.get('missing', 0)} missing",
            "icon": "⚠️"
        },
        {
            "label": "Audit Duration",
            "value": f"{summary.get('duration', 0):.1f}s",
            "delta": "Processed",
            "icon": "⏱️"
        }
    ]
    
    metric_row(metrics, columns=4)


# ============================================================================
# FILE UPLOAD INTERFACE
# ============================================================================

def upload_pdf_section() -> Optional[Any]:
    """Display professional PDF upload interface.
    
    Returns:
        Uploaded file object or None
    """
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "📄 Upload Financial Document",
            type=["pdf"],
            help="WOZ beschikking, bank statement, hypotheek, etc.",
            key="pdf_uploader"
        )
    
    with col2:
        st.write("")  # Spacer
        st.caption("PDF files only")
    
    return uploaded_file


# ============================================================================
# AG-CODE INPUT
# ============================================================================

def ag_codes_input() -> Optional[Dict[str, float]]:
    """Display AG-code input interface with validation.
    
    Returns:
        Dictionary of {ag_code: amount} or None
    """
    info_box(
        "Enter the tax authority codes (AG-codes) you want to audit against extracted data.",
        box_type="info"
    )
    
    ag_input = st.text_area(
        "AG-Codes (JSON Format)",
        value='{\n    "AG3020": 50000,\n    "AG3030": 500000,\n    "AG3050": 100000\n}',
        height=120,
        help='Example: {"AG3020": 50000, "AG3050": 100000}',
        key="ag_codes_input"
    )
    
    try:
        import json
        ag_codes = json.loads(ag_input)
        st.success(f"✅ Parsed {len(ag_codes)} AG-codes")
        return ag_codes
    except json.JSONDecodeError as e:
        info_box(f"Invalid JSON format: {str(e)}", box_type="error")
        return None


# ============================================================================
# RISK LEVEL DISPLAY
# ============================================================================

def risk_level_indicator(risk_level: str) -> None:
    """Display risk level with color coding.
    
    Args:
        risk_level: Risk level (LOW, MEDIUM, HIGH, CRITICAL)
    """
    risk_config = {
        "LOW": {"icon": "🟢", "color": "#059669", "label": "Low Risk"},
        "MEDIUM": {"icon": "🟡", "color": "#D97706", "label": "Medium Risk"},
        "HIGH": {"icon": "🔴", "color": "#DC2626", "label": "High Risk"},
        "CRITICAL": {"icon": "🔴🔴", "color": "#DC2626", "label": "Critical Risk"},
    }
    
    config = risk_config.get(risk_level, risk_config["HIGH"])
    
    html = f"""
    <div style="
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        border-radius: 8px;
        background: rgba({int(config['color'][1:3], 16)}, {int(config['color'][3:5], 16)}, {int(config['color'][5:7], 16)}, 0.1);
        border: 1px solid {config['color']};
        color: {config['color']};
        font-weight: 600;
        font-size: 1.1rem;
    ">
        {config['icon']} {config['label']}
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)


# ============================================================================
# EXPORT BUTTONS
# ============================================================================

def export_buttons(json_data: str, file_name: str = "audit_results") -> None:
    """Display professional export buttons.
    
    Args:
        json_data: JSON string to export
        file_name: Export file name (without extension)
    """
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.download_button(
            label="📥 Download JSON",
            data=json_data,
            file_name=f"{file_name}.json",
            mime="application/json",
            use_container_width=True,
        )
    
    with col2:
        if st.button("📋 Copy to Clipboard", use_container_width=True):
            st.toast("Copied to clipboard!", icon="✅")
    
    with col3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

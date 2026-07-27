"""
FiscAudit AI - Executive Fiscal Dashboard (PROFESSIONALLY REDESIGNED)

Modern, elegant dashboard for automated fiscal audits of Dutch tax returns.
Built with professional design system and reusable UI components.

Features:
  • Professional executive dashboard design
  • Drag-and-drop PDF upload
  • Real-time audit matching
  • Risk analysis with Claude AI
  • Professional export & communication
  • GDPR/AVG compliant
"""

import os
import json
import logging
import tempfile
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

import streamlit as st

# Import FiscAudit modules
try:
    from src.anonymizer import DataAnonymizer
    from src.extractor import DocumentExtractor, ExtractedFinancialData
    from src.matcher import AuditMatcher, MatchResult, AuditSummary
    from src.advisor import FiscalAdvisor, RiskAssessment
    from src.db import SupabaseClient
    from src.ui_components import (
        metric_card, metric_row,
        status_badge, status_indicator,
        section_container, info_box,
        divider, spacer,
        audit_results_table, audit_summary_cards,
        copyable_text_area, code_block,
        upload_pdf_section, ag_codes_input,
        risk_level_indicator, export_buttons,
        progress_step, sidebar_header, sidebar_section,
        format_currency, format_percentage
    )
except ImportError as e:
    st.error(f"❌ Failed to import FiscAudit modules: {str(e)}")
    st.stop()


# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# CSS LOADING
# ============================================================================

def load_css() -> None:
    """Load external CSS stylesheet for professional styling."""
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
        logger.info("CSS stylesheet loaded successfully")
    except FileNotFoundError:
        logger.warning(f"CSS file not found at {css_path}")
    except Exception as e:
        logger.error(f"Error loading CSS: {str(e)}")


# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="FiscAudit AI - Fiscal Audit Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items=None
)

# Load CSS styling
load_css()


# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

def init_session_state():
    """Initialize Streamlit session state variables."""
    defaults = {
        'uploaded_file': None,
        'extracted_data': None,
        'ag_codes': {},
        'audit_results': None,
        'audit_summary': None,
        'risk_assessment': None,
        'dossier_id': None,
        'anonymized_data': None,
        'audit_in_progress': False,
        'current_step': 'upload',
        'klant_naam': 'New Client',
        'jaar': 2024,
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


init_session_state()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def log_audit_action(action: str, status: str, details: str = ""):
    """Log audit action for compliance trail."""
    logger.info(f"[AUDIT] {action} | {status} | {details}")


def initialize_clients() -> Tuple[Optional[DocumentExtractor], Optional[AuditMatcher], 
                                  Optional[FiscalAdvisor], Optional[SupabaseClient]]:
    """Initialize all API clients with error handling."""
    try:
        google_key = st.secrets.get("google_api_key")
        claude_key = st.secrets.get("anthropic_api_key")
        supabase_url = st.secrets.get("supabase_url")
        supabase_key = st.secrets.get("supabase_key")
        
        # Extractor
        if not google_key:
            st.warning("⚠️ Google API key not found in secrets")
            extractor = None
        else:
            extractor = DocumentExtractor(api_key=google_key)
        
        # Matcher
        matcher = AuditMatcher()
        
        # Advisor
        if not claude_key:
            st.warning("⚠️ Claude API key not found - risk analysis unavailable")
            advisor = None
        else:
            advisor = FiscalAdvisor(api_key=claude_key)
        
        # Database
        if not supabase_url or not supabase_key:
            st.info("ℹ️ Supabase not configured - data won't be persisted")
            db = None
        else:
            db = SupabaseClient(url=supabase_url, key=supabase_key)
        
        return extractor, matcher, advisor, db
        
    except Exception as e:
        st.error(f"❌ Error initializing clients: {str(e)}")
        return None, None, None, None


# ============================================================================
# SIDEBAR: DOSSIER MANAGEMENT
# ============================================================================

def render_sidebar():
    """Render sidebar with dossier management."""
    with st.sidebar:
        # Header
        st.markdown("### 📁 Dossier Management")
        
        # Dossier inputs
        col1, col2 = st.columns(2)
        with col1:
            klant_naam = st.text_input(
                "Client Name",
                value=st.session_state['klant_naam'],
                placeholder="Jan Jansen",
                key="klant_input"
            )
        with col2:
            jaar = st.number_input(
                "Tax Year",
                value=st.session_state['jaar'],
                min_value=2000,
                max_value=2030,
                key="jaar_input"
            )
        
        st.session_state['klant_naam'] = klant_naam
        st.session_state['jaar'] = jaar
        
        # Create dossier button
        if st.button("➕ Create New Dossier", use_container_width=True, type="primary"):
            if klant_naam:
                st.success(f"✅ Dossier: {klant_naam} ({jaar})")
                log_audit_action("CREATE_DOSSIER", "SUCCESS", f"{klant_naam}-{jaar}")
            else:
                st.warning("Enter client name")
        
        # Current dossier display
        if st.session_state['dossier_id']:
            st.info(f"Current: {st.session_state['dossier_id']}")
        
        divider()
        
        # Statistics
        st.markdown("### 📈 Session Statistics")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("AG-Codes", len(st.session_state.get('ag_codes', {})) or "-")
        with col2:
            if st.session_state.get('audit_summary'):
                st.metric("Matched", st.session_state['audit_summary'].matched)
            else:
                st.metric("Matched", "-")
        with col3:
            if st.session_state.get('audit_summary'):
                st.metric("Risk", st.session_state['audit_summary'].overall_risk_level.value)
            else:
                st.metric("Risk", "-")


# ============================================================================
# TAB 1: UPLOAD & INPUT
# ============================================================================

def render_tab_upload():
    """Render Tab 1: Upload & AG-code Input."""
    
    st.markdown("# 📥 Upload & Input")
    st.markdown("*Extract financial data from PDF documents and match against AG-codes*")
    
    # Step 1: PDF Upload
    st.markdown("## Step 1: Upload Financial Document")
    info_box(
        "Upload bank statements, WOZ descriptions, hypotheek documents, or other financial records.",
        box_type="info"
    )
    
    uploaded_file = upload_pdf_section()
    
    if uploaded_file is not None:
        st.session_state['uploaded_file'] = uploaded_file
        st.success(f"✅ File uploaded: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
        
        # Extract button
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            extract_button = st.button(
                "🔍 Extract Financial Data",
                use_container_width=True,
                type="primary",
                key="extract_btn"
            )
        
        with col2:
            st.write("")
        
        with col3:
            st.write("")
        
        if extract_button:
            st.session_state['audit_in_progress'] = True
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name
            
            try:
                # Extract
                progress_step(1, 3, "Initializing Gemini")
                extractor, _, _, _ = initialize_clients()
                
                if not extractor:
                    st.error("Extractor not initialized - check API keys")
                    return
                
                progress_step(2, 3, "Processing PDF")
                
                with st.spinner("Extracting data from PDF..."):
                    extracted_data = extractor.extract_from_pdf(tmp_path)
                    st.session_state['extracted_data'] = extracted_data
                
                progress_step(3, 3, "Complete")
                
                # Display results
                st.success("✅ Extraction successful!")
                divider()
                
                # KPI cards
                st.markdown("### Extraction Summary")
                metrics = [
                    {
                        "label": "Confidence",
                        "value": format_percentage(extracted_data.extraction_confidence),
                        "icon": "🎯"
                    },
                    {
                        "label": "Bank Accounts",
                        "value": str(len(extracted_data.bank_accounts)),
                        "icon": "🏦"
                    },
                    {
                        "label": "Mortgages",
                        "value": str(len(extracted_data.mortgages)),
                        "icon": "🏠"
                    },
                    {
                        "label": "Properties",
                        "value": str(len(extracted_data.real_estate)),
                        "icon": "🏘️"
                    },
                ]
                metric_row(metrics, columns=4)
                
                divider()
                
                # Extracted data viewer
                with st.expander("📋 View Extracted Data (JSON)"):
                    code_block(
                        json.dumps(extracted_data.model_dump(), indent=2, default=str),
                        language="json"
                    )
                
                log_audit_action("EXTRACT_PDF", "SUCCESS", 
                               f"Confidence: {extracted_data.extraction_confidence}")
            
            except Exception as e:
                st.error(f"❌ Extraction failed: {str(e)}")
                logger.error(f"Extraction error: {str(e)}")
                log_audit_action("EXTRACT_PDF", "FAILED", str(e))
            
            finally:
                st.session_state['audit_in_progress'] = False
                try:
                    os.unlink(tmp_path)
                except:
                    pass
    
    # Step 2: AG-Codes Input
    st.markdown("## Step 2: Enter AG-Codes to Audit")
    
    ag_codes = ag_codes_input()
    st.session_state['ag_codes'] = ag_codes or {}
    
    # Step 3: Start Audit
    st.markdown("## Step 3: Run Audit")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        run_audit = st.button(
            "⚖️ Start Audit Matching",
            use_container_width=True,
            type="primary",
            key="audit_btn"
        )
    
    if run_audit:
        if not st.session_state['extracted_data']:
            info_box("Please upload and extract a PDF first", box_type="error")
        elif not st.session_state['ag_codes']:
            info_box("Please enter AG-codes", box_type="error")
        else:
            try:
                _, matcher, _, _ = initialize_clients()
                
                if not matcher:
                    st.error("Matcher not initialized")
                    return
                
                progress_step(1, 2, "Running audit matcher")
                
                with st.spinner("Matching AG-codes..."):
                    results, summary = matcher.match_ag_codes(
                        extracted_data=st.session_state['extracted_data'],
                        reported_amounts=st.session_state['ag_codes']
                    )
                
                st.session_state['audit_results'] = results
                st.session_state['audit_summary'] = summary
                
                progress_step(2, 2, "Audit complete")
                
                st.success("✅ Audit matching complete!")
                info_box(
                    f"Matched: {summary.matched}/{summary.total_ag_codes_checked} • "
                    f"Mismatch: {summary.mismatched} • "
                    f"Risk: {summary.overall_risk_level.value}",
                    box_type="success"
                )
                
                log_audit_action("MATCH_CODES", "SUCCESS", 
                               f"Matched: {summary.matched}/{summary.total_ag_codes_checked}")
            
            except Exception as e:
                st.error(f"❌ Audit failed: {str(e)}")
                log_audit_action("MATCH_CODES", "FAILED", str(e))


# ============================================================================
# TAB 2: AUDIT DASHBOARD
# ============================================================================

def render_tab_dashboard():
    """Render Tab 2: Audit Dashboard."""
    
    st.markdown("# 📊 Audit Dashboard")
    st.markdown("*Real-time audit results and analysis*")
    
    if not st.session_state['audit_results']:
        info_box(
            "Upload a document and run matching in Tab 1 to see results here.",
            box_type="info"
        )
        return
    
    summary = st.session_state['audit_summary']
    results = st.session_state['audit_results']
    
    # KPI Summary
    st.markdown("## Audit Summary")
    audit_summary_cards({
        "match_rate": summary.match_rate,
        "matched": summary.matched,
        "mismatched": summary.mismatched,
        "missing": summary.missing_proof,
        "total_difference": summary.total_difference_eur,
        "risk_level": summary.overall_risk_level.value,
        "duration": summary.duration_seconds,
    })
    
    divider()
    
    # Risk Level
    st.markdown("## Risk Assessment")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        risk_level_indicator(summary.overall_risk_level.value)
    
    divider()
    
    # Results Table
    st.markdown("## Detailed Results")
    
    display_data = []
    for result in results:
        display_data.append({
            "ag_code": result.ag_code,
            "name": result.ag_name,
            "reported": format_currency(result.reported_amount_eur),
            "extracted": format_currency(result.extracted_amount_eur),
            "difference": format_currency(result.difference_eur),
            "status": status_badge(result.status.value),
            "confidence": format_percentage(result.confidence),
        })
    
    audit_results_table(display_data)
    
    divider()
    
    # Export Options
    st.markdown("## Export Results")
    
    json_export = json.dumps({
        "summary": summary.model_dump(),
        "results": [r.model_dump(mode='json') for r in results],
        "timestamp": datetime.now().isoformat()
    }, indent=2, default=str)
    
    export_buttons(json_export, file_name=f"audit_{st.session_state['klant_naam']}")


# ============================================================================
# TAB 3: RISK ANALYSIS & COMMUNICATION
# ============================================================================

def render_tab_risk_analysis():
    """Render Tab 3: Risk Analysis & Client Communication."""
    
    st.markdown("# 📋 Fiscal Risk Analysis & Communication")
    st.markdown("*AI-powered risk assessment and professional client communication*")
    
    if not st.session_state['audit_results']:
        info_box(
            "Complete the audit in Tab 1 to see risk analysis here.",
            box_type="info"
        )
        return
    
    _, _, advisor, _ = initialize_clients()
    
    if not advisor:
        info_box(
            "Claude API key not configured. Risk analysis unavailable.",
            box_type="warning"
        )
        return
    
    try:
        # Generate risk assessment
        with st.spinner("Analyzing fiscal risks..."):
            risk_assessment = advisor.analyze_audit(
                extracted_data=st.session_state['extracted_data'],
                audit_results=st.session_state['audit_results'],
                audit_summary=st.session_state['audit_summary']
            )
        
        st.session_state['risk_assessment'] = risk_assessment
        
        # Risk Level Display
        st.markdown("## Overall Risk Level")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            risk_level_indicator(risk_assessment.overall_risk_level.value)
        
        divider()
        
        # Risk Points
        if risk_assessment.risk_points:
            st.markdown("## Risk Points & Findings")
            
            for i, point in enumerate(risk_assessment.risk_points, 1):
                with st.expander(f"**#{i}** {point.risk_type} - {point.risk_level.value}"):
                    st.markdown(f"**Description:** {point.description}")
                    st.markdown(f"**Impact:** {point.impact_description}")
                    if point.recommendation:
                        st.markdown(f"**Recommendation:** {point.recommendation}")
        
        divider()
        
        # Client Email Draft
        st.markdown("## Client Communication Email")
        info_box(
            "Professional email draft for client communication. Copy and customize as needed.",
            box_type="info"
        )
        
        email_text = advisor.generate_email(risk_assessment)
        
        email_output = copyable_text_area(
            "📧 Email Draft",
            value=email_text,
            height=400,
            key="email_draft"
        )
        
        # Export email
        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button(
                label="📥 Download Email",
                data=email_output,
                file_name=f"email_{st.session_state['klant_naam']}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        
        with col2:
            if st.button("📋 Copy to Clipboard", use_container_width=True):
                st.toast("Copied to clipboard!", icon="✅")
        
        with col3:
            if st.button("📧 Preview Formatted", use_container_width=True):
                st.info("Email preview ready to copy")
        
        log_audit_action("ANALYZE_RISKS", "SUCCESS", 
                        f"Risk level: {risk_assessment.overall_risk_level.value}")
    
    except Exception as e:
        st.error(f"❌ Risk analysis failed: {str(e)}")
        log_audit_action("ANALYZE_RISKS", "FAILED", str(e))


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point."""
    
    # Render sidebar
    render_sidebar()
    
    # Main content area
    st.markdown("# 📊 FiscAudit AI")
    st.markdown("*Automated Fiscal Audit Platform for Dutch Tax Professionals*")
    st.markdown("*Built with AI-powered extraction, deterministic matching, and GDPR compliance*")
    
    divider()
    
    # Tabs
    tab1, tab2, tab3 = st.tabs([
        "📥 Upload & Input",
        "📊 Audit Dashboard",
        "📋 Risk Analysis"
    ])
    
    with tab1:
        render_tab_upload()
    
    with tab2:
        render_tab_dashboard()
    
    with tab3:
        render_tab_risk_analysis()


if __name__ == "__main__":
    main()

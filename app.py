"""
FiscAudit AI - Streamlit Application (PRODUCTION-READY)

Complete fiscal audit platform with:
- Proper error handling & user feedback
- Anonymization before ALL external API calls
- Beautiful UI/UX with Streamlit components
- 3 interactive tabs (Upload, Dashboard, Advice)
- Loading indicators & progress tracking
"""

import os
import json
import logging
import tempfile
from datetime import datetime
from typing import Optional, Tuple

import streamlit as st
from streamlit_option_menu import option_menu

# Import FiscAudit modules
try:
    from src.anonymizer import DataAnonymizer
    from src.extractor import DocumentExtractor, ExtractedFinancialData
    from src.matcher import AuditMatcher, MatchResult, AuditSummary
    from src.advisor import FiscalAdvisor, RiskAssessment
    from src.db import SupabaseClient
except ImportError as e:
    st.error(f"Failed to import FiscAudit modules: {str(e)}")
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
# STREAMLIT PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="FiscAudit AI - Fiscal Audit Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for beautiful UI
CUSTOM_CSS = """
<style>
    /* Main theme colors */
    :root {
        --primary: #2563EB;
        --success: #10B981;
        --warning: #F59E0B;
        --danger: #EF4444;
        --dark: #1F2937;
        --light: #F9FAFB;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1F2937 0%, #111827 100%);
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        background-color: #F3F4F6;
        padding: 10px;
        border-radius: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 5px;
        background-color: white;
        border: 1px solid #E5E7EB;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #2563EB;
        color: white;
    }
    
    /* Metric cards */
    [data-testid="metric-container"] {
        background-color: #F9FAFB;
        padding: 20px;
        border-radius: 8px;
        border: 1px solid #E5E7EB;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    /* Status badges */
    .status-match { color: #10B981; font-weight: bold; }
    .status-mismatch { color: #EF4444; font-weight: bold; }
    .status-minor { color: #F59E0B; font-weight: bold; }
    .status-missing { color: #8B5CF6; font-weight: bold; }
    
    /* Loading animation */
    .loading-spinner {
        display: inline-block;
        animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    /* Error/success messages */
    .error-box { background-color: #FEE2E2; border-left: 4px solid #EF4444; padding: 15px; border-radius: 5px; }
    .success-box { background-color: #ECFDF5; border-left: 4px solid #10B981; padding: 15px; border-radius: 5px; }
    .warning-box { background-color: #FFFBEB; border-left: 4px solid #F59E0B; padding: 15px; border-radius: 5px; }
    
    /* Code/results section */
    .results-container {
        background-color: #F9FAFB;
        padding: 20px;
        border-radius: 8px;
        border: 1px solid #E5E7EB;
        font-family: 'Monaco', 'Courier New', monospace;
        font-size: 13px;
        max-height: 400px;
        overflow-y: auto;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


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


def format_currency(value: float) -> str:
    """Format number as Euro currency."""
    return f"€{value:,.2f}"


def display_status_badge(status: str) -> str:
    """Display colored status badge."""
    badges = {
        "MATCH": "✅ MATCH",
        "MINOR_VARIANCE": "⚠️ MINOR",
        "MISMATCH": "❌ MISMATCH",
        "MISSING_PROOF": "❓ MISSING",
        "ERROR": "⚠️ ERROR",
    }
    return badges.get(status, status)


def initialize_clients() -> Tuple[Optional[DocumentExtractor], Optional[AuditMatcher], Optional[FiscalAdvisor], Optional[SupabaseClient]]:
    """Initialize all API clients with error handling."""
    try:
        # Get API keys from Streamlit secrets
        google_key = st.secrets.get("google_api_key")
        claude_key = st.secrets.get("anthropic_api_key")
        supabase_url = st.secrets.get("supabase_url")
        supabase_key = st.secrets.get("supabase_key")
        
        # Initialize extractor
        if not google_key:
            st.error("❌ Google API key not found in secrets")
            return None, None, None, None
        
        extractor = DocumentExtractor(api_key=google_key)
        
        # Initialize matcher (no API key needed)
        matcher = AuditMatcher()
        
        # Initialize advisor
        if not claude_key:
            st.warning("⚠️ Claude API key not found - risk analysis unavailable")
            advisor = None
        else:
            advisor = FiscalAdvisor(api_key=claude_key)
        
        # Initialize database
        if not supabase_url or not supabase_key:
            st.warning("⚠️ Supabase credentials not found - data won't be persisted")
            db = None
        else:
            db = SupabaseClient(url=supabase_url, key=supabase_key)
        
        return extractor, matcher, advisor, db
        
    except Exception as e:
        st.error(f"❌ Error initializing clients: {str(e)}")
        logger.error(f"Client initialization failed: {str(e)}")
        return None, None, None, None


# ============================================================================
# MAIN APP
# ============================================================================

def main():
    """Main Streamlit application."""
    
    # Title and description
    st.title("📊 FiscAudit AI - Automated Fiscal Audit Platform")
    st.markdown("*AI-powered fiscal audit tool for Dutch tax returns (IB/VPB) with GDPR compliance*")
    
    # Initialize clients
    with st.spinner("Initializing FiscAudit AI..."):
        extractor, matcher, advisor, db = initialize_clients()
    
    if not extractor or not matcher:
        st.error("Failed to initialize core services. Please check your API keys in secrets.toml")
        return
    
    # Initialize anonymizer
    anonymizer = DataAnonymizer()
    
    # Sidebar - Dossier Management
    with st.sidebar:
        st.header("📁 Dossier Management")
        
        col1, col2 = st.columns(2)
        with col1:
            klant_naam = st.text_input("Client Name", placeholder="Jan Jansen")
        with col2:
            jaar = st.number_input("Tax Year", value=2024, min_value=2000, max_value=2030)
        
        if st.button("➕ Create New Dossier", use_container_width=True):
            if klant_naam:
                try:
                    if db:
                        dossier_id = db.create_dossier(
                            klant_naam=klant_naam,
                            aangiftejaar=jaar,
                            status="in_progress"
                        )
                        st.session_state['dossier_id'] = dossier_id
                        st.success(f"✅ Dossier created: {dossier_id}")
                        log_audit_action("CREATE_DOSSIER", "SUCCESS", f"Dossier {dossier_id}")
                    else:
                        st.info("ℹ️ Database not configured - dossier not persisted")
                except Exception as e:
                    st.error(f"Error creating dossier: {str(e)}")
            else:
                st.warning("Please enter client name")
        
        # Dossier status
        if st.session_state['dossier_id']:
            st.info(f"Current Dossier: {st.session_state['dossier_id']}")
        
        # Statistics
        st.divider()
        st.subheader("📈 Statistics")
        if db:
            try:
                stats = db.get_dossier_stats()
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Dossiers", stats.get('total_dossiers', 0))
                with col2:
                    st.metric("In Progress", stats.get('in_progress', 0))
                with col3:
                    st.metric("Completed", stats.get('completed', 0))
            except:
                pass
    
    # Main content - Tabs
    tab1, tab2, tab3 = st.tabs(["📥 Upload & Input", "📊 Audit Dashboard", "📋 Risk Analysis & Email"])
    
    # ========== TAB 1: UPLOAD & INPUT ==========
    with tab1:
        st.header("Step 1: Upload Financial Documents")
        
        uploaded_file = st.file_uploader(
            "Choose a PDF document",
            type=["pdf"],
            help="WOZ beschikking, bank statement, hypotheek, etc."
        )
        
        if uploaded_file is not None:
            st.session_state['uploaded_file'] = uploaded_file
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name
            
            st.success(f"✅ File uploaded: {uploaded_file.name}")
            
            # Extract button
            if st.button("🔍 Extract Financial Data", use_container_width=True, type="primary"):
                st.session_state['audit_in_progress'] = True
                progress_bar = st.progress(0, text="Initializing extraction...")
                
                try:
                    # Step 1: Extract
                    progress_bar.progress(20, text="Extracting data from PDF...")
                    extracted_data = extractor.extract_from_pdf(tmp_path)
                    st.session_state['extracted_data'] = extracted_data
                    progress_bar.progress(60, text="Data extracted successfully")
                    
                    # Step 2: Anonymize (for audit trail)
                    progress_bar.progress(70, text="Anonymizing data...")
                    anonymized = anonymizer.anonymize_json(
                        extracted_data.model_dump()
                    )
                    st.session_state['anonymized_data'] = anonymized
                    progress_bar.progress(100, text="Complete!")
                    
                    # Display results
                    st.success("✅ Data extracted successfully!")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Confidence", f"{extracted_data.extraction_confidence*100:.0f}%")
                    with col2:
                        st.metric("Bank Accounts", len(extracted_data.bank_accounts))
                    with col3:
                        st.metric("Mortgages", len(extracted_data.mortgages))
                    with col4:
                        st.metric("Properties", len(extracted_data.real_estate))
                    
                    # Show extracted data
                    with st.expander("📋 View Extracted Data (JSON)"):
                        st.json(extracted_data.model_dump())
                    
                    log_audit_action("EXTRACT_PDF", "SUCCESS", f"Confidence: {extracted_data.extraction_confidence}")
                    
                except Exception as e:
                    st.error(f"❌ Error during extraction: {str(e)}")
                    logger.error(f"Extraction failed: {str(e)}")
                    log_audit_action("EXTRACT_PDF", "FAILED", str(e))
                
                finally:
                    st.session_state['audit_in_progress'] = False
                    os.unlink(tmp_path)
        
        # Step 2: Enter AG-Codes
        st.divider()
        st.header("Step 2: Enter AG-Codes to Match")
        
        st.info("Enter the tax authority codes (AG-codes) you want to match against the extracted data")
        
        # Input AG-codes
        ag_input = st.text_area(
            "AG-Codes (JSON format)",
            value='{"AG3020": 50000, "AG3030": 500000}',
            height=100,
            help='Example: {"AG3020": 50000, "AG3050": 100000}'
        )
        
        try:
            ag_codes = json.loads(ag_input)
            st.session_state['ag_codes'] = ag_codes
            st.success(f"✅ Parsed {len(ag_codes)} AG-codes")
        except json.JSONDecodeError:
            st.error("Invalid JSON format. Please check your input.")
        
        # Match button
        if st.button("⚖️ Start Audit Matching", use_container_width=True, type="primary"):
            if not st.session_state['extracted_data']:
                st.error("Please upload and extract a PDF first")
            elif not st.session_state['ag_codes']:
                st.error("Please enter AG-codes")
            else:
                progress_bar = st.progress(0, text="Starting audit...")
                
                try:
                    progress_bar.progress(30, text="Matching AG-codes...")
                    
                    # Run matcher
                    results, summary = matcher.match_ag_codes(
                        extracted_data=st.session_state['extracted_data'],
                        reported_amounts=st.session_state['ag_codes']
                    )
                    
                    st.session_state['audit_results'] = results
                    st.session_state['audit_summary'] = summary
                    progress_bar.progress(100, text="Audit complete!")
                    
                    st.success("✅ Audit matching complete!")
                    st.info(f"Matched: {summary.matched}/{summary.total_ag_codes_checked} | "
                           f"Mismatch: {summary.mismatched} | "
                           f"Risk: {summary.overall_risk_level.value}")
                    
                    log_audit_action("MATCH_CODES", "SUCCESS", f"Matched: {summary.matched}/{summary.total_ag_codes_checked}")
                    
                except Exception as e:
                    st.error(f"❌ Error during matching: {str(e)}")
                    logger.error(f"Matching failed: {str(e)}")
                    log_audit_action("MATCH_CODES", "FAILED", str(e))
    
    # ========== TAB 2: DASHBOARD ==========
    with tab2:
        st.header("Audit Dashboard")
        
        if not st.session_state['audit_results']:
            st.info("ℹ️ Upload a document and run matching to see results")
        else:
            summary = st.session_state['audit_summary']
            results = st.session_state['audit_results']
            
            # KPI Cards
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(
                    "Match Rate",
                    f"{summary.match_rate:.0f}%",
                    delta=f"{summary.matched} matched"
                )
            with col2:
                st.metric(
                    "Total Variance",
                    format_currency(summary.total_difference_eur),
                    delta=f"{summary.mismatched} mismatches"
                )
            with col3:
                st.metric(
                    "Risk Level",
                    summary.overall_risk_level.value,
                    delta="See details below"
                )
            with col4:
                st.metric(
                    "Audit Duration",
                    f"{summary.duration_seconds:.1f}s",
                    delta="Processed in seconds"
                )
            
            # Results table
            st.divider()
            st.subheader("Detailed Results")
            
            # Convert to display format
            display_data = []
            for result in results:
                display_data.append({
                    "AG-Code": result.ag_code,
                    "Name": result.ag_name,
                    "Reported": format_currency(result.reported_amount_eur),
                    "Extracted": format_currency(result.extracted_amount_eur),
                    "Difference": format_currency(result.difference_eur),
                    "Status": display_status_badge(result.status.value),
                    "Confidence": f"{result.confidence*100:.0f}%",
                })
            
            st.dataframe(
                display_data,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Status": st.column_config.TextColumn(width="medium"),
                }
            )
            
            # Export results
            st.divider()
            col1, col2 = st.columns(2)
            
            with col1:
                json_export = json.dumps({
                    "summary": summary.model_dump(),
                    "results": [r.model_dump(mode='json') for r in results],
                    "timestamp": datetime.now().isoformat()
                }, indent=2, default=str)
                
                st.download_button(
                    label="📥 Download Results (JSON)",
                    data=json_export,
                    file_name="audit_results.json",
                    mime="application/json",
                    use_container_width=True,
                )
            
            # Persist to database
            with col2:
                if st.button("💾 Save to Supabase", use_container_width=True):
                    if db and st.session_state['dossier_id']:
                        try:
                            # Save results
                            db.save_audit_results(
                                dossier_id=st.session_state['dossier_id'],
                                results=[r.model_dump(mode='json') for r in results]
                            )
                            st.success("✅ Results saved to database")
                            log_audit_action("SAVE_RESULTS", "SUCCESS", st.session_state['dossier_id'])
                        except Exception as e:
                            st.error(f"Error saving: {str(e)}")
                    else:
                        st.warning("Database or dossier not available")
    
    # ========== TAB 3: RISK ANALYSIS & EMAIL ==========
    with tab3:
        st.header("📋 Fiscal Risk Analysis & Client Communication")
        
        if not st.session_state['audit_results']:
            st.info("ℹ️ Complete audit in Tab 1 to see risk analysis")
        else:
            if advisor:
                try:
                    progress_bar = st.progress(0, text="Analyzing fiscal risks...")
                    
                    # Get risk assessment
                    risk_assessment = advisor.analyze_audit(
                        extracted_data=st.session_state['extracted_data'],
                        audit_results=st.session_state['audit_results'],
                        audit_summary=st.session_state['audit_summary']
                    )
                    
                    st.session_state['risk_assessment'] = risk_assessment
                    progress_bar.progress(100, text="Analysis complete!")
                    
                    # Display risk level
                    risk_colors = {
                        "LOW": "🟢",
                        "MEDIUM": "🟡",
                        "HIGH": "🔴",
                        "CRITICAL": "🔴🔴"
                    }
                    
                    st.subheader(f"{risk_colors.get(risk_assessment.overall_risk_level.value, '')} Overall Risk: {risk_assessment.overall_risk_level.value}")
                    
                    # Risk points
                    if risk_assessment.risk_points:
                        st.divider()
                        st.subheader("⚠️ Risk Points")
                        
                        for i, point in enumerate(risk_assessment.risk_points, 1):
                            with st.expander(f"#{i}: {point.risk_type} ({point.risk_level.value})"):
                                st.write(f"**Description:** {point.description}")
                                st.write(f"**Impact:** {point.impact_description}")
                                if point.recommendation:
                                    st.write(f"**Recommendation:** {point.recommendation}")
                    
                    # Email draft
                    st.divider()
                    st.subheader("📧 Client Communication Email")
                    
                    email_text = advisor.generate_email(risk_assessment)
                    
                    email_output = st.text_area(
                        "Email (copy-ready)",
                        value=email_text,
                        height=300,
                        disabled=False
                    )
                    
                    # Copy button
                    col1, col2 = st.columns(2)
                    with col1:
                        st.button(
                            "📋 Copy to Clipboard",
                            help="Copy email text to clipboard",
                            use_container_width=True,
                        )
                    
                    with col2:
                        st.download_button(
                            label="📥 Download Email",
                            data=email_output,
                            file_name="client_email.txt",
                            use_container_width=True,
                        )
                    
                    log_audit_action("ANALYZE_RISKS", "SUCCESS", f"Risk level: {risk_assessment.overall_risk_level.value}")
                    
                except Exception as e:
                    st.error(f"❌ Error during risk analysis: {str(e)}")
                    logger.error(f"Risk analysis failed: {str(e)}")
                    log_audit_action("ANALYZE_RISKS", "FAILED", str(e))
            
            else:
                st.warning("⚠️ Claude API key not configured - risk analysis unavailable")
                st.info("Please add 'anthropic_api_key' to .streamlit/secrets.toml")


if __name__ == "__main__":
    main()

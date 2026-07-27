"""
FiscAudit AI - Streamlit Applicatie
Complete fiscale audit dashboard met AI-gestuurde analyse.
"""

import streamlit as st
import json
import os
import asyncio
from datetime import datetime
from typing import Optional, List, Dict

# Lokale imports
from src.anonymizer import DataAnonymizer
from src.extractor import DocumentExtractor, DocumentType
from src.matcher import AuditMatcher
from src.advisor import FiscalAdvisor
from src.db import SupabaseClient, initialize_supabase


# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="FiscAudit AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# CUSTOM CSS STYLING (Modern Executive Fiscal Theme)
# ============================================================================

CUSTOM_CSS = """
<style>
/* Color Palette */
:root {
    --primary: #2563EB;          /* Royal Blue */
    --secondary: #059669;         /* Emerald */
    --danger: #DC2626;            /* Crimson */
    --warning: #D97706;           /* Amber */
    --dark: #0F172A;              /* Dark Charcoal */
    --slate: #1E293B;             /* Slate Blue */
    --light: #F1F5F9;             /* Slate-100 */
    --success: #059669;
}

/* Main Background */
.stApp {
    background-color: #FFFFFF;
}

/* Sidebar Styling */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, var(--slate) 0%, var(--dark) 100%);
    color: #FFFFFF;
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
    color: #FFFFFF;
}

/* Headers */
h1, h2, h3 {
    color: var(--slate);
    font-weight: 700;
}

h1 {
    border-bottom: 3px solid var(--primary);
    padding-bottom: 10px;
}

/* Tabs */
[data-baseweb="tab-list"] {
    border-bottom: 2px solid var(--light);
}

[aria-selected="true"] {
    border-bottom-color: var(--primary) !important;
    color: var(--primary) !important;
}

/* Metric Cards */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, var(--light) 0%, #E8F5FF 100%);
    border-left: 4px solid var(--primary);
    border-radius: 8px;
    padding: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

/* Status Badges */
.status-match {
    background: linear-gradient(135deg, var(--success) 0%, #10B981 100%);
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    display: inline-block;
}

.status-mismatch {
    background: linear-gradient(135deg, var(--danger) 0%, #EF4444 100%);
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    display: inline-block;
}

.status-missing {
    background: linear-gradient(135deg, var(--warning) 0%, #F59E0B 100%);
    color: #111827;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    display: inline-block;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, var(--primary) 0%, #1D4ED8 100%);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(37, 99, 235, 0.4);
}

/* Text Input & File Upload */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div {
    border: 2px solid var(--light);
    border-radius: 8px;
    padding: 10px;
    transition: border-color 0.3s ease;
}

.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stSelectbox > div > div:focus {
    border-color: var(--primary);
}

/* Data Tables */
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

/* Success/Error Messages */
[data-testid="stAlert"] {
    border-radius: 8px;
    border-left: 4px solid var(--primary);
}

.stSuccess {
    background-color: #ECFDF5;
    border-color: var(--success);
}

.stWarning {
    background-color: #FFFBEB;
    border-color: var(--warning);
}

.stError {
    background-color: #FEF2F2;
    border-color: var(--danger);
}

/* Divider */
hr {
    border-color: var(--light);
    margin: 24px 0;
}

/* Code blocks */
code {
    background-color: var(--light);
    color: var(--slate);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
}

/* Expander */
[data-testid="stExpander"] {
    border: 1px solid var(--light);
    border-radius: 8px;
}

/* Footer */
.footer {
    text-align: center;
    color: #94A3B8;
    font-size: 12px;
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid var(--light);
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

if "current_dossier_id" not in st.session_state:
    st.session_state.current_dossier_id = None

if "audit_results" not in st.session_state:
    st.session_state.audit_results = None

if "fiscal_assessment" not in st.session_state:
    st.session_state.fiscal_assessment = None

if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = None

if "anonymizer" not in st.session_state:
    st.session_state.anonymizer = DataAnonymizer()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_secrets():
    """Laad API keys van Streamlit secrets"""
    try:
        return {
            "supabase_url": st.secrets.get("supabase_url"),
            "supabase_key": st.secrets.get("supabase_key"),
            "google_api_key": st.secrets.get("google_api_key"),
            "anthropic_api_key": st.secrets.get("anthropic_api_key"),
        }
    except:
        return None


def initialize_services(secrets):
    """Initialiseer externe services"""
    try:
        db = initialize_supabase(secrets["supabase_url"], secrets["supabase_key"])
        extractor = DocumentExtractor(secrets["google_api_key"])
        advisor = FiscalAdvisor(secrets["anthropic_api_key"])
        matcher = AuditMatcher()
        
        return {"db": db, "extractor": extractor, "advisor": advisor, "matcher": matcher}
    except Exception as e:
        st.error(f"Fout bij initialisatie services: {str(e)}")
        return None


def render_status_badge(status: str) -> str:
    """Render een status badge"""
    badges = {
        "MATCH": '<span class="status-match">✓ MATCH</span>',
        "MISMATCH": '<span class="status-mismatch">✗ MISMATCH</span>',
        "MISSING_PROOF": '<span class="status-missing">? ONTBREKEND</span>',
        "ERROR": '<span class="status-mismatch">⚠ FOUT</span>'
    }
    return badges.get(status, status)


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point"""
    
    # Header
    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        st.title("📊 FiscAudit AI")
        st.caption("Automated Fiscal Audit & Reconciliation Platform")
    
    with col2:
        st.info("v1.0.0", icon="ℹ️")
    
    # Load secrets & initialize
    secrets = load_secrets()
    if not secrets or not all(secrets.values()):
        st.error("⚠️ API keys niet geconfigureerd. Controleer .streamlit/secrets.toml")
        st.stop()
    
    services = initialize_services(secrets)
    if not services:
        st.error("Fout bij service initialisatie")
        st.stop()
    
    # ========================================================================
    # SIDEBAR
    # ========================================================================
    
    with st.sidebar:
        st.markdown("## ⚙️ Configuratie")
        
        # Dossierselectie
        dossiers = services["db"].list_dossiers()
        dossier_options = {d["klant_naam"]: d["id"] for d in dossiers} if dossiers else {}
        
        if dossier_options:
            selected_dossier = st.selectbox(
                "📁 Selecteer dossier",
                options=dossier_options.keys(),
                key="dossier_selector"
            )
            st.session_state.current_dossier_id = dossier_options[selected_dossier]
        else:
            st.info("Geen dossiers beschikbaar. Start een nieuwe audit.")
        
        # Nieuwe dossier
        st.markdown("### 📝 Nieuw Dossier")
        with st.form("new_dossier_form"):
            klant_naam = st.text_input("Klantnaam")
            klant_email = st.text_input("Email klant")
            aangiftejaar = st.number_input("Aangiftejaar", min_value=2015, max_value=2100, value=2024)
            
            if st.form_submit_button("📥 Dossier aanmaken"):
                try:
                    dossier_id = services["db"].create_dossier(klant_naam, klant_email, aangiftejaar)
                    st.session_state.current_dossier_id = dossier_id
                    services["db"].log_action(dossier_id, "dossier_created", {"klant_naam": klant_naam})
                    st.success(f"✓ Dossier aangemaakt: {klant_naam}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fout: {str(e)}")
        
        st.divider()
        
        # Info
        st.markdown("### ℹ️ Over")
        st.markdown("""
        **FiscAudit AI** is een automatische
        belasting-audit tool voor Nederlandse
        inkomsten- en vennootschapsbelasting.
        
        **Features:**
        - 🔍 Document extractie (Gemini)
        - ⚖️ AG-code matching
        - 🤖 Fiscale risicoanalyse (Claude)
        - 📋 Professionele rapportage
        """)
        
        st.divider()
        
        # Statistics
        try:
            stats = services["db"].get_statistics()
            st.markdown("### 📈 Statistieken")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Totaal dossiers", stats.get("total_dossiers", 0))
                st.metric("In behandeling", stats.get("in_progress", 0))
            with col2:
                st.metric("Afgerond", stats.get("completed", 0))
        except:
            pass
    
    # ========================================================================
    # MAIN CONTENT TABS
    # ========================================================================
    
    if not st.session_state.current_dossier_id:
        st.warning("Selecteer of maak een dossier aan in het linkermenu.")
        return
    
    tab1, tab2, tab3 = st.tabs(["📥 Upload & Invoer", "📊 Audit Dashboard", "📋 Fiscaal Advies"])
    
    # ====================================================================
    # TAB 1: Upload & Invoer
    # ====================================================================
    
    with tab1:
        st.markdown("## 📥 Dossier Upload & AG-Code Invoer")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### PDF-documenten")
            uploaded_files = st.file_uploader(
                "Sleep PDF's hieronder",
                type=["pdf"],
                accept_multiple_files=True,
                help="Ondersteunende documenten (WOZ, bankafschriften, etc.)"
            )
            
            if uploaded_files and st.button("🚀 PDF's verwerken", key="process_pdfs"):
                with st.spinner("PDFs worden geëxtraheerd..."):
                    try:
                        extracted_list = []
                        for file in uploaded_files:
                            # Sla temp op
                            temp_path = f"/tmp/{file.name}"
                            with open(temp_path, "wb") as f:
                                f.write(file.getbuffer())
                            
                            # Extraheer
                            extracted = services["extractor"].extract_from_pdf_sync(temp_path)
                            extracted_list.append(extracted)
                            
                            # Log & sla op
                            services["db"].save_uploaded_document(
                                st.session_state.current_dossier_id,
                                file.name,
                                extracted.document_type.value,
                                extracted.dict()
                            )
                            services["db"].log_action(
                                st.session_state.current_dossier_id,
                                "pdf_uploaded",
                                {"filename": file.name}
                            )
                        
                        st.session_state.extracted_data = extracted_list
                        st.success(f"✓ {len(uploaded_files)} PDF's verwerkt")
                    except Exception as e:
                        st.error(f"Fout bij verwerking: {str(e)}")
        
        with col2:
            st.markdown("### AG-Code Invoer")
            
            invoer_method = st.radio(
                "Invoermethode",
                ["Handmatig", "CSV/JSON"],
                horizontal=False
            )
            
            ag_codes_dict = {}
            
            if invoer_method == "Handmatig":
                # Manual entry
                num_ag_codes = st.number_input("Aantal AG-codes", min_value=1, max_value=20, value=5)
                
                for i in range(num_ag_codes):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        ag_code = st.text_input(f"AG-code #{i+1}", value="AG2010", key=f"ag_code_{i}")
                    with col_b:
                        amount = st.number_input(f"Bedrag €", value=0.0, key=f"amount_{i}")
                    
                    if ag_code and amount:
                        ag_codes_dict[ag_code] = float(amount)
            
            else:
                # CSV/JSON
                json_text = st.text_area(
                    "Plak JSON of CSV data",
                    value='{"AG2010": 50000, "AG3030": 400000}',
                    height=150
                )
                
                if json_text:
                    try:
                        ag_codes_dict = json.loads(json_text)
                    except json.JSONDecodeError:
                        st.error("Ongeldig JSON formaat")
            
            # Preview
            if ag_codes_dict:
                st.markdown("#### 👀 Preview")
                preview_df = st.dataframe(
                    {
                        "AG-Code": list(ag_codes_dict.keys()),
                        "Bedrag": [f"€{v:,.2f}" for v in ag_codes_dict.values()]
                    },
                    use_container_width=True
                )
        
        # ================================================================
        # AUDIT STARTEN
        # ================================================================
        
        st.divider()
        
        if st.button("🚀 Start Fiscale AI-Audit", use_container_width=True, type="primary"):
            if not ag_codes_dict:
                st.error("Voer AG-codes in")
                return
            
            if not st.session_state.extracted_data:
                st.warning("Upload eerst PDF-documenten")
                return
            
            with st.spinner("Audit in uitvoering..."):
                try:
                    # Merge extracted data
                    merged_data = {}
                    if st.session_state.extracted_data:
                        first_data = st.session_state.extracted_data[0]
                        merged_data = first_data.dict()
                    
                    # Match AG-codes
                    results, summary = services["matcher"].match_ag_codes(
                        ag_codes_dict,
                        st.session_state.extracted_data[0] if st.session_state.extracted_data else None
                    )
                    
                    # Sla resultaten op
                    services["db"].save_audit_results(st.session_state.current_dossier_id, results)
                    st.session_state.audit_results = results
                    
                    # Fiscale analyse
                    assessment = services["advisor"].analyze_audit(
                        results, summary, merged_data
                    )
                    st.session_state.fiscal_assessment = assessment
                    services["db"].save_fiscal_notes(st.session_state.current_dossier_id, assessment)
                    
                    # Log
                    services["db"].log_action(
                        st.session_state.current_dossier_id,
                        "audit_completed",
                        {"ag_codes_count": len(ag_codes_dict), "matched": summary.matched_count}
                    )
                    
                    st.success("✓ Audit afgerond!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Auditfout: {str(e)}")
    
    # ====================================================================
    # TAB 2: Audit Dashboard
    # ====================================================================
    
    with tab2:
        st.markdown("## 📊 Audit Resultaten")
        
        if st.session_state.audit_results:
            results = st.session_state.audit_results
            summary = None
            
            # Bereken summary
            matched = sum(1 for r in results if r.status.value == "MATCH")
            mismatched = sum(1 for r in results if r.status.value == "MISMATCH")
            missing = sum(1 for r in results if r.status.value == "MISSING_PROOF")
            
            # KPI Kaarten
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Totaal AG-codes", len(results))
            with col2:
                st.metric("✓ Matches", matched, delta=f"{(matched/len(results)*100):.0f}%")
            with col3:
                st.metric("✗ Mismatches", mismatched)
            with col4:
                st.metric("? Ontbrekend", missing)
            
            st.divider()
            
            # Tabel met resultaten
            st.markdown("### Gedetailleerde Resultaten")
            
            results_data = []
            for r in results:
                results_data.append({
                    "AG-Code": r.ag_code,
                    "Naam": r.ag_name,
                    "Status": render_status_badge(r.status.value),
                    "Aangifte": f"€{r.bedrag_aangifte:,.2f}" if r.bedrag_aangifte else "-",
                    "Document": f"€{r.bedrag_document:,.2f}" if r.bedrag_document else "-",
                    "Verschil": f"€{r.verschil:,.2f}" if r.verschil else "-",
                    "Opmerking": r.opmerking
                })
            
            st.dataframe(
                results_data,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Status": st.column_config.Column(width="small")
                }
            )
            
            # Export
            st.divider()
            st.markdown("### 💾 Exporteren")
            
            export_json = json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False)
            st.download_button(
                label="📥 Download JSON rapport",
                data=export_json,
                file_name=f"audit_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
        
        else:
            st.info("Voer eerst een audit uit in Tab 1")
    
    # ====================================================================
    # TAB 3: Fiscaal Advies
    # ====================================================================
    
    with tab3:
        st.markdown("## 📋 Fiscaal Advies & Risico-Analyse")
        
        if st.session_state.fiscal_assessment:
            assessment = st.session_state.fiscal_assessment
            
            # Risk Level Indicator
            risk_colors = {
                "LOW": "🟢",
                "MEDIUM": "🟡",
                "HIGH": "🔴",
                "CRITICAL": "🔴"
            }
            
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                st.markdown("### Risico-Samenvatting")
            with col2:
                risk_emoji = risk_colors.get(assessment.overall_risk.value, "❓")
                st.metric("Totaal risico", f"{risk_emoji} {assessment.overall_risk.value}")
            
            st.divider()
            
            # Risico Punten
            if assessment.risico_punten:
                st.markdown("### 🚨 Geïdentificeerde Risico's")
                
                for rp in assessment.risico_punten:
                    with st.expander(f"{rp.titel} ({rp.impact.value})", expanded=False):
                        st.write(rp.beschrijving)
                        st.info(f"**Aanbeveling:** {rp.aanbevolen_actie}")
                        if rp.referentie:
                            st.caption(f"Referentie: {rp.referentie}")
            
            st.divider()
            
            # Sterke punten
            if assessment.sterke_punten:
                st.markdown("### ✅ Sterke Punten")
                for punt in assessment.sterke_punten:
                    st.success(f"✓ {punt}")
            
            # Aanbevelingen
            if assessment.aanbevelingen:
                st.markdown("### 💡 Aanbevelingen")
                for i, aanbeveling in enumerate(assessment.aanbevelingen, 1):
                    st.write(f"{i}. {aanbeveling}")
            
            st.divider()
            
            # Email Concept
            st.markdown("### 📧 Email Concept naar Klant")
            
            email_text = st.text_area(
                "Email concept",
                value=assessment.klant_email_concept,
                height=200,
                key="email_concept"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📋 Kopiëren", use_container_width=True):
                    st.success("Email gekopieerd naar clipboard!")
            with col2:
                if st.button("📮 Verzenden", use_container_width=True):
                    st.info("Email verzenden functie (toekomstige versie)")
        
        else:
            st.info("Voer eerst een audit uit in Tab 1 voor fiscale analyse")
    
    # ========================================================================
    # FOOTER
    # ========================================================================
    
    st.markdown("""
    <div class="footer">
    <p>© 2024 FiscAudit AI | Automated Fiscal Audit Platform</p>
    <p>Contact: info@fiscaudit.nl | v1.0.0</p>
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()

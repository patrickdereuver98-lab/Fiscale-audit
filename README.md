# 📊 FiscAudit AI

**An Automated AI-Driven Fiscal Audit & Reconciliation Platform for Dutch Tax Returns**

## 🎯 Project Overview

FiscAudit AI is een geautomatiseerde belastingaudit-tool die:

- 🔍 **Documenten analyseert** met Google Gemini 1.5 Pro (visuele PDF-extractie)
- ⚖️ **AG-codes vergelijkt** met een pure Python matcher (100% reproducible)
- 🤖 **Risico's identificeert** via Claude 3.5 Sonnet (fiscale expertise)
- 📋 **Professionele rapporten genereert** met kant-en-klare klant-communicatie
- 💾 **Alles persisteert** in Supabase (PostgreSQL)

**Technologie Stack:**
- Frontend: Streamlit + Custom CSS
- Backend: Python 3.11+ (Asyncio, Pydantic v2)
- AI: Google Gemini + Anthropic Claude
- Database: Supabase (PostgreSQL)
- Compliance: GDPR/AVG-proof anonymisering

---

## 📦 Installation & Setup

### Prerequisites

- Python 3.11+ (https://www.python.org/downloads/)
- Git (https://git-scm.com/)
- API Keys:
  - Google Gemini API (https://makersuite.google.com/app/apikey)
  - Anthropic Claude API (https://console.anthropic.com/)
  - Supabase Project (https://supabase.com/)

### 1. Clone Repository

```bash
git clone https://github.com/yourcompany/fisc-audit-ai.git
cd fisc-audit-ai
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure API Keys

#### Option A: Via Streamlit Secrets (Recommended for Local Development)

```bash
# Create .streamlit directory if not exists
mkdir -p .streamlit

# Copy and configure secrets template
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

```toml
# Supabase
supabase_url = "https://your-project.supabase.co"
supabase_key = "your-anon-public-key-here"

# Google Gemini
google_api_key = "your-google-gemini-api-key-here"

# Anthropic Claude
anthropic_api_key = "your-anthropic-api-key-here"

# Settings
environment = "development"
debug_mode = true
```

#### Option B: Environment Variables

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-anon-public-key-here"
export GOOGLE_API_KEY="your-google-gemini-api-key-here"
export ANTHROPIC_API_KEY="your-anthropic-api-key-here"
```

### 5. Setup Supabase Database

1. **Create Supabase Project**
   - Go to https://supabase.com/
   - Create new project
   - Note your Project URL and API Keys

2. **Run Database Schema**
   - Open Supabase SQL Editor
   - Copy entire content of `schema.sql`
   - Execute in SQL Editor

3. **Verify Tables**
   ```sql
   SELECT * FROM dossiers LIMIT 1;
   SELECT * FROM audit_results LIMIT 1;
   SELECT * FROM fiscal_notes LIMIT 1;
   ```

### 6. Run Application

```bash
streamlit run app.py
```

Your app will open at: **http://localhost:8501**

---

## 🚀 Usage Guide

### Workflow

1. **Create Dossier** (Sidebar)
   - Enter client name, email, tax year
   - Click "📥 Dossier aanmaken"

2. **Upload Documents** (Tab 1)
   - Drag & drop PDF files (WOZ, bank statements, etc.)
   - Click "🚀 PDF's verwerken"

3. **Enter AG-Codes** (Tab 1)
   - Manually OR paste JSON
   - Example: `{"AG2010": 50000, "AG3030": 400000}`

4. **Start Audit** (Tab 1)
   - Click "🚀 Start Fiscale AI-Audit"
   - Wait for analysis (2-5 minutes depending on documents)

5. **Review Results** (Tab 2)
   - See matching statistics
   - Identify mismatches & missing proofs
   - Export JSON report

6. **Read Fiscal Advice** (Tab 3)
   - Review identified risks
   - Read recommendation actions
   - Copy email template for client communication

---

## 🏗️ Architecture

### Data Flow

```
┌─────────────────┐
│ PDF Uploads     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Anonymizer (GDPR/AVG Compliant) │  ← Masks BSN, IBAN, etc.
└────────┬────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│ Gemini 1.5 Pro Document Extractor      │  ← Extracts financial data
│ (Pydantic validation)                  │
└────────┬─────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ Deterministic Matcher      │  ← AG-code comparison (pure Python)
│ (No AI - 100% reproducible)│
└────────┬───────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ Claude 3.5 Sonnet Fiscal Advisor     │  ← Risk analysis & recommendations
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────┐
│ Supabase Storage │  ← Persistent audit trail
└──────────────────┘
```

### Module Structure

```
fisc-audit-ai/
├── src/
│   ├── __init__.py              # Package initialization
│   ├── anonymizer.py            # GDPR compliance layer
│   ├── extractor.py             # Gemini PDF extraction
│   ├── matcher.py               # AG-code matching (pure Python)
│   ├── advisor.py               # Claude fiscal analysis
│   └── db.py                    # Supabase CRUD
├── app.py                       # Main Streamlit application
├── schema.sql                   # Database schema
├── requirements.txt             # Python dependencies
├── .streamlit/
│   ├── config.toml              # Streamlit settings
│   └── secrets.toml.example     # Secrets template
├── .gitignore                   # Git ignore rules
└── README.md                    # This file
```

---

## 🔒 Security & Compliance

### Data Privacy (GDPR/AVG)

✅ **All personal data is automatically anonymized:**
- BSN-nummers: Masked to `[BSN_MASKED]`
- IBANs: Masked to `[IBAN_NL...XXXX]`
- E-mails: Masked to `[EMAIL_MASKED@domain]`
- Phone numbers: Masked to `[PHONE_MASKED]`

✅ **Audit trail maintained:**
- All actions logged in `audit_logs` table
- Timestamp & user tracking
- Reversible masking for authorized personnel

### API Security

- Streamlit secrets stored in `.streamlit/secrets.toml` (not in Git)
- Environment variables alternative available
- All external API calls use HTTPS
- No credentials hardcoded

### Database Security

```sql
-- Row Level Security (RLS) can be enabled in production
ALTER TABLE dossiers ENABLE ROW LEVEL SECURITY;

-- Example policy:
CREATE POLICY "Users can view their own dossiers" ON dossiers
    FOR SELECT USING (user_id = current_user_id);
```

---

## 📊 API Reference

### Anonymizer

```python
from src.anonymizer import DataAnonymizer

anonymizer = DataAnonymizer(strict_mode=True)
masked_text, report = anonymizer.anonymize_text(
    "BSN: 123456789, IBAN: NL91ABNA0417164300",
    mask_bsn=True,
    mask_iban=True,
    mask_email=True
)
print(report.total_masked)  # 2
```

### Extractor

```python
from src.extractor import DocumentExtractor

extractor = DocumentExtractor(api_key="your-google-key")
data = extractor.extract_from_pdf_sync("document.pdf")
print(data.woz_gegevens.woz_waarde)  # 500000.0
```

### Matcher

```python
from src.matcher import AuditMatcher

matcher = AuditMatcher(threshold_eur=100.0)
results, summary = matcher.match_ag_codes(
    {"AG2010": 50000.0, "AG3030": 400000.0},
    extracted_data
)
print(summary.accuracy_percentage)  # 95.0
```

### Advisor

```python
from src.advisor import FiscalAdvisor

advisor = FiscalAdvisor(api_key="your-anthropic-key")
assessment = advisor.analyze_audit(results, summary, extracted_data)
print(assessment.overall_risk)  # RiskLevel.MEDIUM
```

---

## 🧪 Testing

### Unit Tests (Future)

```bash
# Run tests (when implemented)
pytest tests/ -v --cov=src
```

### Manual Testing

1. **Extract PDF:**
   ```python
   from src.extractor import DocumentExtractor
   ext = DocumentExtractor("your-key")
   data = ext.extract_from_pdf_sync("test.pdf")
   ```

2. **Match AG-codes:**
   ```python
   from src.matcher import AuditMatcher
   matcher = AuditMatcher()
   results, summary = matcher.match_ag_codes(
       {"AG2010": 50000}, data
   )
   ```

3. **Analyze Risks:**
   ```python
   from src.advisor import FiscalAdvisor
   advisor = FiscalAdvisor("your-key")
   assessment = advisor.analyze_audit(results, summary, {})
   ```

---

## 🚢 Deployment

### Option 1: Streamlit Cloud (Recommended for quick start)

1. Push repository to GitHub
2. Go to https://streamlit.io/cloud
3. Click "New app"
4. Select repository and branch
5. Add secrets in Settings → Secrets

### Option 2: Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501"]
```

```bash
docker build -t fisc-audit-ai .
docker run -p 8501:8501 -e SUPABASE_URL=... fisc-audit-ai
```

### Option 3: Traditional Server

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3-pip

cd /opt/fisc-audit-ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run with systemd
sudo cp fisc-audit-ai.service /etc/systemd/system/
sudo systemctl start fisc-audit-ai
sudo systemctl enable fisc-audit-ai
```

---

## 🛠️ Troubleshooting

### Error: "API keys not configured"

**Solution:** Create `.streamlit/secrets.toml` with all required keys:
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit file with your actual API keys
```

### Error: "Database connection failed"

**Solution:** Verify Supabase credentials and network:
```python
from src.db import initialize_supabase
db = initialize_supabase("your-url", "your-key")
if db.health_check():
    print("✓ Database connected")
```

### Error: "Gemini API rate limit"

**Solution:** Implement retry logic (already built-in via `tenacity`):
```python
extractor = DocumentExtractor(api_key="your-key")
# Automatically retries on rate limit
data = extractor.extract_from_pdf_sync("large-file.pdf")
```

### PDF extraction returns empty data

**Solution:** Ensure PDF is not scanned/image-only:
- Use OCR if needed: `python-pdf2image` + Tesseract
- Check Gemini vision capabilities
- Verify API quota

---

## 📚 References

- **Streamlit Docs:** https://docs.streamlit.io/
- **Google Gemini:** https://ai.google.dev/
- **Anthropic Claude:** https://docs.anthropic.com/
- **Supabase:** https://supabase.com/docs
- **Pydantic:** https://docs.pydantic.dev/

### Dutch Tax Resources

- **Belastingdienst:** https://www.belastingdienst.nl/
- **IB 2024:** https://www.belastingdienst.nl/inkomstenbelasting
- **VPB:** https://www.belastingdienst.nl/vennootschapsbelasting
- **Box 3:** https://www.belastingdienst.nl/box-3

---

## 🤝 Contributing

### Development Setup

```bash
# Install dev dependencies
pip install black flake8 mypy pylint pytest

# Format code
black src/ app.py

# Lint
flake8 src/ app.py --max-line-length=100

# Type check
mypy src/
```

### Commit Convention

```
feat: Add new feature (AG2060 matching)
fix: Fix bug in anonymizer
docs: Update README
style: Format code
refactor: Restructure module
test: Add unit tests
chore: Update dependencies
```

---

## 📝 License

MIT License - See LICENSE file

---

## 📞 Support & Contact

- **Email:** support@fiscaudit.nl
- **Issues:** https://github.com/yourcompany/fisc-audit-ai/issues
- **Documentation:** https://docs.fiscaudit.nl/

---

## 🎯 Roadmap

- ✅ MVP: Document extraction + AG-code matching + Risk analysis
- 🔲 AFAS ERP integration
- 🔲 Email delivery (SMTP)
- 🔲 Multi-user/client support (Teams)
- 🔲 Advanced reporting (PDF export)
- 🔲 Mobile app
- 🔲 Real-time collaboration
- 🔲 AI model fine-tuning on Dutch tax data

---

**FiscAudit AI v1.0.0** | Made with ❤️ for Dutch tax professionals

Last Updated: 2024 | © FiscAudit Team

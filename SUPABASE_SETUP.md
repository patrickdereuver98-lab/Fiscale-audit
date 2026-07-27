# 🗄️ FiscAudit AI - Supabase Setup Guide

## 📋 Overzicht

Dit document bevat **stap-voor-stap instructies** om Supabase in te richten voor FiscAudit AI.

---

## ⚡ Quick Start (5 minuten)

### Stap 1: Supabase Project Aanmaken

1. Ga naar https://supabase.com/
2. Login of registreer (gratis account)
3. Click **"New project"**
4. Vul in:
   - **Name**: `fisc-audit-db` (of naar keuze)
   - **Password**: Sterk wachtwoord (bijv. `Kj9$mQ2#xL8&vN4p`)
   - **Region**: `eu-central-1` (Frankfurt) ← Voor snelheid
5. Click **"Create new project"**
6. Wacht ~2 minuten tot project klaar is

### Stap 2: API Keys Noteren

1. Ga naar **Settings** → **API**
2. Kopieer:
   - **Project URL** (bijv. `https://xxxx.supabase.co`)
   - **anon public key** (lang sleutel onder "Project API keys")

   ```
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5..."
   ```

### Stap 3: Database Schema Uitvoeren

1. Ga naar **SQL Editor** (linkermenu)
2. Click **"New Query"**
3. Copy alles uit `schema.sql` in dit project
4. Click **"Run"** (blauw knopje rechtsboven)
5. Wacht tot "Success" bericht verschijnt

**Dat's het!** Database is klaar! ✅

---

## 🔍 Verificatie

### Check 1: Tabellen Bestaan

In SQL Editor, run:

```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

Je ziet:
- `audit_logs`
- `audit_results`
- `dossiers`
- `fiscal_notes`
- `uploaded_documents`

### Check 2: Columns Correct

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'dossiers'
ORDER BY ordinal_position;
```

### Check 3: Test Insert/Select

```sql
-- Insert test dossier
INSERT INTO dossiers (klant_naam, aangiftejaar, status)
VALUES ('Test Klant', 2024, 'in_progress');

-- Select all
SELECT * FROM dossiers;

-- Clean up
DELETE FROM dossiers WHERE klant_naam = 'Test Klant';
```

---

## 🔐 Configuratie in FiscAudit AI

### Stap 1: Secrets File

1. Copy template naar werkend bestand:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

2. Vul je Supabase credentials in:
   ```toml
   supabase_url = "https://xxxx.supabase.co"
   supabase_key = "eyJhbGciOiJIUzI1NiIsInR5..."
   
   # Voeg ook Google & Anthropic keys toe:
   google_api_key = "AIzaSy..."
   anthropic_api_key = "sk-ant-api03-..."
   ```

3. **BELANGRIJK**: `.streamlit/secrets.toml` staat in `.gitignore`
   - Dit bestand wordt NOOIT naar Git gecommit
   - Dit beschermt je API keys! 🔒

### Stap 2: Test Connectie

Start de app:
```bash
streamlit run app.py
```

Je ziet in sidebar:
- ✓ Supabase verbonden
- Statistieken (totale dossiers, etc.)

---

## 🚀 Geavanceerde Setup (Optional)

### Row Level Security (RLS) Activeren

Voor production: enable RLS zodat users enkel hun eigen data zien.

```sql
-- Enable RLS op alle tabellen
ALTER TABLE dossiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE fiscal_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE uploaded_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Voorbeeld policy: Users kunnen hun eigen dossiers zien
CREATE POLICY "Users can view own dossiers"
  ON dossiers FOR SELECT
  USING (user_id = auth.uid());
```

### Backups Inschakelen

1. Settings → **Backups**
2. Kies backup schedule (bijv. dagelijks)
3. Backups worden 7 dagen bewaard

### Performance Monitoring

1. Settings → **Performance** (voor production)
2. Monitoor query performance
3. View slow query logs

---

## 🆘 Troubleshooting

### Error: "Connection refused"

**Oorzaak**: Supabase project niet actief
**Oplossing**:
```bash
# Test connectie
curl https://xxxx.supabase.co/auth/v1/health

# Je ziet: {"status":"ok"} ✓
```

### Error: "Invalid API key"

**Oorzaak**: Verkeerde key in `secrets.toml`
**Oplossing**:
1. Ga naar Supabase → Settings → API
2. Double-check de **anon public key** (niet service role key!)
3. Kopieer opnieuw in `secrets.toml`

### Error: "Table does not exist"

**Oorzaak**: `schema.sql` niet volledig uitgevoerd
**Oplossing**:
1. Ga naar SQL Editor
2. Run:
   ```sql
   DROP SCHEMA IF EXISTS public CASCADE;
   CREATE SCHEMA public;
   ```
3. Run compleet `schema.sql` opnieuw

### Error: "Permission denied"

**Oorzaak**: RLS policies te strict
**Oplossing**:
1. Disable RLS temporarily:
   ```sql
   ALTER TABLE dossiers DISABLE ROW LEVEL SECURITY;
   ```
2. Update policies
3. Re-enable RLS

---

## 📊 Database Monitoring

### Disk Usage

Settings → **Billing**
- Current usage
- Limits & quotas

### Query Stats

Table → ⋮ (3 dots) → **Query Performance**

### Connection Pools

Settings → **Connection Pooling**
- Setup PgBouncer voor betere performance

---

## 🗑️ Cleanup (Resets)

### Delete All Data (Keep Schema)

```sql
-- Cascade delete (deletes dependents automatically)
DELETE FROM dossiers;

-- Verify
SELECT COUNT(*) FROM dossiers;  -- Should be 0
SELECT COUNT(*) FROM audit_results;  -- Should be 0
```

### Full Reset (Delete Everything)

```sql
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
-- Then run schema.sql again
```

---

## 🔄 Backup & Restore

### Manual Backup

```bash
# Download backup (requires Supabase CLI)
supabase db pull --db-url "postgresql://..."

# Create dump
pg_dump postgresql://... > backup_2024.sql
```

### Restore from Backup

```bash
psql postgresql://... < backup_2024.sql
```

---

## 💾 Environment Variables Alternative

If you prefer env vars instead of `.streamlit/secrets.toml`:

```bash
# .env file (also in .gitignore!)
export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5..."
export GOOGLE_API_KEY="AIzaSy..."
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

Then in app.py:
```python
import os
from dotenv import load_dotenv

load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
```

---

## 📚 Useful Supabase Resources

- **Docs**: https://supabase.com/docs
- **SQL Reference**: https://supabase.com/docs/guides/database
- **RLS Guide**: https://supabase.com/docs/guides/auth/row-level-security
- **Pricing**: https://supabase.com/pricing
- **Status Page**: https://status.supabase.com

---

## ✅ Checklist

Before you start testing FiscAudit AI:

- [ ] Supabase project created
- [ ] Region set to eu-central-1
- [ ] schema.sql executed successfully
- [ ] All 5 tables exist
- [ ] API keys copied to secrets.toml
- [ ] .streamlit/secrets.toml in .gitignore
- [ ] Database connectivity tested
- [ ] Backups enabled (optional)

---

## 🎉 Supabase Setup Complete!

You're ready to:
1. Upload PDFs
2. Run audits
3. Store results in Supabase
4. Generate fiscal reports

Next: Start FiscAudit AI!

```bash
streamlit run app.py
```

Questions? Check the README.md or troubleshooting section above! 🚀

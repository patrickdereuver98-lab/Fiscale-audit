-- FiscAudit AI - PostgreSQL Schema voor Supabase
-- Volledig met RLS policies, enums en optimalisaties

-- ============================================================================
-- ENUMS & TYPES
-- ============================================================================

CREATE TYPE audit_status AS ENUM ('MATCH', 'MISMATCH', 'MISSING_PROOF', 'ERROR');

CREATE TYPE risk_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');

-- ============================================================================
-- TABLES
-- ============================================================================

-- Dossiers: Bovenliggende container voor een volledige audit
CREATE TABLE IF NOT EXISTS dossiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    klant_naam TEXT NOT NULL,
    klant_email TEXT,
    aangiftejaar INTEGER NOT NULL,
    inkomstenbelasting BOOLEAN DEFAULT FALSE,
    vennootschapsbelasting BOOLEAN DEFAULT FALSE,
    box3_audit BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'in_progress',
    notities TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT valid_aangiftejaar CHECK (aangiftejaar >= 2015 AND aangiftejaar <= 2100)
);

-- Audit Results: Per AG-code match/mismatch
CREATE TABLE IF NOT EXISTS audit_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    ag_code TEXT NOT NULL, -- bijv. 'AG2010', 'AG3050'
    status audit_status NOT NULL,
    bedrag_aangifte NUMERIC(15, 2),
    bedrag_document NUMERIC(15, 2),
    verschil NUMERIC(15, 2),
    opmerking TEXT,
    document_ref TEXT, -- reference naar source document
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    INDEX idx_dossier_id (dossier_id),
    INDEX idx_ag_code (ag_code),
    INDEX idx_status (status)
);

-- Fiscal Notes: Risico-analyses en advies per dossier
CREATE TABLE IF NOT EXISTS fiscal_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    risk_level risk_level DEFAULT 'MEDIUM',
    risico_analyse TEXT NOT NULL, -- Claude's gestructureerde analyse
    kritieke_punten JSONB DEFAULT '[]'::jsonb, -- Array met {punten, risico, actie}
    klant_mail_concept TEXT, -- Kant-en-klaar emailconcept
    advisor_notes TEXT, -- Interne notities
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    INDEX idx_dossier_id (dossier_id),
    INDEX idx_risk_level (risk_level)
);

-- Document Metadata: Info over geüploade PDF's
CREATE TABLE IF NOT EXISTS uploaded_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    bestandsnaam TEXT NOT NULL,
    document_type TEXT, -- 'WOZ_Beschikking', 'Bank_Jaaroverzicht', etc.
    extracted_data JSONB, -- Geëxtraheerde gegevens (anoniem)
    pagina_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    INDEX idx_dossier_id (dossier_id),
    INDEX idx_document_type (document_type)
);

-- Audit Log: Voor compliance tracking
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    user_info TEXT,
    ip_address TEXT,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    INDEX idx_dossier_id (dossier_id),
    INDEX idx_created_at (created_at)
);

-- ============================================================================
-- INDEXES & PERFORMANCE
-- ============================================================================

CREATE INDEX idx_dossiers_jaar ON dossiers(aangiftejaar);
CREATE INDEX idx_dossiers_status ON dossiers(status);
CREATE INDEX idx_dossiers_created ON dossiers(created_at DESC);
CREATE INDEX idx_audit_results_dossier_status ON audit_results(dossier_id, status);

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) - Voorlopig uitgeschakeld voor development
-- In production: Enable RLS en configureer policies per user/tenant
-- ============================================================================

-- ALTER TABLE dossiers ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE audit_results ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE fiscal_notes ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE uploaded_documents ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Placeholder policies (uncomment en customize in production)
-- CREATE POLICY "Users can view their own dossiers" ON dossiers
--     FOR SELECT USING (auth.uid()::text = user_id);

-- ============================================================================
-- VIEWS & AGGREGATE QUERIES
-- ============================================================================

-- Dashboard Overview: Statistieken per dossier
CREATE OR REPLACE VIEW dossier_summary AS
SELECT 
    d.id,
    d.klant_naam,
    d.aangiftejaar,
    COUNT(CASE WHEN ar.status = 'MATCH' THEN 1 END) as matches_count,
    COUNT(CASE WHEN ar.status = 'MISMATCH' THEN 1 END) as mismatches_count,
    COUNT(CASE WHEN ar.status = 'MISSING_PROOF' THEN 1 END) as missing_proof_count,
    COUNT(CASE WHEN ar.status = 'ERROR' THEN 1 END) as error_count,
    SUM(CASE WHEN ar.status = 'MISMATCH' THEN ar.verschil ELSE 0 END) as total_verschil,
    fn.risk_level,
    d.created_at,
    d.updated_at
FROM dossiers d
LEFT JOIN audit_results ar ON d.id = ar.dossier_id
LEFT JOIN fiscal_notes fn ON d.id = fn.dossier_id
GROUP BY d.id, d.klant_naam, d.aangiftejaar, d.created_at, d.updated_at, fn.risk_level;

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Functie om dossier status automatisch bij te werken
CREATE OR REPLACE FUNCTION update_dossier_status()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE dossiers SET updated_at = now()
    WHERE id = NEW.dossier_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger voor audit_results
CREATE TRIGGER trigger_update_dossier_on_audit_results
AFTER INSERT OR UPDATE ON audit_results
FOR EACH ROW
EXECUTE FUNCTION update_dossier_status();

-- Trigger voor fiscal_notes
CREATE TRIGGER trigger_update_dossier_on_fiscal_notes
AFTER INSERT OR UPDATE ON fiscal_notes
FOR EACH ROW
EXECUTE FUNCTION update_dossier_status();

-- ============================================================================
-- SAMPLE DATA (Optioneel, voor development)
-- ============================================================================

-- INSERT INTO dossiers (klant_naam, klant_email, aangiftejaar, status)
-- VALUES 
--     ('Demo Klant BV', 'contact@demo.nl', 2024, 'in_progress'),
--     ('Test Persoon', 'persoon@test.nl', 2024, 'completed');

-- ============================================================================
-- COMMENTS (For documentation)
-- ============================================================================

COMMENT ON TABLE dossiers IS 'Hoofd-container voor een fiscale audit-run';
COMMENT ON TABLE audit_results IS 'Per-AG-code match/mismatch resultaten';
COMMENT ON TABLE fiscal_notes IS 'Inhoudelijke risico-analyses van Claude';
COMMENT ON TABLE uploaded_documents IS 'Metadata van geüploade en geverifieerde PDF-documenten';
COMMENT ON COLUMN dossiers.aangiftejaar IS 'Jaar van de aangifteperiode (bijv. 2024)';
COMMENT ON COLUMN audit_results.status IS 'MATCH: perfect match, MISMATCH: verschil > 0, MISSING_PROOF: geen ondersteunend document';

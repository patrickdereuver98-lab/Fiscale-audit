-- FiscAudit AI - PostgreSQL Schema voor Supabase
-- Volledig met RLS policies, enums en optimalisaties

-- ============================================================================
-- ENUMS & TYPES
-- ============================================================================

-- MINOR_VARIANCE en PENDING ontbraken; een insert met die status werd door
-- Postgres geweigerd met een enum-schending.
CREATE TYPE audit_status AS ENUM (
    'MATCH', 'MINOR_VARIANCE', 'MISMATCH', 'MISSING_PROOF', 'ERROR', 'PENDING'
);

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
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
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
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Document Metadata: Info over geüploade PDF's
CREATE TABLE IF NOT EXISTS uploaded_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    bestandsnaam TEXT NOT NULL,
    document_type TEXT, -- 'WOZ_Beschikking', 'Bank_Jaaroverzicht', etc.
    extracted_data JSONB, -- Geëxtraheerde gegevens (anoniem)
    pagina_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Audit Log: Voor compliance tracking
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    user_info TEXT,
    ip_address TEXT,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- ============================================================================
-- INDEXES & PERFORMANCE
-- ============================================================================

-- Indexnamen zijn in PostgreSQL schemabreed uniek, dus met tabelprefix.
CREATE INDEX IF NOT EXISTS idx_dossiers_jaar ON dossiers(aangiftejaar);
CREATE INDEX IF NOT EXISTS idx_dossiers_status ON dossiers(status);
CREATE INDEX IF NOT EXISTS idx_dossiers_created ON dossiers(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_results_dossier ON audit_results(dossier_id);
CREATE INDEX IF NOT EXISTS idx_audit_results_ag_code ON audit_results(ag_code);
CREATE INDEX IF NOT EXISTS idx_audit_results_status ON audit_results(status);
CREATE INDEX IF NOT EXISTS idx_audit_results_dossier_status
    ON audit_results(dossier_id, status);

CREATE INDEX IF NOT EXISTS idx_fiscal_notes_dossier ON fiscal_notes(dossier_id);
CREATE INDEX IF NOT EXISTS idx_fiscal_notes_risk ON fiscal_notes(risk_level);

CREATE INDEX IF NOT EXISTS idx_documents_dossier ON uploaded_documents(dossier_id);
CREATE INDEX IF NOT EXISTS idx_documents_type ON uploaded_documents(document_type);

CREATE INDEX IF NOT EXISTS idx_audit_logs_dossier ON audit_logs(dossier_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);

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
    COUNT(CASE WHEN ar.status = 'MINOR_VARIANCE' THEN 1 END) as minor_variance_count,
    COUNT(CASE WHEN ar.status = 'MISMATCH' THEN 1 END) as mismatches_count,
    COUNT(CASE WHEN ar.status = 'MISSING_PROOF' THEN 1 END) as missing_proof_count,
    COUNT(CASE WHEN ar.status = 'ERROR' THEN 1 END) as error_count,
    -- ABS: zonder absolute waarde heffen een te hoge en een te lage post elkaar
    -- op en toont het dashboard 0 terwijl er twee afwijkingen zijn.
    COALESCE(SUM(CASE WHEN ar.status = 'MISMATCH'
                      THEN ABS(ar.verschil) ELSE 0 END), 0) as bruto_verschil,
    COALESCE(SUM(CASE WHEN ar.status = 'MISMATCH'
                      THEN ar.verschil ELSE 0 END), 0) as netto_verschil,
    COALESCE(SUM(CASE WHEN ar.status = 'MISSING_PROOF'
                      THEN ar.bedrag_aangifte ELSE 0 END), 0) as niet_verifieerbaar,
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


-- ============================================================================
-- FISCALE KENNISBANK
-- ============================================================================
-- Per belastingjaar gescheiden. Een regel die in 2023 gold en in 2024 niet
-- meer, mag bij een aangifte 2024 niet worden opgehaald. Zonder die scheiding
-- levert de kennisbank met gezag een verouderd antwoord, en dat is schadelijker
-- dan geen antwoord.

CREATE TYPE kennis_herkomst AS ENUM (
    'WETGEVING',       -- wettekst, vrij van auteursrecht
    'BELASTINGDIENST', -- publieke toelichting van de Belastingdienst
    'BELEIDSBESLUIT',
    'RECHTSPRAAK',
    'KANTOORMEMO',     -- eigen vastlegging
    'MODEL_GEGENEREERD' -- door een taalmodel opgesteld, nog niet nagekeken
);

CREATE TYPE kennis_status AS ENUM (
    'CONCEPT',      -- opgenomen, nog niet nagekeken
    'GEVERIFIEERD', -- door een mens gecontroleerd en akkoord
    'VERVALLEN'     -- niet meer van toepassing, bewaard voor oudere jaren
);

CREATE TABLE IF NOT EXISTS fiscale_kennis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    belastingjaar INTEGER NOT NULL,
    onderwerp TEXT NOT NULL,          -- bijv. 'bijleenregeling'
    trigger_kind TEXT,                -- koppeling met triggers.py, bijv. 'WONING_AANKOOP'

    -- de inhoud
    titel TEXT NOT NULL,
    inhoud TEXT NOT NULL,
    toepassingsvoorwaarden TEXT,

    -- herkomst en houdbaarheid
    herkomst kennis_herkomst NOT NULL,
    bron_url TEXT,
    bron_citaat TEXT,
    status kennis_status NOT NULL DEFAULT 'CONCEPT',

    -- Wie heeft dit nagekeken en wanneer. Een kennisbank die een taalmodel
    -- zelf vult en daarna zelf leest is een gesloten kring zonder externe
    -- toets: een fout bevestigt zichzelf. Deze twee kolommen maken zichtbaar
    -- welke regels een mens heeft gezien.
    geverifieerd_door TEXT,
    geverifieerd_op DATE,

    -- vervangingsketen, zodat een oudere aangifte de oude regel blijft zien
    vervangt_id UUID REFERENCES fiscale_kennis(id),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

    CONSTRAINT geldig_belastingjaar
        CHECK (belastingjaar >= 2015 AND belastingjaar <= 2100),
    -- Geverifieerd zonder naam en datum kan niet: dan is de status een lege
    -- belofte en zou de reviewnote onterecht 'gecontroleerd' tonen.
    CONSTRAINT verificatie_volledig CHECK (
        status <> 'GEVERIFIEERD'
        OR (geverifieerd_door IS NOT NULL AND geverifieerd_op IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_kennis_jaar_onderwerp
    ON fiscale_kennis(belastingjaar, onderwerp);
CREATE INDEX IF NOT EXISTS idx_kennis_trigger
    ON fiscale_kennis(trigger_kind, belastingjaar);
CREATE INDEX IF NOT EXISTS idx_kennis_status ON fiscale_kennis(status);

-- Alleen wat is nagekeken, per jaar. Dit is de weergave waar de tool uit
-- ophaalt wanneer een verwijzing in de reviewnote terechtkomt.
CREATE OR REPLACE VIEW kennis_geverifieerd AS
SELECT id, belastingjaar, onderwerp, trigger_kind, titel, inhoud,
       toepassingsvoorwaarden, herkomst, bron_url, geverifieerd_op
FROM fiscale_kennis
WHERE status = 'GEVERIFIEERD';

COMMENT ON TABLE fiscale_kennis IS
    'Fiscale regels per belastingjaar. Alleen rijen met status GEVERIFIEERD '
    'mogen in een reviewnote worden aangehaald; CONCEPT en MODEL_GEGENEREERD '
    'zijn uitsluitend intern en moeten als onbevestigd worden weergegeven.';


-- ============================================================================
-- BEHANDELSTATUS PER BEVINDING
-- ============================================================================
-- Zonder deze tabel komt elke terechte uitzondering bij iedere nieuwe run
-- opnieuw als rood vlaggetje naar boven, en kijkt niemand er na twee weken nog
-- naar.

CREATE TYPE review_status AS ENUM (
    'OPEN', 'SEEN', 'ACCEPTED', 'CORRECTION_REQUIRED'
);

CREATE TABLE IF NOT EXISTS bevinding_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,

    -- Stabiele sleutel van de bevinding, los van de rij-id, zodat een
    -- accordering een nieuwe run overleeft.
    bevinding_sleutel TEXT NOT NULL,
    aangiftepost TEXT NOT NULL,

    status review_status NOT NULL DEFAULT 'OPEN',
    onderbouwing TEXT,
    behandeld_door TEXT,
    behandeld_op TIMESTAMP WITH TIME ZONE,

    -- Het bedrag waarop is geaccordeerd. Wijzigt het bedrag bij een volgende
    -- run, dan gaat de bevinding terug naar OPEN: een akkoord op EUR 500 is
    -- geen akkoord op EUR 5.000.
    geaccordeerd_verschil NUMERIC(15, 2),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

    CONSTRAINT een_status_per_bevinding UNIQUE (dossier_id, bevinding_sleutel),
    -- Akkoord zonder reden is geen akkoord maar een klik.
    CONSTRAINT akkoord_met_reden CHECK (
        status <> 'ACCEPTED'
        OR (onderbouwing IS NOT NULL AND length(trim(onderbouwing)) > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_bevinding_dossier ON bevinding_status(dossier_id);
CREATE INDEX IF NOT EXISTS idx_bevinding_status ON bevinding_status(status);

COMMENT ON COLUMN bevinding_status.geaccordeerd_verschil IS
    'Bedrag waarop is geaccordeerd. Wijkt het verschil bij een volgende run '
    'af, dan hoort de bevinding opnieuw als OPEN te verschijnen.';


-- ============================================================================
-- AANGETROFFEN BIJZONDERE SITUATIES
-- ============================================================================
-- Vastleggen omdat een deel doorwerkt naar latere jaren. De bijleenregeling en
-- de oudedagsreserve zijn niet te controleren zonder de gegevens van eerdere
-- jaren; deze tabel maakt die controle volgend jaar mogelijk.

CREATE TABLE IF NOT EXISTS dossier_situaties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    belastingjaar INTEGER NOT NULL,

    trigger_kind TEXT NOT NULL,
    reden TEXT,
    raakt_volgend_jaar BOOLEAN NOT NULL DEFAULT FALSE,

    -- Waarden die volgend jaar nodig zijn, bijvoorbeeld de eigenwoningreserve
    -- of de stand van de oudedagsreserve.
    doorwerkende_waarden JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

    CONSTRAINT geldig_situatiejaar
        CHECK (belastingjaar >= 2015 AND belastingjaar <= 2100)
);

CREATE INDEX IF NOT EXISTS idx_situaties_dossier ON dossier_situaties(dossier_id);
CREATE INDEX IF NOT EXISTS idx_situaties_doorwerking
    ON dossier_situaties(raakt_volgend_jaar, belastingjaar);


-- ============================================================================
-- FISCALE KERNWAARDEN
-- ============================================================================
-- Getallen: tarieven, drempels, schijven. Onderscheiden van fiscale_kennis, dat
-- tekstuele regels bevat. De deterministische controles lezen hier
-- rechtstreeks uit, zonder modelaanroep per berekening.
--
-- Verversen levert voorstellen op die per stuk worden goedgekeurd. Een waarde
-- zonder laatst_geverifieerd wordt door de tool niet gebruikt: die geeft None
-- terug in plaats van een getal, zodat een onbevestigde aanname niet
-- ongemerkt in een fiscale conclusie belandt.

CREATE TABLE IF NOT EXISTS fiscale_kernwaarden (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    sleutel TEXT NOT NULL,            -- vaste aanduiding, bijv. 'box3_forfait_spaargeld'
    belastingjaar INTEGER NOT NULL,
    naam TEXT NOT NULL,

    -- JSONB en niet NUMERIC, omdat een deel van de waarden een schijventabel is
    -- (eigenwoningforfait, KIA, IB-schijven) en niet een enkel getal.
    waarde JSONB,
    eenheid TEXT NOT NULL DEFAULT 'EUR',  -- EUR, procent, tabel, uren
    toelichting TEXT,

    bron_naam TEXT,
    bron_url TEXT,
    laatst_geverifieerd DATE,
    geverifieerd_door TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

    CONSTRAINT een_waarde_per_jaar UNIQUE (sleutel, belastingjaar),
    CONSTRAINT geldig_kernwaardejaar
        CHECK (belastingjaar >= 2015 AND belastingjaar <= 2100),
    -- Geverifieerd zonder naam, datum en verwijzing kan niet: dan is er niets
    -- om tegen na te kijken en rust het getal alleen op het model.
    CONSTRAINT verificatie_herleidbaar CHECK (
        laatst_geverifieerd IS NULL
        OR (geverifieerd_door IS NOT NULL
            AND length(trim(geverifieerd_door)) > 0
            AND bron_url IS NOT NULL
            AND length(trim(bron_url)) > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_kernwaarden_jaar
    ON fiscale_kernwaarden(belastingjaar);
CREATE INDEX IF NOT EXISTS idx_kernwaarden_sleutel
    ON fiscale_kernwaarden(sleutel, belastingjaar);

-- Alleen wat bruikbaar is. De tool leest hieruit; wat hier niet in staat is
-- nog niet nagekeken en mag geen rol spelen in een berekening.
CREATE OR REPLACE VIEW kernwaarden_bruikbaar AS
SELECT sleutel, belastingjaar, naam, waarde, eenheid,
       bron_naam, bron_url, laatst_geverifieerd, geverifieerd_door
FROM fiscale_kernwaarden
WHERE waarde IS NOT NULL AND laatst_geverifieerd IS NOT NULL;

-- Wat er nog nagekeken moet worden, oudste verificatie eerst.
CREATE OR REPLACE VIEW kernwaarden_openstaand AS
SELECT sleutel, belastingjaar, naam, eenheid, toelichting,
       laatst_geverifieerd,
       CASE
           WHEN waarde IS NULL THEN 'Niet vastgesteld'
           WHEN laatst_geverifieerd IS NULL THEN 'Niet geverifieerd'
       END AS status
FROM fiscale_kernwaarden
WHERE waarde IS NULL OR laatst_geverifieerd IS NULL
ORDER BY belastingjaar DESC, sleutel;

COMMENT ON TABLE fiscale_kernwaarden IS
    'Fiscale getallen per belastingjaar. Een rij zonder laatst_geverifieerd '
    'wordt door de tool niet gebruikt; laad via de view kernwaarden_bruikbaar.';

COMMENT ON COLUMN fiscale_kernwaarden.waarde IS
    'JSONB omdat een deel van de waarden een schijventabel is en niet een '
    'enkel getal.';

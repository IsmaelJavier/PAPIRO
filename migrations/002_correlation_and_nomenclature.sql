-- PAPIRO migration 002
-- Preserves existing findings while correcting semantic nomenclature and
-- adding deterministic cross-source correlation.
--
-- Execute against the existing PostgreSQL database. Do NOT drop the database.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'findings' AND column_name = 'confidence'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'findings' AND column_name = 'evidence_strength'
    ) THEN
        ALTER TABLE findings RENAME COLUMN confidence TO evidence_strength;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'findings' AND column_name = 'relevance_reason'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'findings' AND column_name = 'match_reason'
    ) THEN
        ALTER TABLE findings RENAME COLUMN relevance_reason TO match_reason;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS correlations (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    finding_a_id VARCHAR(36) NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    finding_b_id VARCHAR(36) NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    correlation_type VARCHAR(64) NOT NULL,
    basis TEXT NOT NULL,
    assessment VARCHAR(32) NOT NULL DEFAULT 'indeterminado',
    assessment_note TEXT,
    assessment_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_correlation_job_findings
        UNIQUE (job_id, finding_a_id, finding_b_id)
);

CREATE INDEX IF NOT EXISTS ix_correlations_job_id
    ON correlations(job_id);
CREATE INDEX IF NOT EXISTS ix_correlations_finding_a_id
    ON correlations(finding_a_id);
CREATE INDEX IF NOT EXISTS ix_correlations_finding_b_id
    ON correlations(finding_b_id);

CREATE TABLE IF NOT EXISTS correlation_evidence (
    id VARCHAR(36) PRIMARY KEY,
    correlation_id VARCHAR(36) NOT NULL
        REFERENCES correlations(id) ON DELETE CASCADE,
    indicator_a_id VARCHAR(36) NOT NULL
        REFERENCES indicators(id) ON DELETE CASCADE,
    indicator_b_id VARCHAR(36) NOT NULL
        REFERENCES indicators(id) ON DELETE CASCADE,
    CONSTRAINT uq_correlation_indicator_pair
        UNIQUE (correlation_id, indicator_a_id, indicator_b_id)
);

CREATE INDEX IF NOT EXISTS ix_correlation_evidence_correlation_id
    ON correlation_evidence(correlation_id);

-- Existing records receive the explicit neutral state.
UPDATE correlations
SET assessment = 'indeterminado'
WHERE assessment IS NULL;

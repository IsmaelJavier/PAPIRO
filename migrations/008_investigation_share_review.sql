-- Additive review state for GitHub-style investigation proposals.
-- Existing shares and investigation data are preserved.
ALTER TABLE investigation_shares
    ADD COLUMN IF NOT EXISTS reviewed_snapshot JSONB NULL;
ALTER TABLE investigation_shares
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NULL;

-- Investigation workspace metadata; safe to apply more than once.
ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'draft';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS investigation_title TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS notes TEXT;

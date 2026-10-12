-- Entity accounts and auditable organization verification.
-- Existing organizations remain unverified until an administrator reviews them.
-- Idempotent so deployments can safely re-run the migration.

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS contact_email VARCHAR(320);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS verified_by_user_id VARCHAR(36);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_organizations_verified_by_user'
    ) THEN
        ALTER TABLE organizations ADD CONSTRAINT fk_organizations_verified_by_user
            FOREIGN KEY (verified_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
END $$;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_global_role_check;
ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_global_role;
ALTER TABLE users ADD CONSTRAINT ck_users_global_role
    CHECK (global_role IN ('superuser', 'investigator', 'entity', 'user'));

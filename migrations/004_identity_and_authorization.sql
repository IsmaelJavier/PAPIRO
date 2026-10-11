-- Identity and authorization foundation.
-- Safe additive migration: historical jobs remain ownerless until an explicit
-- audited claim/reassignment. Do not assign historical ownership by inference.

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    global_role VARCHAR(32) NOT NULL DEFAULT 'investigator'
        CHECK (global_role IN ('superuser', 'investigator', 'user')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

CREATE TABLE IF NOT EXISTS organizations (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_organizations_slug ON organizations(slug);

CREATE TABLE IF NOT EXISTS organization_memberships (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL DEFAULT 'investigator'
        CHECK (role IN ('entity', 'investigator')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_organization_membership UNIQUE (organization_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_organization_memberships_organization_id
    ON organization_memberships(organization_id);
CREATE INDEX IF NOT EXISTS ix_organization_memberships_user_id
    ON organization_memberships(user_id);

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(36);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS organization_id VARCHAR(36);
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_jobs_owner_user') THEN
        ALTER TABLE jobs ADD CONSTRAINT fk_jobs_owner_user
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_jobs_organization') THEN
        ALTER TABLE jobs ADD CONSTRAINT fk_jobs_organization
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_jobs_owner_user_id ON jobs(owner_user_id);
CREATE INDEX IF NOT EXISTS ix_jobs_organization_id ON jobs(organization_id);

-- Intentionally no NOT NULL yet: existing records must be explicitly assigned
-- to a verified user/org before a later hardening migration enforces ownership.
-- A job is personal when organization_id IS NULL and organizational otherwise;
-- owner_user_id is always the accountable investigator for newly created jobs.

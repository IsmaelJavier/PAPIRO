-- Entity onboarding requests and uniqueness of the platform administrator.
-- Additive and safe for existing user, organization, membership and investigation data.

CREATE TABLE IF NOT EXISTS entity_registration_requests (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    organization_name VARCHAR(200) NOT NULL,
    organization_slug VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ NULL,
    reviewed_by_user_id VARCHAR(36) NULL REFERENCES users(id) ON DELETE RESTRICT,
    organization_id VARCHAR(36) NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    rejection_reason TEXT NULL,
    CONSTRAINT ck_entity_registration_request_status CHECK (status IN ('pending', 'approved', 'rejected'))
);
CREATE INDEX IF NOT EXISTS ix_entity_registration_requests_email ON entity_registration_requests(email);
CREATE INDEX IF NOT EXISTS ix_entity_registration_requests_slug ON entity_registration_requests(organization_slug);
CREATE INDEX IF NOT EXISTS ix_entity_registration_requests_status ON entity_registration_requests(status);

-- PostgreSQL permits only one row with the platform-wide superuser role.
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_superuser
    ON users (global_role) WHERE global_role = 'superuser';

-- New investigator memberships are invitations, not active memberships, until
-- the invited investigator explicitly accepts. Existing memberships are kept.
ALTER TABLE organization_memberships
    ADD COLUMN IF NOT EXISTS invitation_status VARCHAR(16) NOT NULL DEFAULT 'accepted';
ALTER TABLE organization_memberships
    ADD COLUMN IF NOT EXISTS invited_by_user_id VARCHAR(36) NULL REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE organization_memberships
    ADD COLUMN IF NOT EXISTS responded_at TIMESTAMPTZ NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_organization_membership_invitation_status'
    ) THEN
        ALTER TABLE organization_memberships
            ADD CONSTRAINT ck_organization_membership_invitation_status
            CHECK (invitation_status IN ('pending', 'accepted', 'rejected'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_organization_memberships_invitation_status
    ON organization_memberships(invitation_status, user_id);

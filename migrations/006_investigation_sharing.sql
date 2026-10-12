-- Investigation collaboration: each share points to a separate collaborator-owned copy.
CREATE TABLE IF NOT EXISTS investigation_shares (
    id VARCHAR(36) PRIMARY KEY,
    original_job_id VARCHAR(36) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    shared_job_id VARCHAR(36) NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    owner_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    collaborator_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    permission VARCHAR(16) NOT NULL CHECK (permission IN ('read', 'comment', 'edit')),
    base_snapshot JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_investigation_share_collaborator UNIQUE (original_job_id, collaborator_user_id),
    CONSTRAINT ck_investigation_share_not_self CHECK (owner_user_id <> collaborator_user_id)
);
CREATE INDEX IF NOT EXISTS ix_investigation_shares_original_job_id ON investigation_shares(original_job_id);
CREATE INDEX IF NOT EXISTS ix_investigation_shares_shared_job_id ON investigation_shares(shared_job_id);
CREATE INDEX IF NOT EXISTS ix_investigation_shares_owner_user_id ON investigation_shares(owner_user_id);
CREATE INDEX IF NOT EXISTS ix_investigation_shares_collaborator_user_id ON investigation_shares(collaborator_user_id);

CREATE TABLE IF NOT EXISTS investigation_comments (
    id VARCHAR(36) PRIMARY KEY,
    share_id VARCHAR(36) NOT NULL REFERENCES investigation_shares(id) ON DELETE CASCADE,
    author_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    body TEXT NOT NULL CHECK (length(trim(body)) > 0 AND length(body) <= 10000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_investigation_comments_share_id ON investigation_comments(share_id);
CREATE INDEX IF NOT EXISTS ix_investigation_comments_author_user_id ON investigation_comments(author_user_id);

-- Entity/profile reconstruction and investigator graph layer.
-- Does not modify or delete findings/correlations.

CREATE TABLE IF NOT EXISTS entities (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    label VARCHAR(200) NOT NULL,
    entity_type VARCHAR(32) NOT NULL DEFAULT 'person_candidate',
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_entities_job_id ON entities(job_id);

CREATE TABLE IF NOT EXISTS entity_findings (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    finding_id VARCHAR(36) NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    role VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_entity_finding UNIQUE(entity_id, finding_id)
);

CREATE INDEX IF NOT EXISTS ix_entity_findings_entity_id ON entity_findings(entity_id);
CREATE INDEX IF NOT EXISTS ix_entity_findings_finding_id ON entity_findings(finding_id);

CREATE TABLE IF NOT EXISTS relationships (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    entity_a_id VARCHAR(36) NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    entity_b_id VARCHAR(36) NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relationship_type VARCHAR(64) NOT NULL,
    basis TEXT NOT NULL,
    assessment VARCHAR(32) NOT NULL DEFAULT 'indeterminado',
    assessment_note TEXT,
    assessment_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_entity_relationship UNIQUE(job_id, entity_a_id, entity_b_id, relationship_type),
    CONSTRAINT ck_relationship_not_self CHECK(entity_a_id <> entity_b_id)
);

CREATE INDEX IF NOT EXISTS ix_relationships_job_id ON relationships(job_id);
CREATE INDEX IF NOT EXISTS ix_relationships_entity_a_id ON relationships(entity_a_id);
CREATE INDEX IF NOT EXISTS ix_relationships_entity_b_id ON relationships(entity_b_id);

CREATE TABLE IF NOT EXISTS relationship_evidence (
    id VARCHAR(36) PRIMARY KEY,
    relationship_id VARCHAR(36) NOT NULL REFERENCES relationships(id) ON DELETE CASCADE,
    correlation_id VARCHAR(36) REFERENCES correlations(id) ON DELETE SET NULL,
    finding_a_id VARCHAR(36) REFERENCES findings(id) ON DELETE SET NULL,
    finding_b_id VARCHAR(36) REFERENCES findings(id) ON DELETE SET NULL,
    CONSTRAINT uq_relationship_correlation_evidence UNIQUE(relationship_id, correlation_id)
);

CREATE INDEX IF NOT EXISTS ix_relationship_evidence_relationship_id ON relationship_evidence(relationship_id);
CREATE INDEX IF NOT EXISTS ix_relationship_evidence_correlation_id ON relationship_evidence(correlation_id);

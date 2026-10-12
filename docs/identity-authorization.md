# Identity, entity verification and authorization rollout (migrations 004, 006 and 007)

## Policy contract

- A user may belong to multiple organizations; membership roles are scoped per organization.
- Personal investigation: accountable owner set, organization_id NULL.
- Organizational investigation: accountable owner set and organization_id set. The owner must be an active member of that organization when the job is created.
- `investigator`: read/write own jobs; cannot see other investigators' organizational jobs by default.
- `entity`: can read all investigations in their organization and manage that organization's memberships; cannot modify investigation content or enqueue searches.
- `superuser`: platform-wide administrative access.
- `user`: reserved for future read-only/public features; no public publication endpoint is introduced.
- Public registration is limited to `investigator` and `user`; an account cannot self-assign `entity` or `superuser`.
- A `superuser` creates an entity account with global role `entity`, then provisions its organization using a unique identifier and the same account email. The provisioning action stores `contact_email`, `verified_at` and `verified_by_user_id` for audit. This is an administrative verification step, not automated email-domain verification.
- Entity accounts can add or remove investigator memberships but cannot promote users to the entity role. The last active entity manager cannot be removed.
- Historical jobs remain ownerless after migration 004. They must not be assigned to the first account automatically. Until audited reassignment, only a superuser should be allowed to inspect or claim them.
- API authentication is bearer-token based; UI visibility is not an authorization boundary.
- Authentication and authorization must not change OSINT source, collection, normalization, correlation, or graph semantics.

## Migration

Back up PostgreSQL first, then run migrations 002, 003 (if not already applied), 004, 006 and 007 in order. Migrations 004, 006 and 007 are additive and idempotent; they do not drop or rewrite findings, correlations, entities, or relationships. Migration 004 deliberately leaves ownership columns nullable for a controlled historical-record transition. Migration 007 adds the entity global role and organization verification metadata; existing organizations remain unverified until an administrator reviews them.

After deploying authorization, inventory ownerless jobs and reassign them explicitly with an audit trail. Only after the count of ownerless jobs is zero should a later migration set `jobs.owner_user_id NOT NULL`.

## Rollback

Do not drop the new tables/columns as an automatic rollback: accounts or memberships may already reference jobs. Roll back application code first and retain the additive schema until a reviewed data migration is planned.

## Verification checklist

- [ ] Back up PostgreSQL and confirm migrations 002/003 status.
- [ ] Apply 004, 006 and 007 to a copy of production data first.
- [ ] Bootstrap first superuser out-of-band; never ship a default password.
- [ ] Test personal/organizational job access, cross-user isolation, multi-organization membership, entity read-only behavior, administrative entity provisioning, and superuser access.
- [ ] Confirm denied requests do not enqueue Celery tasks.
- [ ] Confirm all indirect identifiers (finding/entity/relationship/correlation) resolve authorization through their parent job.
- [ ] Audit ownerless jobs before enforcing NOT NULL.
- [ ] Remove tracked `.env` from Git history/working tree as appropriate, rotate any real secrets, and keep only `.env.example`.

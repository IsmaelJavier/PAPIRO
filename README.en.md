# PAPIRO — assisted reconstruction of open digital footprints

PAPIRO is an OSINT platform prototype for organizing public evidence, examining matches between findings, and building candidate profiles and relationships for investigator review. Its intended workflow is traceable: results should retain their sources and must not automatically become claims about a person's identity.

**Status:** working prototype under development. It includes an API, web interface, persistence, collection from selected public sources, deterministic correlation, and an investigation workspace with a graph. It is not a general-purpose OSINT platform or a production-ready product.

- [Leer en español](README.md)
- [Читать на русском](README.ru.md)

## What it currently supports

- Create an investigation and explicitly run a name search.
- Query the currently configured sources: GitHub and Wikidata.
- Store findings with their available URLs and provenance.
- Extract indicators from public fields returned by the sources.
- Detect exact matches between normalized indicators from different sources.
- Review and assess correlations without automatically treating them as confirmed identities.
- Create candidate profiles, associate findings with them, and define relationships between profiles.
- Explore findings, indicators, correlations, profiles, and relationships in the investigation interface.
- Use accounts with different roles and permissions to access investigations.

## Current limitations

- No artificial intelligence, language models, or machine learning are used.
- Searches do not autonomously iterate until no new indicators are found.
- The system does not search the entire web or guarantee social-network coverage.
- It does not prove that two findings belong to the same person; a match is a lead requiring review.
- It should not be treated as a surveillance, definitive identification, or identity-verification tool.
- Not all graph-editing operations are implemented. Hiding an item in the view does not delete it from the database.
- This documentation does not claim production-grade security, performance, or formal validation.

## Current architecture

- **API and interface:** FastAPI.
- **Asynchronous processing:** Celery and Redis.
- **Primary persistence:** PostgreSQL.
- **Graph visualization:** Cytoscape.js in the web interface.
- **Name-search sources:** GitHub and Wikidata.
- **Correlation:** deterministic matching of exact normalized indicators across different sources.

High-level workflow:

`Investigation → explicit search → findings and indicators → correlations → candidate profiles and relationships → investigator assessment`

PostgreSQL stores application data; Redis coordinates asynchronous tasks. Neo4j, Elasticsearch, and MinIO are not part of the active workflow described by this configuration.

## Requirements

- Git.
- Docker and Docker Compose.
- Internet access to download images and query public sources.
- Optionally, a GitHub token for higher API rate limits.

The current `docker-compose.yml` uses `network_mode: host` and loopback addresses. It targets the development environment for which the project was configured; Windows/macOS Docker Desktop and other deployment environments may require network configuration changes. Do not expose ports or services to untrusted networks without reviewing the configuration.

## Local installation

Clone the repository:

```bash
git clone https://github.com/Starv1ng/Kami-no-Eye.git
cd Kami-no-Eye
git switch main
```

Create the environment file:

```bash
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env`.

Edit `.env` and replace `AUTH_SECRET_KEY` with your own random secret of at least 32 characters. Generate one with Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not commit `.env` or reuse a secret from another installation. `GITHUB_TOKEN` is optional; leave it empty if you do not configure one.

Build and start the services:

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 api worker postgres redis
```

Expected local URLs:

- Interface: http://127.0.0.1:8000/ui
- API documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

If startup fails, inspect the logs and check Docker networking compatibility with your operating system. The development Compose configuration contains local credentials; change and review them before any shared or production deployment.

## Database and initial administrator

On startup, the application creates tables represented by its models, but this **does not replace every migration** needed for an existing database or for identity, entity, and collaboration features.

Before applying migrations to a database containing data, back it up and determine which migrations have already run. Do not delete the `pgdata` volume to troubleshoot errors: it contains PostgreSQL persistence.

For a new database, inspect the migrations and apply those required by the current schema. The documented sequence for enabling the current feature set is:

1. Apply `migrations/002_correlation_and_nomenclature.sql`.
2. Apply `migrations/003_entities_graph.sql`.
3. Run `docker compose exec api python -m scripts.apply_identity_migration` for identity migration 004.
4. Apply `migrations/006_investigation_sharing.sql`.
5. Apply `migrations/007_entity_accounts_and_verification.sql`.

From the repository root, SQL migrations 002, 003, 006, and 007 can be applied, for example, with:

```bash
cat migrations/002_correlation_and_nomenclature.sql | docker compose exec -T postgres psql -U kami -d kami_eye
```

Repeat the command with the appropriate migration file. Migration 004 uses the Python command above. If the database already contains data, do not run migrations blindly: inspect their contents and the actual schema first.

Create the first administrator **only after applying the identity migration**:

```bash
docker compose exec -it api python -m scripts.bootstrap_superuser
```

The script prompts for an email and password twice and requires a password of at least 12 characters. It refuses to run if any account already exists. No demo credentials are predefined.

## Try PAPIRO

1. Open http://127.0.0.1:8000/ui and sign in with a valid account.
2. If public registration is enabled on the instance, create an investigator account. Institutional-account requests require administrator approval.
3. Create an investigation in the interface.
4. Manually start a name search. **Creating an investigation does not start collection by itself.**
5. Review findings and their sources; inspect indicators and proposed correlations.
6. Create a candidate profile, associate findings, and define relationships when there is a basis to investigate them.
7. Assess correlations and relationships as confirmed, discarded, or indeterminate using the available options. Record the rationale.
8. Open the graph from the investigation workspace and check that items can be traced back to their source evidence.

Use public data only and treat results as research leads. A matching name, alias, or indicator alone is not enough to attribute an identity.

## Automated tests

From the project root:

```bash
docker compose run --rm api pytest -q
```

Results depend on the code version, configuration, and environment. This README does not claim that the entire suite currently passes: run the tests before accepting changes or deploying, and investigate each failure. Tests that mock HTTP responses verify logic under controlled conditions; they do not replace an end-to-end test against real services.

## Security and responsible use

- Configure a strong, unique secret in `.env`; never commit it.
- Do not expose a development instance directly to the Internet.
- Back up the database before migrations or schema changes.
- Preserve evidence provenance and document investigator decisions.
- Limit collection to public information and lawful, authorized purposes.
- Before production, review authentication, session handling, rate limiting, networking, secrets, permissions, and data-retention policy.

## Future work

Areas for further work include expanding and evaluating data sources, improving persistent graph editing, streamlining evidence and correlation review, completing authorization and UI tests, making installation more portable, and formally validating the method and platform behavior.

These are future work items, not features that should be assumed to be implemented already.

## License

Check the repository for the project's license status. This README does not itself grant additional redistribution or usage rights.

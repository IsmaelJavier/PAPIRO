# PAPIRO

PAPIRO is an OSINT prototype for collecting public information, reviewing matches, and organizing findings into candidate profiles and an investigation graph. **Matches are leads, not identity confirmation.**

- [Español](README.md) · [Русский](README.ru.md)

## Implemented

- Web interface and API with authentication and roles.
- Name search across **GitHub and Wikidata**.
- Findings with source URLs and indicators extracted from public data.
- Deterministic correlation based on exact matches between normalized indicators.
- Candidate profiles, finding associations, and relationships.
- Investigation workspace to review evidence and explore the graph.

## Installation

Requirements: Git, Docker, and Docker Compose. The current Docker configuration uses `network_mode: host`; Docker Desktop and other environments may require network adjustments.

```bash
git clone https://github.com/Starv1ng/Kami-no-Eye.git
cd Kami-no-Eye
git switch main
cp .env.example .env
```

Edit `.env` and replace `AUTH_SECRET_KEY` with your own random secret of at least 32 characters. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start the services:

```bash
docker compose up --build -d
docker compose ps
```

Open the app at [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui). API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

**Database:** for a new installation with all identity and role features, review and apply migrations in `migrations/` (002, 003, 004, 006, and 007, in that order; apply 004 with `docker compose exec api python -m scripts.apply_identity_migration`). Back up an existing database before migrating. Do not delete the `pgdata` volume.

After migration 004, create the first administrator:

```bash
docker compose exec -it api python -m scripts.bootstrap_superuser
```

The script prompts for an email and password (at least 12 characters). It only runs if no account exists yet.

## Try it

1. Sign in to the interface.
2. Create an investigation.
3. **Manually start** a name search; creating an investigation does not start a search.
4. Review findings, sources, indicators, and correlations.
5. Create candidate profiles, associate evidence, and inspect relationships in the graph.
6. Assess matches carefully: they do not prove that findings belong to the same person.

Run automated tests:

```bash
docker compose run --rm api pytest -q
```

## Future work

- Iterative searches using newly discovered indicators.
- More sources and broader coverage.
- More complete graph editing and persistence.
- Additional UI, authorization, and installation tests.
- Formal validation of the method and platform evaluation.

PAPIRO is still under development, does not use AI/ML, and is not production-ready. Use public data lawfully and review security settings before exposing the app to other networks.

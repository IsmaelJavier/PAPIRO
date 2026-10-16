# PAPIRO

PAPIRO is an OSINT prototype for collecting public information, reviewing matches, and organizing findings into candidate profiles and an investigation graph. **A match is a lead, not proof of identity.**

- [Español](README.md) · [Русский](README.ru.md)

## What you can do

- Create investigations and start name searches.
- Query the configured sources: **GitHub and Wikidata**.
- Review findings with their sources, URLs, and indicators.
- Inspect deterministic correlations based on exact matches between normalized indicators.
- Create candidate profiles, associate evidence, and explore relationships in the graph.
- Use authenticated investigator accounts.

## Quick installation

Requirements: Git, Docker, and Docker Compose. Clone the repository:

```bash
git clone https://github.com/Starv1ng/Kami-no-Eye.git
cd Kami-no-Eye
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead.

Edit `.env` and replace `AUTH_SECRET_KEY` with your own random secret of at least 32 characters. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start the application:

```bash
docker compose up --build -d
docker compose ps
```

Open the [web interface](http://127.0.0.1:8000/ui). The [API documentation](http://127.0.0.1:8000/docs) is available for technical use.

**Do you need to run migrations?**
- **Fresh clone with an empty database:** no. On startup, the application creates tables for the current models.
- **An existing database from an older version:** migrations may be required. Back up the database first, then inspect the migration instructions and actual schema before running scripts in `migrations/`. Do not delete the `pgdata` volume.

The current Docker configuration uses `network_mode: host`; some operating systems or Docker Desktop setups may require network adjustments.

## How to use it

1. Open the interface and select **Create account** to register as an **Investigator**. Passwords must be at least 12 characters.
2. Sign in and create an investigation.
3. Manually start a name search; creating an investigation does not start one automatically.
4. Review findings, sources, indicators, and correlations.
5. Create candidate profiles, associate evidence, and explore graph relationships.
6. Treat matches cautiously: they are not definitive identity evidence.

If you need a superuser account for administration, create it **before registering any other account**:

```bash
docker compose exec -it api python -m scripts.bootstrap_superuser
```

The script asks for an email and password twice, requires at least 12 characters, and only works when no account exists yet.

## Tests

```bash
docker compose run --rm api pytest -q
```

Run the tests in your own environment; this README does not assume that every test currently passes.

## Future work

- Iterative searches based on newly discovered indicators.
- More sources and broader coverage.
- More complete persistent graph editing and deletion.
- Additional UI, authorization, and installation tests.
- Formal validation of the method and platform evaluation.

PAPIRO is still under development, does not use AI/ML, and is not production-ready. Use public information lawfully and review security before exposing the instance to other networks.

# PAPIRO

**PAPIRO is an OSINT platform under development for investigating people using publicly available information.** It gathers findings from supported sources, organizes indicators, surfaces possible matches, and helps investigators build candidate profiles and explore relationships in a graph.

Its purpose is to help investigators organize and assess leads—not to automatically establish a person's identity or replace human verification.

- [Español](README.md) · [Русский](README.ru.md)

## Current capabilities

- Create investigations and manually launch name searches.
- Query the implemented sources: **GitHub and Wikidata**.
- Review findings with their URLs, provenance, and indicators.
- Identify correlations through exact matches between normalized indicators.
- Create candidate profiles, associate findings, and explore relationships in a graph.
- Use authenticated investigator accounts.

## Known limitations

- Source coverage is limited, and name searches must be started manually.
- Correlation is deterministic: a matching indicator is a lead, not a confirmed identity.
- Iterative searches based on newly discovered findings and broader source coverage are still pending.
- Persistent editing and deletion of graph elements need further work.
- The platform does not use AI/ML and still needs additional testing and formal validation.
- **It is not production-ready** and should not be exposed to untrusted networks without a security review.

## Installation

Requirements: Git, Docker, and Docker Compose.

```bash
git clone https://github.com/Starv1ng/Kami-no-Eye.git
cd Kami-no-Eye
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead of the last command.

Edit `.env` and replace `AUTH_SECRET_KEY` with your own random secret of at least 32 characters. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start the services:

```bash
docker compose up --build -d
docker compose ps
```

- Web interface: http://127.0.0.1:8000/ui
- API documentation: http://127.0.0.1:8000/docs

The current configuration uses `network_mode: host`; some operating systems or Docker Desktop setups may require network adjustments.

## First use

1. Open the interface and create an **Investigator** account. Passwords must be at least 12 characters.
2. Sign in and create an investigation.
3. Manually start a name search.
4. Review findings, sources, indicators, and correlations.
5. If useful, organize findings into candidate profiles and explore graph relationships.

To create a superuser account, run the following command **before registering any other account**:

```bash
docker compose exec -it api python -m scripts.bootstrap_superuser
```

The script asks for the email and password twice and requires a password of at least 12 characters. It only works when no account exists yet.

## Tests

```bash
docker compose run --rm api pytest -q
```

Run the tests in your own environment; this README does not guarantee that all tests pass in every version.

## Responsible use

Investigate only with a lawful basis and respect privacy and source terms. Verify each finding against its context and provenance. **Do not treat a match, candidate profile, or graph relationship as definitive proof of identity.**

If you use a database from an older version, back it up and review the schema and migration instructions before applying changes. Do not delete the Docker `pgdata` volume.

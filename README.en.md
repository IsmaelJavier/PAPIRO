# PAPIRO

**PAPIRO is an OSINT platform under development for investigating people using publicly available information.** Its long-term goal is to automate as much of the process as possible: collect information from multiple sources, discover and correlate indicators, resolve candidate identities, and expand investigations iteratively as new data emerges, including when working with large volumes of information.

This is the project's intended direction, not the level of automation available in the current version. PAPIRO currently provides an initial functional foundation for running limited searches, organizing findings, and examining correlations. Significant work remains before it can support automated, iterative, and scalable investigations.

- [Español](README.md) · [Русский](README.ru.md)

## Current capabilities

- Create investigations and manually launch name searches.
- Query the implemented sources: **GitHub and Wikidata**.
- Review findings alongside their URLs, provenance, and indicators.
- Detect correlations through exact matches between normalized indicators.
- Create candidate profiles, associate findings, and explore relationships in a graph.
- Manage access through authenticated accounts.

## Current limitations and development priorities

- Source coverage is limited, and searches must be started manually.
- Correlation is based on deterministic rules and exact matches; it is not yet a complete identity-resolution mechanism.
- Iteratively expanding searches from new findings and large-scale analysis remain pending.
- Persistent editing and deletion of graph elements need improvement.
- The platform does not use AI/ML and needs more testing and formal validation.
- Reducing these limitations, refactoring the code, and strengthening security are priorities.

## Installation

Requirements: Git, Docker, and Docker Compose.

```bash
git clone https://github.com/Starv1ng/PAPIRO.git PAPIRO
cd PAPIRO
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead of the last command.

Edit `.env` and set a cryptographically random authentication secret of at least 32 characters.

Start the services:

```bash
docker compose up --build -d
docker compose ps
```

- Web interface: http://127.0.0.1:8000/ui
- API documentation: http://127.0.0.1:8000/docs

The current configuration uses `network_mode: host`; some operating systems or Docker Desktop configurations may require network adjustments.

## First use

1. Open the interface and create an **Investigator** account. The password must be at least 12 characters long.
2. Sign in and create an investigation.
3. Manually run a name search.
4. Review findings, their sources, indicators, and correlations.
5. Organize findings into candidate profiles and explore graph relationships when necessary.

## User types

- **Investigator:** can conduct private investigations or investigations for an entity they belong to.
- **Entity:** can manage multiple investigators.

Test-account details are documented in the Spanish README.

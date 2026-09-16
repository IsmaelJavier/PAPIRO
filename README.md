# OSINT MVP — ruta mínima verificable

MVP construido desde cero para validar primero el flujo y el modelo de datos con una sola fuente real: GitHub.

## Flujo

`POST /api/v1/ingest/name` → PostgreSQL Job → Celery/Redis → GitHub → perfil público → normalización → Finding + Indicators → PostgreSQL → `GET /api/v1/jobs/{job_id}`.

## Principios

- PostgreSQL es la fuente de verdad.
- Redis solo coordina Celery.
- No hay Elasticsearch/Neo4j/MinIO todavía.
- No hay IA, ML ni LLM.
- No hay búsqueda iterativa todavía.
- Un candidato devuelto por GitHub NO se afirma automáticamente como la misma persona.
- Cada finding conserva `raw_evidence`, fuente, URL, input, score y razón del score.
- Los indicadores se crean solo de campos públicos realmente devueltos por la fuente.

## Arranque

```bash
cp .env.example .env
docker compose up --build
```

Swagger: `http://localhost:8000/docs`

Crear trabajo:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/name \
  -H "Content-Type: application/json" \
  -d '{"name":"Monalisa Octocat"}'
```

Consultar:

```bash
curl http://localhost:8000/api/v1/jobs/<JOB_ID>
curl http://localhost:8000/api/v1/jobs/<JOB_ID>/findings
```

## Token de GitHub

`GITHUB_TOKEN` es opcional. Para uso público no es obligatorio, pero autenticarse aumenta los límites de API.

## Tests

```bash
docker compose run --rm api pytest -q
```

Los tests HTTP utilizan `MockTransport` únicamente para validar lógica determinista. La prueba E2E real debe hacerse con Docker Compose y GitHub.

## Próximo incremento

Solo cuando este flujo sea estable: entrada `username` → búsqueda directa del perfil → reutilización del mismo modelo `Finding`/`Indicator`. Después: iteración, correlación, Elasticsearch y Neo4j.

## Wikidata source

The person-name ingestion now queries two independent public sources:

- GitHub (`github_person_search`)
- Wikidata (`wikidata_person_search`)

The Wikidata module uses the public Wikibase Action API (`wbsearchentities` followed by `wbgetentities`) and stores each returned entity as a canonical finding. It exposes the Wikidata Q-ID and available English/Spanish Wikipedia sitelinks as indicators. As with GitHub, evidence strength is not an identity probability; identity and relevance remain investigator assessments.

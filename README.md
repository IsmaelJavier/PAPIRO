# OSINT MVP — ruta mínima verificable

MVP construido desde cero para validar primero el flujo y el modelo de datos con una sola fuente real: GitHub.

## Flujo

`POST /api/v1/ingest/name` → PostgreSQL Job → Celery/Redis → GitHub → perfil público → normalización → Finding + Indicators → correlación determinista → PostgreSQL → `GET /api/v1/jobs/{job_id}`.

## Principios

- PostgreSQL es la fuente de verdad.
- Redis solo coordina Celery.
- No hay Elasticsearch/Neo4j/MinIO todavía.
- No hay IA, ML ni LLM.
- No hay búsqueda iterativa todavía.
- Un candidato devuelto por GitHub NO se afirma automáticamente como la misma persona.
- Cada finding conserva `raw_evidence`, fuente, URL, input, fuerza de evidencia (`evidence_strength`) y razón de coincidencia (`match_reason`).
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

Siguiente incremento implementado:

- contrato común `PersonSource` para las fuentes de búsqueda por nombre;
- nomenclatura semántica: `evidence_strength` y `match_reason`;
- correlación determinista entre hallazgos de fuentes diferentes mediante indicadores normalizados;
- evaluación independiente de las correlaciones (`indeterminado`, `confirmada`, `descartada`);
- la correlación no determina automáticamente identidad.

### Migración

Para conservar los datos existentes, ejecutar:

```bash
cat migrations/002_correlation_and_nomenclature.sql | docker compose exec -T postgres psql -U kami -d kami_eye
```

La migración renombra `findings.confidence` a `findings.evidence_strength`, `findings.relevance_reason` a `findings.match_reason` y crea las tablas de correlación. No se debe eliminar el volumen de PostgreSQL.

### Correlación

Consultar las correlaciones de un trabajo:

```bash
curl http://localhost:8000/api/v1/jobs/<JOB_ID>/correlations
```

La correlación usa únicamente coincidencias exactas de indicadores normalizados entre fuentes diferentes. El nombre original de la consulta no se utiliza como evidencia de correlación.

Evaluar una correlación:

```bash
curl -X PATCH http://localhost:8000/api/v1/correlations/<CORRELATION_ID>/assessment \
  -H "Content-Type: application/json" \
  -d '{"assessment":"confirmada","assessment_note":"Existe evidencia independiente que justifica la asociación."}'
```


## Wikidata source

The person-name ingestion now queries two independent public sources:

- GitHub (`github_person_search`)
- Wikidata (`wikidata_person_search`)

The Wikidata module uses the public Wikibase Action API (`wbsearchentities` followed by `wbgetentities`) and stores each returned entity as a canonical finding. It exposes the Wikidata Q-ID and available English/Spanish Wikipedia sitelinks as indicators. As with GitHub, evidence strength is not an identity probability; identity and relevance remain investigator assessments.

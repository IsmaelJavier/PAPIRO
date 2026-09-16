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

## Entidades, perfiles y grafo de investigación

El tercer incremento añade una capa de reconstrucción gestionada por el investigador. Una `Entity` representa un candidato de perfil dentro de un trabajo; no equivale automáticamente a una persona real ni resuelve identidad.

Flujo:

`Finding → Indicator → Correlation → Entity → Relationship → Graph`

### Principios de la capa de entidad

- Una entidad se crea explícitamente como contenedor de investigación (`person_candidate`).
- Los findings se pueden asociar a una entidad con un rol descriptivo.
- Las relaciones entre entidades son independientes de la identidad y comienzan en `indeterminado`.
- Una relación puede documentar la correlación que la sustenta mediante `correlation_id` y findings.
- La API mantiene trazabilidad desde el grafo hacia findings, indicadores y fuentes.
- No se fusionan automáticamente personas ni se emiten conclusiones de identidad.

### API de exploración

Obtener la proyección completa del grafo:

```bash
curl http://localhost:8000/api/v1/jobs/<JOB_ID>/graph
```

Abrir la visualización interactiva en el navegador:

```text
http://localhost:8000/ui/graph/<JOB_ID>
```

Crear una entidad candidata:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/<JOB_ID>/entities \
  -H "Content-Type: application/json" \
  -d '{"label":"Candidato 1","description":"Agrupación para evaluación del investigador"}'
```

Asociar un finding:

```bash
curl -X POST http://localhost:8000/api/v1/entities/<ENTITY_ID>/findings \
  -H "Content-Type: application/json" \
  -d '{"finding_id":"<FINDING_ID>","role":"perfil"}'
```

Crear una relación entre entidades:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/<JOB_ID>/relationships \
  -H "Content-Type: application/json" \
  -d '{"entity_a_id":"<ENTITY_A>","entity_b_id":"<ENTITY_B>","relationship_type":"associated_with","basis":"shared_username:johnsmith","correlation_id":"<CORRELATION_ID>"}'
```

Evaluar una relación:

```bash
curl -X PATCH http://localhost:8000/api/v1/relationships/<RELATIONSHIP_ID>/assessment \
  -H "Content-Type: application/json" \
  -d '{"assessment":"confirmada","assessment_note":"La relación fue revisada por el investigador."}'
```

### Migración 003

Con PostgreSQL activo y después de ejecutar la migración 002:

```bash
cat migrations/003_entities_graph.sql | docker compose exec -T postgres psql -U kami -d kami_eye
```

No se debe eliminar el volumen de PostgreSQL.

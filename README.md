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

## Visualización del grafo en GitHub Codespaces

La API expone una interfaz web en:

`/ui/graph/{job_id}`

En Codespaces, abre el panel **Ports**, localiza el puerto `8000` y pulsa el icono de abrir en navegador (globe). Después añade `/ui/graph/<JOB_ID>` a la dirección, por ejemplo:

`https://<codespace>-8000.app.github.dev/ui/graph/ac1d9bb2-86c1-4259-a370-1b8d4d1fc673`

La interfaz consulta automáticamente `/api/v1/jobs/{job_id}/graph` y permite filtrar por tipo de nodo y fuente, buscar etiquetas y seleccionar nodos/aristas para inspeccionar la evidencia.

## Espacio de investigación (UI)

La ruta `/ui/job/<JOB_ID>` (y la ruta anterior `/ui/graph/<JOB_ID>`) sirve ahora como espacio de trabajo del investigador. El objetivo de esta iteración es permitir la reconstrucción asistida sin utilizar la consola:

1. Revisar los findings recolectados y sus evaluaciones.
2. Seleccionar uno o varios findings como evidencia.
3. Crear una entidad/perfil candidato y asociarle esa evidencia en una sola operación.
4. Abrir el perfil para consultar findings, indicadores y relaciones.
5. Seleccionar dos entidades y crear una relación desde la interfaz.
6. Confirmar, descartar o mantener indeterminada una relación.
7. Confirmar, descartar o mantener indeterminadas las correlaciones y los findings.
8. Navegar entre el grafo y el detalle de cada elemento, conservando la trazabilidad hacia la fuente.

La UI no convierte una correlación en una identidad ni una entidad en una persona confirmada. Las agrupaciones y relaciones son objetos de investigación que requieren evaluación del investigador.

### Migración de esta iteración

Antes de utilizar entidades y relaciones en una base existente, ejecutar una vez:

```bash
cat migrations/003_entities_graph.sql | docker compose exec -T postgres psql -U kami -d kami_eye
```

Luego reiniciar API y worker si es necesario:

```bash
docker compose restart api worker
```

En GitHub Codespaces, abrir el puerto `8000` desde **Ports → Open in Browser** y añadir:

```text
/ui/job/<JOB_ID>
```

Por ejemplo:

```text
https://<codespace>-8000.app.github.dev/ui/job/ac1d9bb2-86c1-4259-a370-1b8d4d1fc673
```

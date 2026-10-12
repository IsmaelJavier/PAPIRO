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

## Correcciones y mejoras del espacio de investigación

La interfaz `/ui/job/{JOB_ID}` incorpora ahora:

- Persistencia local de la posición de los nodos del grafo al arrastrarlos, evitando que una evaluación de finding reorganice el grafo de forma aleatoria.
- Ocultación/recuperación de nodos sin eliminar evidencia de la base de datos.
- Controles para mostrar u ocultar indicadores, correlaciones y aristas de pertenencia.
- Edición del nombre y descripción de entidades candidatas.
- Asociación posterior de varios findings seleccionados a una entidad existente.
- Edición del tipo y base de una relación.
- Nueva búsqueda de persona contra las fuentes configuradas mediante `POST /api/v1/jobs/{job_id}/search/name`; los findings nuevos se incorporan a la investigación y, cuando corresponde, se recalculan las correlaciones deterministas.

Las posiciones y nodos ocultos son preferencias locales del navegador en esta iteración; no modifican la evidencia ni eliminan datos. La persistencia server-side de la vista podrá añadirse posteriormente.


## Identidad, entidades y autorización

La rama `feature/identity-authorization` incorpora autenticación y autorización por recurso, colaboración mediante copias independientes y gestión de entidades institucionales. No modifica la lógica de recolección OSINT, normalización, correlación ni reconstrucción del grafo.

### Política de acceso

- Las investigaciones personales tienen un investigador responsable.
- Una investigación organizativa tiene un responsable y un `organization_id`.
- Los investigadores solo consultan y modifican sus propias investigaciones, salvo una copia que les haya sido compartida explícitamente.
- Las cuentas con rol global `entity` pueden consultar las investigaciones de su organización y administrar las membresías de investigadores, pero no modificar ni eliminar el contenido de las investigaciones.
- Un investigador no obtiene acceso a los expedientes de sus compañeros solo por pertenecer a la misma organización.
- `superuser` conserva el acceso administrativo global.
- El registro público solo permite `investigator` y `user`. Una cuenta no puede asignarse a sí misma el rol `entity`.

### Configuración y migraciones

1. Copia `.env.example` a `.env` y establece `AUTH_SECRET_KEY` con un secreto aleatorio de al menos 32 caracteres.
2. Haz una copia de seguridad de PostgreSQL y confirma que las migraciones 002 y 003 están aplicadas.
3. Aplica la migración 004 con `docker compose exec api python -m scripts.apply_identity_migration`.
4. Aplica las migraciones de colaboración y entidades, en este orden:
   ```bash
   cat migrations/006_investigation_sharing.sql | docker compose exec -T postgres psql -U kami -d kami_eye
   cat migrations/007_entity_accounts_and_verification.sql | docker compose exec -T postgres psql -U kami -d kami_eye
   ```
5. Crea el primer administrador de forma interactiva: `docker compose exec -it api python -m scripts.bootstrap_superuser`.
6. Abre `http://127.0.0.1:8000/ui`. Las cuentas de investigador y público pueden registrarse; las cuentas de entidad y administración deben crearse desde el panel administrativo.

Las migraciones 004, 006 y 007 son idempotentes y no requieren eliminar volúmenes. Los trabajos históricos sin propietario no se asignan automáticamente: deben auditarse y reasignarse explícitamente.

### Alta de una entidad institucional

1. En el panel administrativo, crea una cuenta con rol **Entidad verificada**.
2. Verifica la identidad institucional fuera de la plataforma.
3. Registra la entidad usando su identificador único y el correo de esa cuenta. El sistema guarda el correo de contacto, la fecha de verificación y el administrador responsable.
4. Inicia sesión con la cuenta de entidad para consultar las investigaciones de la organización y administrar las membresías.

La verificación institucional es una operación administrativa; no implica verificación automática del dominio ni envío de un correo de confirmación. No se debe conceder el rol de entidad sin comprobar la identidad por un canal fiable.

Los responsables de entidad pueden añadir cuentas existentes de investigador y retirar sus membresías. No pueden convertir otras cuentas en entidades ni eliminar al último responsable activo. Para crear una investigación organizativa, el investigador selecciona la organización a la que pertenece en el formulario de nueva investigación.

### Colaboración entre investigadores

Compartir una investigación crea una copia independiente con permiso de lectura, lectura y comentarios, o edición. Los cambios de la copia no alteran el original hasta que el responsable incorpora la copia mediante el proceso de merge; si el original cambió desde la creación de la copia, el merge se rechaza para evitar sobrescrituras.

### Importante antes de producción

- La UI del grafo almacena el bearer token en `localStorage`; antes de producción conviene valorar una cookie `HttpOnly` y añadir protección contra fuerza bruta.
- CI ejecuta las pruebas de Python, comprobaciones de sintaxis JavaScript y una prueba de humo de migraciones sobre PostgreSQL, incluidas segundas ejecuciones para comprobar idempotencia. Antes de desplegar, prueba las migraciones sobre una copia de la base real.
- El historial Git puede conservar versiones antiguas de `.env`. Si contuvo credenciales reales, rótalas y sanea el historial antes de compartir la rama.



## Colaboración de investigaciones: revisión antes de integrar

La rama `feature/collaboration-pull-request-flow` añade un flujo de propuesta tipo pull request:

1. Compartir crea una copia independiente para el investigador colaborador.
2. El propietario original revisa la diferencia de esa copia desde `Pull / Merge`.
3. El propietario marca como revisada una versión concreta; cualquier edición posterior invalida esa revisión.
4. La API rechaza la integración si no existe revisión vigente o si el original cambió desde la base compartida.
5. El hilo de comentarios se consulta por `share_id`, por lo que tanto el propietario original como el colaborador pueden ver los comentarios permitidos por su rol.

Antes de desplegar esta rama, aplicar la migración aditiva `migrations/008_investigation_share_review.sql` sobre la base de datos existente. Esta migración solo agrega dos columnas a `investigation_shares`; no elimina investigaciones, copias ni comentarios.

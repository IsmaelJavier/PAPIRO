# PAPIRO — reconstrucción asistida de huellas digitales abiertas

PAPIRO es el prototipo de una plataforma OSINT orientada a la investigación de personas para organizar evidencias públicas, examinar coincidencias entre ellas y construir perfiles candidatos y relaciones que un investigador pueda revisar. El proyecto busca ofrecer un flujo de trabajo trazable: los resultados deben conservar su fuente y no convertirse automáticamente en afirmaciones sobre la identidad de una persona.

**Estado:** prototipo funcional en desarrollo. Incluye API, interfaz web, persistencia, recolección desde fuentes públicas seleccionadas, correlación determinista y un espacio de investigación con grafo. No es todavía una plataforma OSINT general ni un producto listo para producción.

- [Read this in English](README.en.md)
- [Читать на русском](README.ru.md)

## Qué permite hacer

- Crear una investigación y ejecutar explícitamente una búsqueda por nombre.
- Consultar resultados de las fuentes configuradas actualmente: GitHub y Wikidata.
- Conservar los hallazgos junto con la URL y los datos de procedencia disponibles.
- Extraer indicadores de campos públicos devueltos por las fuentes.
- Detectar coincidencias exactas entre indicadores normalizados de hallazgos de fuentes diferentes.
- Revisar y evaluar correlaciones sin convertirlas automáticamente en identidades confirmadas.
- Crear perfiles candidatos, asociarles hallazgos y definir relaciones entre perfiles.
- Explorar hallazgos, indicadores, correlaciones, perfiles y relaciones desde la interfaz de investigación.
- Usar cuentas con roles y permisos diferentes para acceder a investigaciones.

## Qué no hace todavía

- No utiliza inteligencia artificial, modelos de lenguaje ni aprendizaje automático.
- No realiza una búsqueda autónoma e iterativa hasta agotar nuevos indicadores.
- No busca de forma universal en toda la web ni garantiza cobertura de redes sociales.
- No demuestra que dos hallazgos correspondan a la misma persona: una coincidencia es una pista que requiere evaluación.
- No debe tratarse como una herramienta de vigilancia, identificación definitiva ni verificación de identidad.
- No todas las operaciones de edición del grafo están implementadas. Ocultar elementos en la vista no equivale a eliminarlos de la base de datos.
- No se ha establecido aquí una garantía de seguridad, rendimiento o validación formal suficiente para producción.

## Arquitectura actual

- **API e interfaz:** FastAPI.
- **Procesamiento asíncrono:** Celery y Redis.
- **Persistencia principal:** PostgreSQL.
- **Visualización del grafo:** Cytoscape.js en la interfaz web.
- **Fuentes de búsqueda por nombre:** GitHub y Wikidata.
- **Correlación:** determinista, basada en coincidencias exactas de indicadores normalizados entre fuentes diferentes.

El flujo general es:

`Investigación → búsqueda explícita → hallazgos e indicadores → correlaciones → perfiles candidatos y relaciones → evaluación del investigador`

PostgreSQL conserva los datos de la aplicación; Redis coordina las tareas asíncronas. Neo4j, Elasticsearch y MinIO no forman parte del flujo activo descrito por esta configuración.

## Requisitos

- Git.
- Docker y Docker Compose.
- Acceso a Internet para descargar imágenes y consultar las fuentes públicas.
- Opcionalmente, un token de GitHub para disponer de límites de API superiores.

La configuración actual de `docker-compose.yml` usa `network_mode: host` y direcciones de loopback. Está orientada al entorno de desarrollo donde se ha preparado el proyecto; en Windows/macOS con Docker Desktop u otros despliegues puede ser necesario adaptar la red antes de arrancar. No expongas los puertos ni el servicio a redes no confiables sin revisar esa configuración.

## Instalación local

Clona el repositorio y entra en su directorio:

```bash
git clone https://github.com/Starv1ng/Kami-no-Eye.git
cd Kami-no-Eye
git switch main
```

Crea el archivo de configuración:

```bash
cp .env.example .env
```

En Windows PowerShell, puedes copiarlo con `Copy-Item .env.example .env`.

Edita `.env` y reemplaza `AUTH_SECRET_KEY` por un secreto aleatorio propio de al menos 32 caracteres. Puedes generar uno con Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

No publiques el archivo `.env` ni reutilices el secreto de otra instalación. `GITHUB_TOKEN` es opcional; déjalo vacío si no vas a configurar uno.

Construye e inicia los servicios:

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 api worker postgres redis
```

Cuando los servicios estén activos, las direcciones locales previstas son:

- Interfaz: http://127.0.0.1:8000/ui
- Documentación de la API: http://127.0.0.1:8000/docs
- Comprobación de salud: http://127.0.0.1:8000/health

Si no arranca, revisa primero los logs y la compatibilidad de la red de Docker con tu sistema. La configuración de desarrollo incluye credenciales locales en el Compose; cámbialas y revisa la configuración antes de cualquier despliegue compartido o de producción.

## Base de datos y primer administrador

La aplicación crea las tablas correspondientes a sus modelos al arrancar, pero eso **no sustituye todas las migraciones** necesarias para una base existente o para habilitar las funciones de identidad, entidades y colaboración.

Antes de aplicar migraciones sobre una base que contenga datos, haz una copia de seguridad y confirma qué migraciones se ejecutaron. No borres el volumen `pgdata` para resolver errores: contiene la persistencia de PostgreSQL.

Para una base de datos nueva, revisa las migraciones y aplícalas en el orden que corresponda a tu estado de esquema. En el flujo documentado para habilitar todas las funciones actuales:

1. Aplica `migrations/002_correlation_and_nomenclature.sql`.
2. Aplica `migrations/003_entities_graph.sql`.
3. Ejecuta `docker compose exec api python -m scripts.apply_identity_migration` para la migración de identidad 004.
4. Aplica `migrations/006_investigation_sharing.sql`.
5. Aplica `migrations/007_entity_accounts_and_verification.sql`.

Las migraciones SQL 002, 003, 006 y 007 pueden aplicarse, por ejemplo, desde la raíz del repositorio con:

```bash
cat migrations/002_correlation_and_nomenclature.sql | docker compose exec -T postgres psql -U kami -d kami_eye
```

Repite el comando con el archivo de migración que corresponda. El método de aplicación de 004 es el comando Python indicado arriba. Si la base ya contiene datos, no ejecutes las migraciones a ciegas: revisa su contenido y el estado real del esquema antes de continuar.

Crea el primer administrador **solo después de aplicar la migración de identidad**:

```bash
docker compose exec -it api python -m scripts.bootstrap_superuser
```

El script solicita correo y contraseña dos veces y exige una contraseña de al menos 12 caracteres. Se niega a ejecutarse si ya existe cualquier cuenta. No hay credenciales de demostración predefinidas.

## Cómo probar PAPIRO

1. Abre http://127.0.0.1:8000/ui e inicia sesión con una cuenta válida.
2. Si el registro público está habilitado en la instancia, crea una cuenta de investigador. Las solicitudes de cuentas institucionales requieren aprobación administrativa.
3. Crea una investigación desde la interfaz.
4. Inicia manualmente una búsqueda por nombre. **Crear una investigación no inicia por sí solo la recolección.**
5. Revisa los hallazgos y sus fuentes; examina los indicadores y las correlaciones propuestas.
6. Crea un perfil candidato, asocia hallazgos y define relaciones cuando exista una base que justifique examinarlas.
7. Evalúa las correlaciones y relaciones como confirmadas, descartadas o indeterminadas según las opciones disponibles. Documenta la razón de la evaluación.
8. Abre el grafo desde el espacio de investigación y comprueba que puedes seguir los elementos hasta sus evidencias de origen.

Usa únicamente datos públicos y trata los resultados como hipótesis de investigación. Una coincidencia de nombre, alias o indicador no basta para atribuir una identidad.

## Pruebas automatizadas

Desde la raíz del proyecto:

```bash
docker compose run --rm api pytest -q
```

El resultado depende de la versión del código, la configuración y el entorno. No se afirma que toda la suite pase en el estado actual: ejecuta las pruebas antes de aceptar cambios o desplegar y revisa cada fallo. Las pruebas que simulan respuestas HTTP verifican lógica de forma controlada; no sustituyen una prueba de extremo a extremo contra servicios reales.

## Seguridad y uso responsable

- Configura un secreto fuerte y único en `.env`; no lo subas al repositorio.
- No expongas una instancia de desarrollo directamente a Internet.
- Haz copias de seguridad antes de migrar o modificar la base de datos.
- Conserva la procedencia de la evidencia y documenta las decisiones del investigador.
- Limita la recolección a información pública y a usos legales y autorizados.
- Antes de producción, revisa la autenticación, la gestión de sesiones, la limitación de intentos, la configuración de red, los secretos, los permisos y la política de retención de datos.

## Próximas líneas de trabajo

Entre las áreas pendientes se encuentran ampliar y evaluar las fuentes de datos, mejorar la edición persistente del grafo, facilitar la revisión de evidencias y correlaciones, completar las pruebas de autorización y de interfaz, reforzar la instalación en distintos sistemas y validar formalmente el método y el comportamiento de la plataforma.

Estas líneas describen trabajo futuro, no funcionalidades que deban considerarse ya implementadas.

## Licencia

Consulta el repositorio para conocer el estado de la licencia. Este README no concede por sí mismo derechos de redistribución o uso adicionales.

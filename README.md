# PAPIRO

**PAPIRO es una plataforma OSINT en desarrollo para investigar personas a partir de información disponible públicamente.** Su objetivo a largo plazo es automatizar la mayor parte posible del proceso: recopilar información de múltiples fuentes, descubrir y correlacionar indicadores, resolver identidades candidatas y ampliar las investigaciones de forma iterativa a medida que aparecen nuevos datos, incluso al trabajar con grandes volúmenes de información.

Este es el objetivo de evolución, no el nivel de automatización que ofrece la versión actual. PAPIRO cuenta hoy con una base funcional inicial para ejecutar búsquedas acotadas, organizar hallazgos y examinar correlaciones. Todavía queda un trabajo considerable para alcanzar una investigación automatizada, iterativa y escalable.

- [English](README.en.md) · [Русский](README.ru.md)

## Funcionalidades actuales

- Crear investigaciones y lanzar manualmente búsquedas por nombre.
- Consultar las fuentes implementadas: **GitHub y Wikidata**.
- Revisar hallazgos junto con sus URL, procedencia e indicadores.
- Detectar correlaciones mediante coincidencias exactas entre indicadores normalizados.
- Crear perfiles candidatos, asociar hallazgos y explorar relaciones en un grafo.
- Gestionar el acceso mediante cuentas autenticadas.

## Limitaciones actuales y prioridades de desarrollo

- La cobertura de fuentes es reducida y las búsquedas deben iniciarse manualmente.
- La correlación se basa en reglas deterministas y coincidencias exactas; todavía no constituye un mecanismo completo de resolución de identidades.
- La expansión iterativa de las búsquedas a partir de nuevos hallazgos y el análisis a gran escala están pendientes.
- La edición y eliminación persistente de elementos del grafo necesitan mejoras.
- La interfaz requiere mejoras de usabilidad para facilitar la revisión de hallazgos y la gestión de perfiles y relaciones.
- La plataforma no utiliza IA/ML y necesita más pruebas y validación formal.
- Es necesario seguir reduciendo estas limitaciones, refactorizar el código donde corresponda y reforzar la seguridad.

**PAPIRO no está preparada para producción.** No la expongas a redes no confiables sin una revisión de seguridad.

## Tipos de usuario

- **Investigador:** puede realizar investigaciones privadas o trabajar en investigaciones vinculadas a una entidad a la que pertenezca.
- **Entidad:** puede administrar a varios investigadores.

## Instalación

Requisitos: Git, Docker y Docker Compose.

```bash
git clone https://github.com/Starv1ng/Kami-no-Eye.git
cd Kami-no-Eye
cp .env.example .env
```

En Windows PowerShell, usa `Copy-Item .env.example .env` en lugar del último comando.

Edita `.env` y sustituye `AUTH_SECRET_KEY` por un secreto aleatorio propio de al menos 32 caracteres. Puedes generarlo con:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Inicia los servicios:

```bash
docker compose up --build -d
docker compose ps
```

- Interfaz web: http://127.0.0.1:8000/ui
- Documentación de la API: http://127.0.0.1:8000/docs

La configuración actual utiliza `network_mode: host`; en algunos sistemas o configuraciones de Docker Desktop puede requerir ajustes de red.

## Primer uso

1. Abre la interfaz y crea una cuenta **Investigator**. La contraseña debe tener al menos 12 caracteres.
2. Inicia sesión y crea una investigación.
3. Ejecuta manualmente una búsqueda por nombre.
4. Revisa los hallazgos, sus fuentes, los indicadores y las correlaciones.
5. Si resulta útil, organiza los hallazgos en perfiles candidatos y explora las relaciones del grafo.

Para crear una cuenta de superusuario, ejecuta el comando **antes de registrar cualquier otra cuenta**:

```bash
docker compose exec -it api python -m scripts.bootstrap_superuser
```

El script solicita el correo y la contraseña dos veces y exige una contraseña de al menos 12 caracteres. Solo funciona si todavía no existe ninguna cuenta.

## Pruebas

```bash
docker compose run --rm api pytest -q
```

Ejecuta las pruebas en tu entorno; no se garantiza que todas pasen en cada versión.

## Uso responsable y protección de datos

Investiga únicamente con una base legal y respeta la privacidad y las condiciones de las fuentes. Conserva la procedencia de la información y verifica los resultados: una coincidencia, un perfil candidato o una relación del grafo no constituyen por sí solos una identificación confirmada.

Si utilizas una base de datos de una versión anterior, haz una copia de seguridad y revisa el esquema y las instrucciones de migración antes de aplicar cambios. No elimines el volumen Docker `pgdata`.

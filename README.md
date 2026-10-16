# PAPIRO

PAPIRO es un prototipo OSINT para reunir información pública, revisar coincidencias y organizar hallazgos en perfiles candidatos y un grafo de investigación. **Las coincidencias son pistas, no una confirmación de identidad.**

- [English](README.en.md) · [Русский](README.ru.md)

## Qué está implementado

- Interfaz web y API con autenticación y roles.
- Búsqueda por nombre en **GitHub y Wikidata**.
- Hallazgos con fuente y URL, e indicadores extraídos de los datos públicos.
- Correlación determinista por coincidencias exactas entre indicadores normalizados.
- Creación de perfiles candidatos, asociación de hallazgos y relaciones.
- Espacio de investigación para revisar evidencias y explorar el grafo.

## Instalación

Requisitos: Git, Docker y Docker Compose. La configuración de Docker usa `network_mode: host`; en Docker Desktop o sistemas distintos puede necesitar ajustes de red.

```bash
git clone https://github.com/Starv1ng/Kami-no-Eye.git
cd Kami-no-Eye
git switch main
cp .env.example .env
```

Edita `.env` y sustituye `AUTH_SECRET_KEY` por un secreto aleatorio propio de al menos 32 caracteres. Puedes generarlo con:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Después inicia los servicios:

```bash
docker compose up --build -d
docker compose ps
```

Abre la aplicación en [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui). La API está documentada en [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

**Base de datos:** antes de usar una instalación nueva con todas las funciones de identidad y roles, revisa y aplica las migraciones de `migrations/` (002, 003, 004, 006 y 007, en ese orden; la 004 se aplica con `docker compose exec api python -m scripts.apply_identity_migration`). Haz copia de seguridad antes de migrar una base existente. No borres el volumen `pgdata`.

Tras aplicar la migración 004, crea el primer administrador:

```bash
docker compose exec -it api python -m scripts.bootstrap_superuser
```

El asistente solicita correo y contraseña (mínimo 12 caracteres). Solo funciona si aún no existe ninguna cuenta.

## Cómo probarlo

1. Inicia sesión en la interfaz.
2. Crea una investigación.
3. **Ejecuta manualmente** una búsqueda por nombre; crear una investigación no inicia la búsqueda.
4. Revisa hallazgos, fuentes, indicadores y correlaciones.
5. Crea perfiles candidatos, asocia evidencias y examina las relaciones en el grafo.
6. Evalúa las coincidencias con criterio: no prueban por sí solas que sea la misma persona.

Para ejecutar las pruebas automatizadas:

```bash
docker compose run --rm api pytest -q
```

## Líneas futuras

- Búsqueda iterativa que aproveche nuevos indicadores.
- Más fuentes y mejor cobertura.
- Edición y persistencia más completas del grafo.
- Pruebas adicionales de interfaz, autorización e instalación.
- Validación formal del método y evaluación de la plataforma.

PAPIRO sigue en desarrollo: no incorpora IA/ML y no está listo para producción. Usa solo datos públicos y de forma legal. Revisa la configuración de seguridad antes de exponer la aplicación a otras redes.

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
- La plataforma no utiliza IA/ML y necesita más pruebas y validación formal.
- Es prioritario reducir estas limitaciones, refactorizar el código y reforzar la seguridad.

## Instalación

Requisitos: Git, Docker y Docker Compose.

```bash
git clone https://github.com/Starv1ng/PAPIRO.git PAPIRO
cd PAPIRO
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
5. Organiza los hallazgos en perfiles candidatos y explora las relaciones del grafo cuando resulte necesario.

## Tipos de usuario

- **Investigador:** puede realizar investigaciones privadas o investigaciones para una entidad a la que pertenezca.
- **Entidad:** puede administrar a varios investigadores.

usuarios de prueba: prueba0@kami.com; prueba1@kami.com; entidad1@kami.com; entidad2@kami.com <--contraseñas:123456789012 | admin: kami@kami.com  <--contraseña:Kami12345678

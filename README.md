# PAPIRO

PAPIRO es un prototipo OSINT para reunir información pública, revisar coincidencias y organizar hallazgos en perfiles candidatos y un grafo de investigación. **Una coincidencia es una pista; no confirma por sí sola la identidad.**

- [English](README.en.md) · [Русский](README.ru.md)

## Qué puedes hacer ahora

- Crear investigaciones y lanzar búsquedas por nombre.
- Consultar las fuentes configuradas: **GitHub y Wikidata**.
- Revisar hallazgos con sus fuentes, URL e indicadores.
- Examinar correlaciones deterministas basadas en coincidencias exactas de indicadores normalizados.
- Crear perfiles candidatos, asociar evidencias y explorar relaciones en el grafo.
- Usar cuentas de investigador con autenticación.

## Instalación rápida

Necesitas Git, Docker y Docker Compose. Clona el repositorio:

```bash
git clone https://github.com/Starv1ng/Kami-no-Eye.git
cd Kami-no-Eye
cp .env.example .env
```

En Windows PowerShell, sustituye el último comando por `Copy-Item .env.example .env`.

Edita `.env` y cambia `AUTH_SECRET_KEY` por un secreto aleatorio de al menos 32 caracteres. Puedes generarlo con:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Inicia la aplicación:

```bash
docker compose up --build -d
docker compose ps
```

Abre [la interfaz](http://127.0.0.1:8000/ui). La [documentación de la API](http://127.0.0.1:8000/docs) está disponible para consultas técnicas.

**¿Hay que ejecutar migraciones?**
- **Clonación nueva con una base de datos vacía:** no. Al arrancar, la aplicación crea las tablas del modelo actual.
- **Una base de datos existente de una versión anterior:** puede necesitar migraciones. Haz primero una copia de seguridad y revisa las instrucciones y el esquema antes de aplicar scripts de `migrations/`. No borres el volumen `pgdata`.

La configuración Docker actual usa `network_mode: host`; según el sistema operativo o la versión de Docker Desktop puede requerir ajustes de red.

## Cómo usarlo

1. Abre la interfaz y selecciona **Create account** para registrar una cuenta de tipo **Investigator**. La contraseña debe tener al menos 12 caracteres.
2. Inicia sesión y crea una investigación.
3. Lanza manualmente una búsqueda por nombre; crear la investigación no inicia la búsqueda automáticamente.
4. Revisa los hallazgos, sus fuentes, los indicadores y las correlaciones.
5. Crea perfiles candidatos, asocia evidencias y explora las relaciones en el grafo.
6. Evalúa las coincidencias con cautela: no son prueba definitiva de identidad.

Si necesitas una cuenta de superusuario para tareas administrativas, créala **antes de registrar cualquier cuenta**:

```bash
docker compose exec -it api python -m scripts.bootstrap_superuser
```

El script solicita correo y contraseña dos veces, exige 12 caracteres como mínimo y solo funciona si aún no existe ninguna cuenta.

## Pruebas

```bash
docker compose run --rm api pytest -q
```

Ejecuta las pruebas en tu entorno; este README no presupone que todas pasen.

## Líneas futuras

- Búsqueda iterativa a partir de nuevos indicadores.
- Más fuentes y mayor cobertura.
- Edición y eliminación persistente más completas del grafo.
- Más pruebas de interfaz, autorización e instalación.
- Validación formal del método y evaluación de la plataforma.

PAPIRO sigue en desarrollo; no utiliza IA/ML ni está listo para producción. Usa información pública de forma legal y revisa la seguridad antes de exponer la instancia a otras redes.

# PAPIRO

**PAPIRO es una plataforma OSINT en desarrollo para investigar personas a partir de información disponible públicamente.** Reúne hallazgos de distintas fuentes, organiza indicadores, muestra posibles coincidencias y permite construir perfiles candidatos y explorar sus relaciones en un grafo.

El objetivo es ayudar al investigador a organizar y analizar pistas; no determinar automáticamente la identidad de una persona ni sustituir la verificación humana.

- [English](README.en.md) · [Русский](README.ru.md)

## Funcionalidades actuales

- Crear investigaciones y lanzar búsquedas por nombre.
- Consultar las fuentes implementadas: **GitHub y Wikidata**.
- Revisar los resultados junto con sus URL, procedencia e indicadores.
- Detectar correlaciones mediante coincidencias exactas entre indicadores normalizados.
- Crear perfiles candidatos, asociar hallazgos y explorar relaciones en un grafo.
- Acceder mediante cuentas autenticadas de investigador.

## Limitaciones conocidas

- La cobertura de fuentes es reducida y las búsquedas por nombre se inician manualmente.
- La correlación es determinista: una coincidencia de indicadores genera una pista, no una identificación confirmada.
- La búsqueda iterativa a partir de nuevos hallazgos y la cobertura ampliada de fuentes siguen pendientes.
- La edición y eliminación persistente de elementos del grafo aún necesitan mejoras.
- La plataforma no utiliza IA/ML y todavía requiere más pruebas y validación formal.
- **No está preparada para producción** ni debe exponerse a redes no confiables sin una revisión de seguridad.

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

## Uso responsable

Investiga únicamente con una base legal y respeta la privacidad y las condiciones de las fuentes. Verifica cada hallazgo con su contexto y procedencia. **No trates una coincidencia, un perfil candidato ni una relación del grafo como prueba definitiva de identidad.**

Si utilizas una base de datos existente de una versión anterior, haz una copia de seguridad y revisa el esquema y las instrucciones de migración antes de aplicar cambios. No elimines el volumen Docker `pgdata`.

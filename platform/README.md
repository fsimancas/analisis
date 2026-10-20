# FAIS Platform

Plataforma web ligera para inteligencia deportiva, construida sobre los datos
históricos de este repositorio sin modificar los scrapers originales.

## Arquitectura

- `backend/`: FastAPI, REST, GraphQL, WebSocket, SQLite y workers.
- `web/`: React, Vite, TypeScript, Tailwind y Apache ECharts.
- `scripts/`: comandos de desarrollo y despliegue nativo.
- `deploy/systemd/`: unidades de ejemplo sin contenedores.

SQLite es la fuente transaccional y tiene un único escritor. Redis/Celery
distribuye trabajos; ClickHouse queda reservado para series temporales de alto
volumen. Ningún proceso debe abrir SQLite a través de NFS.

## Estado de las fases

- Fase 1: modelo canónico SQLite, migraciones y migración idempotente del legado.
- Fase 2: API FastAPI con REST, GraphQL y WebSocket.
- Fase 3: trabajos Celery, Redis Streams, escritor único y outbox durable.
- Fase 4: features temporales sin fuga, Poisson regularizado, mercados y registro de modelos.
- Fase 5: terminal React/Vite/TypeScript/Tailwind/ECharts responsive.
- Fase 6: pruebas, scripts y despliegue nativo con systemd/Caddy.
- Fase 7: normalización temporal con precisión, zona horaria y temporadas trazables.
- Fase 8: adaptador incremental para los JSON producidos por los scrapers.
- Fase 9: backtesting walk-forward persistido y calibración medible.
- Fase 10: exploradores de partidos/equipos, fichas, modelos y calidad.
- Fase 11: usuarios, Argon2, JWT, roles, favoritos y alertas.
- Fase 12: métricas, readiness, backups verificados y smoke test restaurable.
- Fase 13: consola ADMIN con CRUD, cargas, jobs, calidad, usuarios, canales y auditoría.
- Fase 14: permisos por competición, guards por rol y WebSocket autenticado.
- Fase 15: workspace ANALYST, Monte Carlo reproducible y análisis de cuotas/EV.
- Fase 16: proveedores controlados y dominio de jugadores, árbitros, alineaciones y eventos.

Consulta [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para decisiones, límites y evolución.

## Inicio rápido

```bash
cd /workspace/analisis/platform
./scripts/dev-backend.sh
```

En otra terminal:

```bash
cd /workspace/analisis/platform/web
npm ci
npm run dev
```

Para cargar el histórico original una sola vez (las ejecuciones posteriores son
idempotentes):

```bash
cd /workspace/analisis/platform
./scripts/import-legacy.sh ../betplay_flashscore_lite.db
```

Servicios disponibles:

- OpenAPI: `http://127.0.0.1:8000/docs`
- GraphQL: `http://127.0.0.1:8000/graphql`
- REST: `http://127.0.0.1:8000/api/v1`
- Frontend: `http://127.0.0.1:5173`
- Administración: `http://127.0.0.1:5173/admin` (requiere rol `ADMIN`)
- Mesa del analista: `http://127.0.0.1:5173/analyst` (rol `ANALYST` o `ADMIN`)
- Cuotas y valor: `http://127.0.0.1:5173/odds` (respeta permisos por competición)

Redis es necesario para la cola distribuida y WebSocket, pero no para lecturas
REST/GraphQL ni para migrar/importar datos. Si Redis cae, los eventos quedan en
el outbox SQLite y se publican al recuperarse.

En producción, los scrapers depositan sus JSON de forma atómica en
`FAIS_INBOX_PATH/<país>/<competición>/*.json`; Celery Beat detecta únicamente
archivos nuevos o modificados por SHA-256. Selenium no se ejecuta dentro de la API.

La base local generada queda en `data/fais.sqlite3`. Para reconstruirla y crear
predicciones iniciales:

```bash
./scripts/import-legacy.sh ../betplay_flashscore_lite.db
.venv/bin/fais backtest --min-team-history 3
.venv/bin/fais predict-upcoming --from-date 2026-10-18 --limit 25
```

Para integrar una salida JSON nueva de un scraper:

```bash
.venv/bin/fais ingest-json snapshot.json \
  --country colombia --competition primera-a --captured-on 2026-10-18
```

También se puede dejar el archivo en la bandeja y comprobarla manualmente:

```bash
.venv/bin/fais scan-inbox
```

Para entrenar el challenger ligero de CPU y promoverlo solo si supera el
holdout temporal de Poisson:

```bash
pip install -e './backend[ml]'
.venv/bin/fais train-xgboost --promote-if-better
```

PyTorch vive en el extra opcional `./backend[deep-learning]` y no forma parte
del runtime normal. Esto mantiene pequeña la instalación y deja preparada la
extensión neuronal cuando exista una ganancia medible.

## Principios

1. No se inventan fechas, equipos ni estadísticas faltantes.
2. Toda predicción tiene `cutoff`, versión de modelo y entrada reproducible.
3. Los modelos usan exclusivamente información anterior al partido objetivo.
4. REST ejecuta comandos; GraphQL compone lecturas; WebSocket distribuye eventos.
5. Los scrapers publican resultados, pero no conocen el esquema de la interfaz.
6. Una fecha con día pero sin hora nunca se convierte artificialmente en una hora exacta.
7. Contraseñas Argon2 y recursos personales siempre quedan aislados por usuario.
8. `USER` solo consulta competiciones asignadas; `ANALYST` y `ADMIN` tienen alcance global.
9. Los adaptadores de proveedores solo leen JSON validado dentro de `FAIS_INBOX_PATH`.

## Verificación

```bash
cd backend
../.venv/bin/python -m pytest
../.venv/bin/ruff check src tests
cd ../web
npm run lint
npm run build
npm run test:e2e
```

También puede ejecutarse todo junto con `./scripts/verify.sh`. La guía de
producción y restauración está en [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Resultado del baseline

Evaluación cronológica real sobre 17.038 partidos con al menos tres antecedentes
por equipo: `accuracy=48,10%`, `log_loss=1,0299`, `Brier=0,6186` y
`ECE=1,98%`. Estos valores son la referencia mínima que deberá superar cualquier
modelo XGBoost o PyTorch antes de activarse.

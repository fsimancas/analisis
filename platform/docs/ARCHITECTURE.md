# Arquitectura de FAIS

## Objetivo

FAIS separa el código histórico de scraping de una plataforma profesional de
consulta, análisis e inferencia. La arquitectura es modular y distribuible,
pero conserva una instalación pequeña, nativa y sin contenedores ni PostgreSQL.

```text
Fuentes / legado -> Importador idempotente -> SQLite canónico (WAL)
                                                |
React/Vite <- REST + GraphQL <- FastAPI --------+
     ^                  |
     +---- WebSocket <- Redis Streams <- Celery writer/analytics
                                      ^
                                      +-- outbox durable SQLite
```

## Decisiones aplicadas

### Persistencia

SQLite es la fuente operacional. Usa `foreign_keys=ON`, WAL, `busy_timeout`,
transacciones `BEGIN IMMEDIATE`, migraciones versionadas y un worker escritor
con concurrencia 1. La base debe vivir en disco local, nunca NFS. Se conservan
el identificador externo, el registro crudo y un hash para trazabilidad.

ClickHouse no se activa con el volumen actual (46.918 partidos): añadirlo ahora
duplicaría operación sin una mejora medible. El límite de evolución es claro:
se incorpora como proyección analítica cuando eventos/cuotas superen millones
de filas; SQLite sigue siendo el catálogo operacional.

### Datos y calidad

El importador no interpreta fechas ambiguas. Conserva `kickoff_raw`, deja
`kickoff_utc` vacío y crea `AMBIGUOUS_KICKOFF`. Equipos y alias incluyen contexto
de país/proveedor para evitar colisiones. Todas las importaciones son
reentrantes mediante referencias externas y restricciones únicas.

### API

- REST: comandos, health, jobs y lecturas simples.
- GraphQL: composición de vistas de lectura.
- WebSocket: puente sobre Redis Streams para eventos en vivo.
- FastAPI genera OpenAPI y validación de parámetros automáticamente.

No hay una segunda lógica de negocio en cada protocolo: los tres consumen el
mismo repositorio y servicios de dominio.

La identidad local usa Argon2id para contraseñas y JWT HS256 con expiración.
Favoritos y alertas incluyen siempre `user_id` y las eliminaciones verifican la
propiedad. Para exposición pública a gran escala se recomienda OIDC y tokens en
cookies `HttpOnly` en lugar del almacenamiento local usado por el cliente actual.

### Procesamiento e IA

Celery distribuye trabajo y la cola `writer` serializa escrituras. El outbox
durable desacopla los commits de Redis. El baseline `poisson-v1` calcula forma
temporal regularizada, matriz de marcadores, 1X2, totales y ambos marcan. Cada
predicción guarda cutoff, feature version, model version, input hash y payload.

El registro de modelos acepta artefactos XGBoost/PyTorch en una fase de datos
maduros sin acoplarlos a la API. Un modelo no puede activarse hasta superar un
backtest walk-forward y calibración. Los LLM se limitan a explicación narrativa;
no alteran probabilidades ni datos fuente.

### Frontend

React + Vite evita el coste de un servidor Next.js porque el producto actual no
requiere SEO. TypeScript, Tailwind y componentes locales mantienen el bundle y
las dependencias controlados. ECharts usa Canvas e imports modulares. Konva,
Pixi o D3 solo deben añadirse para vistas tácticas que realmente los necesiten.

Las rutas incluyen dashboard, partidos, ficha predictiva, equipos, forma,
modelos/backtests, calidad y cuenta. El frontend no calcula probabilidades: solo
representa artefactos versionados producidos por el backend.

## Escalado sin cambiar de arquitectura

1. Varias réplicas FastAPI de solo lectura detrás de Caddy.
2. Un único worker `writer` sobre SQLite local.
3. Workers `compute` paralelos para cálculo que no escriba directamente.
4. Redis Streams para fan-out y reintentos.
5. ClickHouse como proyección para ticks/cuotas/eventos masivos.

Si en el futuro se necesitan varios nodos escribiendo simultáneamente la misma
base, SQLite deja de ser una elección válida. Ese requisito implicaría cambiar
la base transaccional; no debe simularse compartiendo el fichero por red.

## Seguridad de producción

Caddy termina TLS. El servicio debe ejecutarse con usuario dedicado, permisos
restrictivos sobre `/var/lib/fais`, firewall local y secretos en
`/etc/fais/fais.env`. Antes de exposición pública deben añadirse autenticación
OIDC, rate limiting en el gateway y copias SQLite mediante la backup API.

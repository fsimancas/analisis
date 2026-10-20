# Plataforma de análisis deportivo

Este documento describe las funciones entregadas en las fases de permisos,
workspace analítico, cuotas, simulación e información detallada de partidos.

## Roles y alcance

| Rol | Competiciones | Lectura deportiva | Simular/backtest | Administrar |
| --- | --- | --- | --- | --- |
| `USER` | Solo las asignadas | Sí | No | No |
| `ANALYST` | Todas | Sí | Sí | No |
| `ADMIN` | Todas | Sí | Sí | Sí |

Una cuenta `USER` sin asignaciones ve un catálogo vacío. La autorización se
vuelve a comprobar en el backend; ocultar un enlace en React no concede ni quita
permisos. REST, GraphQL y WebSocket aplican la misma identidad JWT.

## Flujo del analista

1. Abre `/analyst` y selecciona un partido.
2. Encola una predicción si todavía no existe una vigente.
3. Ejecuta Monte Carlo indicando número de iteraciones y semilla.
4. Compara 1X2, totales, ambos marcan y marcadores probables.
5. Abre `/odds` para comparar el modelo con las cuotas disponibles.
6. Guarda hipótesis, notas y resultado en un cuaderno personal.
7. Puede encolar un backtest walk-forward desde el mismo workspace.

Cada simulación queda en `analysis_runs` con usuario, partido, parámetros,
versión del modelo, semilla, estado, resultado o error. Esto hace reproducible
el análisis y evita presentar un número sin procedencia.

## Cuotas y valor esperado

`GET /api/v1/odds/matches/{id}` entrega snapshots y
`GET /api/v1/odds/matches/{id}/value` los cruza con la última predicción. Por
cada selección se devuelve cuota decimal, probabilidad implícita, margen total,
probabilidad implícita justa, probabilidad del modelo, edge y valor esperado.

El valor esperado positivo es una señal estadística, no una garantía. El
frontend ordena las selecciones por EV y conserva proveedor, mercado, línea y
momento de captura para que la comparación sea verificable.

## Partido, jugadores y árbitros

La ficha de partido agrega:

- local y visitante con sus plantillas activas;
- alineaciones probables, confirmadas y finales con formación;
- árbitro principal, asistentes y VAR;
- línea temporal de goles, tarjetas, sustituciones y VAR;
- estadísticas por equipo y periodo;
- predicción, simulaciones y cuotas por mercado.

Los perfiles de jugador muestran país, posición, fecha de nacimiento, equipos y
estadísticas agregadas. El perfil arbitral muestra categoría, partidos y
disciplina. Para un `USER`, estos agregados se limitan a sus competiciones.

## Administración de fuentes

En `/admin`, sección **ingestas**, se registra una fuente con proveedor, tipo,
país y competición. Después se puede cargar un JSON. El archivo debe quedar
dentro de `FAIS_INBOX_PATH`, tener extensión `.json`, corresponder a una fuente
habilitada y pasar la validación del adaptador. Los jobs y errores se supervisan
desde la misma consola y toda carga queda auditada.

La API no lanza navegadores ni ejecuta código de terceros. Los scrapers externos
producen snapshots; el worker es el único componente que los traduce al modelo
canónico SQLite.

## Endpoints principales

- `/api/v1/admin/users/{id}/competition-permissions`
- `/api/v1/analyst/workspace/matches`
- `/api/v1/analyst/workspace/montecarlo/{match_id}`
- `/api/v1/analyst/workspace/runs`
- `/api/v1/analyst/workbooks`
- `/api/v1/odds/matches/{match_id}/value`
- `/api/v1/matches/{match_id}/details`
- `/api/v1/matches/{match_id}/lineups`
- `/api/v1/teams/{team_id}/squad`
- `/api/v1/players/{player_id}`
- `/api/v1/referees/{referee_id}`
- `/api/v1/admin/uploads/provider`

## Pruebas

Las suites validan migraciones, aislamiento por competición, guards de rol,
favoritos/alertas, GraphQL, simulación reproducible, EV, idempotencia de cuotas,
restricción de la bandeja, detalles deportivos y guardado de alineaciones. La
verificación completa sigue siendo `./scripts/verify.sh`.

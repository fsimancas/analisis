# FAIS — Sistema Analítico desde Cero
## Especificación funcional y técnica del motor analítico

**Versión:** 1.0  
**Alcance:** exclusivamente el sistema analítico de FAIS: datos históricos, estado temporal de equipos, features, modelos probabilísticos, predicciones, evaluación y validación estadística.  
**Fuera de alcance:** frontend, panel administrativo, autenticación, comercialización, pagos, suscripciones, marketing y diseño visual del producto.

---

# 1. Objetivo

Construir desde cero un motor de inteligencia deportiva para fútbol que estime probabilidades pre-partido y produzca resultados reproducibles y auditables.

El sistema debe:
1. ingerir datos históricos;
2. validar integridad y calidad;
3. normalizar fuentes a un modelo canónico;
4. reconstruir el historial disponible antes de cada partido;
5. generar features pre-match sin leakage;
6. estimar goles esperados local/visitante;
7. producir una distribución probabilística del marcador;
8. derivar probabilidades de mercados desde esa distribución;
9. evaluar predicciones fuera de muestra;
10. comparar modelos con protocolos temporales;
11. registrar versiones, parámetros y evidencia;
12. promover un Champion solo tras superar gates estadísticos.

**Principio rector:** primero corrección temporal y estadística; después complejidad.

---

# 2. Alcance

## Incluido
- ingesta analítica de JSON histórico;
- contratos de datos;
- canonicalización;
- validación y diagnóstico de calidad;
- construcción temporal de datasets;
- generación y versionado de features;
- estimación de parámetros de goles;
- modelos de goles y de resultado;
- calibración;
- evaluación walk-forward;
- backtesting;
- análisis de errores;
- reproducibilidad de predicciones;
- registro Champion/Challenger;
- reportes de experimentos.

## Excluido
- interfaz de usuario;
- administración comercial;
- autenticación;
- pagos;
- aplicación móvil;
- scraping en vivo como requisito inicial;
- apuestas automáticas;
- promesas de ganancias;
- modelos generativos que decidan directamente las probabilidades.

---

# 3. Restricciones técnicas

Equipo objetivo: Windows 10, laptop con 8 GB RAM y sin GPU obligatoria.

Stack inicial:
- Python 3.12;
- NumPy;
- pandas o Polars, seleccionado por benchmark;
- SciPy;
- scikit-learn;
- Pydantic;
- pytest;
- JSON/Parquet para archivos procesados;
- PostgreSQL opcional para integrar posteriormente el motor en el producto.

El motor debe ejecutarse por CLI en CPU. Deep learning y GPU no son requisitos de la primera versión.

---

# 4. Arquitectura analítica

```text
RAW MATCH DATA
      |
      v
INGESTION + SOURCE VALIDATION
      |
      v
CANONICAL MATCH MODEL
      |
      v
DATA QUALITY & COVERAGE
      |
      v
TEMPORAL MATCH HISTORY
      |
      v
PRE-MATCH TEAM STATE
      |
      v
FEATURE REGISTRY + FEATURE BUILDER
      |
      v
MODEL TRAINING / PARAMETER ESTIMATION
      |
      v
GOAL DISTRIBUTION
      |
      v
SCORELINE DISTRIBUTION
      |
      v
DERIVED MARKET PROBABILITIES
      |
      v
CALIBRATION + WALK-FORWARD EVALUATION
      |
      v
EXPERIMENT LEDGER + MODEL REGISTRY
```

Cada bloque debe tener contratos explícitos y pruebas independientes.

---

# 5. Contrato de entrada y modelo canónico

La fuente inicial es un conjunto JSON generado por el extractor ESPN. El formato observado contiene:
- `id`;
- `temporada`;
- `name`;
- `date`;
- `competitors`;
- `statistics`;
- `rosters`.

No asumir que todos los archivos tienen la misma estructura ni que todas las temporadas están completas.

## Reglas de interpretación
- El ID externo se trata como string.
- `date` se convierte a timestamp con zona horaria.
- `temporada` se valida contra el calendario, no se acepta ciegamente.
- `competitors` debe identificar exactamente local y visitante.
- `statistics` puede variar según endpoint/temporada.
- `rosters` y estadísticas de jugador pueden faltar.
- Los campos ausentes no se convierten automáticamente en cero.
- Estadísticas post-partido están prohibidas como inputs del mismo partido.
- Los goles deben derivarse mediante una regla verificable de eventos/estadísticas de jugadores, con manejo explícito de autogoles, goles anulados y discrepancias. Si no se puede resolver el marcador con seguridad, el partido queda en cuarentena analítica.

## Modelo canónico mínimo

### Match
- `match_id`;
- `provider`;
- `provider_match_id`;
- `competition`;
- `season_id`;
- `kickoff_at`;
- `home_team_id`;
- `away_team_id`;
- `status`;
- `home_goals`;
- `away_goals`;
- `result_1x2`;
- `source_record_hash`.

### TeamMatchStats
- `match_id`;
- `team_id`;
- `home_away`;
- `stat_name`;
- `stat_value`;
- `availability_status`;
- `source_path`.

### PlayerMatchStats
- `match_id`;
- `team_id`;
- `player_id`;
- `minutes_played`;
- `starter`;
- `stats`;
- `source_path`.

### DataQualityIssue
- `issue_id`;
- `match_id`;
- `rule_id`;
- `severity`;
- `details`;
- `status`.

El modelo canónico no debe depender de ESPN fuera del adaptador de ingesta.

---

# 6. Data Quality y cobertura

La calidad de datos es un gate, no un multiplicador arbitrario de probabilidades.

## Validaciones por partido
- ID no vacío;
- fecha válida;
- exactamente dos equipos;
- un local y un visitante;
- equipos diferentes;
- resultado consistente;
- estadísticas numéricas parseables;
- duplicados detectados;
- alineaciones opcionales correctamente marcadas;
- missing diferenciado de cero;
- hash del registro raw;
- temporada consistente con fechas.

## Validaciones por temporada
- partidos esperados frente a observados;
- IDs duplicados;
- fechas duplicadas sospechosas;
- equipos participantes;
- jornadas incompletas;
- huecos temporales;
- proporción de resultados no recuperables;
- cobertura de estadísticas por campo;
- cambios de esquema entre temporadas.

No asumir que una temporada tiene 380 partidos sin comprobarlo. Una temporada incompleta se marca como tal, no se completa con datos fabricados.

## Severidades
- `PASS`;
- `WARNING`;
- `FAIL`;
- `QUARANTINED`.

Los fallos que afecten identidad, resultado, temporalidad o integridad bloquean el uso del partido en entrenamiento/evaluación.

---

# 7. Orden temporal y anti-leakage

## Regla fundamental
Para predecir un partido \(m\) que comienza en tiempo \(t_m\), solo se puede usar información disponible antes de \(t_m\).

\[
H_m = \{j : kickoff_j < kickoff_m\}
\]

Los partidos con el mismo kickoff requieren una política conservadora: uno no alimenta al otro si no existe evidencia fiable del orden de disponibilidad.

## Prohibiciones
No usar como feature del propio partido:
- goles finales;
- resultado 1X2;
- posesión del partido;
- tiros del partido;
- tarjetas del partido;
- estadísticas de jugador del partido;
- alineación real si solo se conoció después del instante de predicción;
- datos posteriores al instante objetivo.

## Tests obligatorios
1. Cambiar estadísticas post-match del partido objetivo no puede alterar su predicción.
2. Añadir un partido futuro no puede cambiar features ni predicciones pasadas.
3. Recalcular el historial hasta \(t_m\) debe producir el mismo estado.
4. Cada feature declara fuente, lag, ventana y política de missing.
5. Un test falla si una feature post-match entra en el dataset pre-match.

---

# 8. Estado temporal de los equipos

Antes de probar modelos complejos, construir un estado pre-match reproducible por equipo.

## Estado inicial
- partidos previos;
- goles a favor/en contra;
- goles a favor/en contra por partido;
- goles en casa/fuera;
- puntos previos;
- forma reciente;
- descanso desde el último partido;
- incertidumbre por tamaño de muestra.

## Forma reciente
Se puede probar ponderación exponencial:

\[
w_k = \exp(-\xi \Delta t_k)
\]

Los parámetros se seleccionan dentro del entrenamiento, nunca mirando el test.

## Shrinkage
Al inicio de temporada, regularizar estimadores de equipo hacia una media de liga o prior explícito. No tratar tres partidos como una estimación estable. Los parámetros de shrinkage se estiman en entrenamiento o se fijan antes de evaluar.

## Equipos nuevos y cambios de división
- No reutilizar parámetros por coincidencia de nombre.
- Mantener IDs canónicos y aliases.
- Para un equipo sin historial comparable, usar prior documentado y mayor incertidumbre.
- Evaluar por separado equipos con historial y cold-start.
- No asumir transferencia automática de parámetros entre temporadas.

---

# 9. Feature Registry

Cada feature declara:

```text
feature_id
name
entity_level
dtype
definition
source
temporal_window
lag
missing_policy
available_at
role
version
```

Roles mínimos:
- `IDENTITY`;
- `TEMPORAL`;
- `PRE_MATCH`;
- `TARGET`;
- `POST_MATCH`;
- `FORBIDDEN`.

Solo `PRE_MATCH` y variables contextuales válidas pueden llegar al predictor.

## Features iniciales

### Equipo
- promedio histórico de goles a favor;
- promedio histórico de goles en contra;
- promedios local/visitante;
- forma reciente de goles;
- diferencia entre ataque propio y defensa rival;
- número de partidos disponibles;
- incertidumbre de estimación.

### Partido
- ventaja de localía;
- descanso entre partidos;
- diferencia de experiencia histórica disponible;
- fase de temporada calculada sin información futura.

### No incluir inicialmente
- métricas post-match;
- alineaciones futuras;
- ratings externos sin procedencia;
- features calculadas con toda la temporada antes de evaluar partidos tempranos.

---

# 10. Baselines obligatorios

Todos deben evaluarse sobre exactamente los mismos folds.

## Baseline A — Frecuencias
Probabilidades de clase estimadas únicamente con datos anteriores. La variante uniforme es referencia técnica, no benchmark competitivo suficiente.

## Baseline B — Majority
Clase más frecuente del entrenamiento, con tratamiento probabilístico explícito y smoothing si corresponde.

## Baseline C — PoissonGoals
Tasas de gol local/visitante estimadas con historial disponible y convertidas a probabilidades 1X2.

## Baseline D — League-rate Poisson
Tasas generales de liga y localía estimadas solo con el entrenamiento. Ayuda a detectar si la fuerza específica de equipos aporta valor.

Cada baseline comparte partidos OOS, timestamps, reglas de disponibilidad, cálculo de métricas y tratamiento de exclusiones.

---

# 11. Motor de goles inicial

## Poisson ataque-defensa

\[
\log(\lambda_H) = \mu + h + a_H - d_A
\]

\[
\log(\lambda_A) = \mu + a_A - d_H
\]

Donde:
- \(\lambda_H\): goles esperados del local;
- \(\lambda_A\): goles esperados del visitante;
- \(\mu\): nivel general de goles;
- \(h\): ventaja de localía;
- \(a_i\): fuerza ofensiva del equipo \(i\);
- \(d_i\): fuerza defensiva del equipo \(i\).

La convención de signos de defensa debe quedar fijada. La parametrización necesita restricciones de identificación, por ejemplo centrado de efectos de ataque y defensa.

## Distribución de goles

\[
P(G_H=x) = \frac{e^{-\lambda_H}\lambda_H^x}{x!}
\]

\[
P(G_A=y) = \frac{e^{-\lambda_A}\lambda_A^y}{y!}
\]

La independencia es una hipótesis de trabajo que debe evaluarse, no una verdad asumida.

## Distribución de marcadores

Construir \(P(G_H=x,G_A=y)\) con truncamiento suficiente y masa residual controlada.

Derivar 1X2 sumando celdas:
- local: \(x>y\);
- empate: \(x=y\);
- visitante: \(x<y\).

## Validaciones
- \(\lambda_H > 0\);
- \(\lambda_A > 0\);
- probabilidades finitas;
- probabilidades en [0,1];
- suma 1 de 1X2 dentro de tolerancia;
- matriz de marcadores normalizada;
- salida determinista con el mismo input y artefacto.

---

# 12. Modelos candidatos y orden experimental

No implementar todos a la vez. Cada candidato debe tener una hipótesis falsable.

1. **PoissonGoals:** tasas generales.
2. **Poisson ataque-defensa regularizado:** fortalezas de equipo con identificación y regularización.
3. **Estado temporal dinámico:** comprobar si ataque/defensa cambia con el tiempo, usando solo partidos previos.
4. **Negative Binomial:** solo si los diagnósticos muestran sobredispersión.
5. **Dixon-Coles:** solo si el error se concentra en marcadores bajos y hay justificación estadística.
6. **Corrección residual ML:** solo tras estabilizar el baseline; corrige residuos de una distribución base y no genera probabilidades inconexas.

Aplazar:
- Markov/live;
- hazard de eventos en directo;
- copulas;
- Monte Carlo complejo;
- fuzzy logic;
- disponibilidad de jugadores sin datos fiables;
- modelos profundos.

Estos componentes no son requisitos del MVP analítico pre-match.

---

# 13. Protocolo de evaluación

## Separación temporal
Usar expanding-window walk-forward, nunca split aleatorio:
1. entrenar con historial disponible;
2. predecir el siguiente bloque;
3. avanzar ventana;
4. repetir hasta cubrir el periodo OOS.

Features y parámetros se recalculan dentro de cada fold.

## Evitar selección en test
Seleccionar hiperparámetros en validación anterior al test final. El test final no selecciona features, modelos, ventanas ni calibradores.

## Métricas 1X2
- log-loss multiclase;
- Brier multiclase con convención documentada;
- accuracy;
- calibration/reliability;
- cobertura;
- métricas por temporada y fold.

No comparar Brier si su convención cambia.

## Métricas de goles
- log-likelihood de goles;
- MAE/RMSE de goles como diagnósticos;
- calibración de totales;
- cobertura de intervalos predictivos, si se producen.

## Incertidumbre
Reportar agregado, por fold, diferencia emparejada, intervalo de confianza o bootstrap apropiado, número de partidos, periodos excluidos y limitaciones de potencia.

Un p-value alto no demuestra equivalencia. No promover por una mejora puntual.

## Criterios de promoción
Un Challenger solo puede ser Champion si:
1. pasa tests temporales;
2. pasa todos los tests;
3. se evalúa en los mismos partidos que el Champion;
4. demuestra mejora OOS consistente y relevante;
5. no presenta degradación inaceptable por temporada/segmento;
6. es reproducible;
7. la decisión queda documentada.

Si la evidencia es insuficiente, se mantiene el Champion.

---

# 14. Calibración

La calibración es posterior a la predicción base y se entrena sin usar resultados del fold de test.

Candidatos:
- temperature scaling;
- calibración multinomial si hay muestra suficiente;
- calibración de probabilidades de goles cuando proceda.

Reglas:
- el calibrador forma parte de la versión del modelo;
- se ajusta solo en validación histórica disponible;
- se evalúa en un periodo posterior;
- no se aplica si no mejora calibración sin perjudicar el score probabilístico;
- se reportan métricas con cautela para muestras pequeñas.

---

# 15. Incertidumbre y cold-start

Registrar por predicción:
- partidos históricos disponibles;
- antigüedad del último dato;
- estado cold-start;
- cobertura de features;
- versión de parámetros;
- estado de calidad de datos.

No presentar intervalos o confianza numérica sin definición estadística reproducible.

---

# 16. Experiment Ledger y Model Registry

Cada experimento registra:

```text
experiment_id
created_at
hypothesis
dataset_version
feature_version
train_window
validation_window
test_window
model_version
hyperparameters
metrics_by_fold
pooled_metrics
uncertainty_analysis
data_quality_summary
decision
decision_reason
code_revision
```

Estados:
- `PROPOSED`;
- `RUNNING`;
- `PASSED`;
- `REJECTED`;
- `BLOCKED`;
- `DEFERRED`.

El Champion no cambia automáticamente. Toda promoción requiere decisión explícita y evidencia guardada.

---

# 17. Reproducibilidad de predicciones

Una predicción debe poder reconstruirse con:
- versión raw;
- hash del partido;
- versión canonical;
- cutoff temporal;
- snapshot del estado del equipo;
- versión del feature set;
- modelo y parámetros;
- calibrador;
- output final.

El comando futuro acepta un identificador de predicción y reconstruye el resultado sin usar datos posteriores. La reproducción compara el output reconstruido con el guardado dentro de tolerancias definidas.

---

# 18. Estructura sugerida del código analítico

```text
src/fais_analytics/
├── contracts/
│   ├── raw.py
│   ├── canonical.py
│   ├── features.py
│   └── predictions.py
├── ingestion/
│   ├── loader.py
│   └── espn_mapper.py
├── quality/
│   ├── match_checks.py
│   ├── season_checks.py
│   └── report.py
├── temporal/
│   ├── ordering.py
│   ├── history.py
│   └── team_state.py
├── features/
│   ├── registry.py
│   └── builder.py
├── models/
│   ├── interface.py
│   ├── league_poisson.py
│   ├── attack_defense_poisson.py
│   └── registry.py
├── probability/
│   ├── score_matrix.py
│   └── markets.py
├── evaluation/
│   ├── walk_forward.py
│   ├── metrics.py
│   ├── calibration.py
│   └── comparison.py
├── experiments/
│   ├── ledger.py
│   └── promotion.py
└── reproduce.py
```

Esta estructura es una propuesta inicial, no una obligación dogmática. Cambiarla requiere decisión documentada.

---

# 19. Plan de implementación por fases

## Fase A — Contratos y fixtures
- [ ] definir raw contract;
- [ ] definir canonical schema;
- [ ] preparar fixtures reales;
- [ ] documentar campos y missingness;
- [ ] testear mapper;
- [ ] congelar reglas de goles.

**Gate:** registros mapeados o puestos en cuarentena sin perder trazabilidad.

## Fase B — Calidad y cobertura
- [ ] duplicados;
- [ ] fechas;
- [ ] local/visitante;
- [ ] marcador;
- [ ] cobertura por temporada;
- [ ] cambios de esquema;
- [ ] reporte de problemas.

**Gate:** se conoce qué partidos se pueden usar y por qué.

## Fase C — Temporal engine
- [ ] orden temporal determinista;
- [ ] estado pre-match;
- [ ] historial acumulado;
- [ ] cortes temporales;
- [ ] tests anti-leakage.

**Gate:** los datos futuros no cambian features pasadas.

## Fase D — Feature platform
- [ ] registry;
- [ ] builder;
- [ ] missing policy;
- [ ] versionado;
- [ ] tests de determinismo y leakage.

**Gate:** cada feature tiene definición y linaje.

## Fase E — Baselines
- [ ] uniform;
- [ ] majority;
- [ ] league-rate Poisson;
- [ ] PoissonGoals;
- [ ] walk-forward;
- [ ] métricas por fold.

**Gate:** baselines reproducibles sobre los mismos partidos OOS.

## Fase F — Goal engine
- [ ] parametrización;
- [ ] identificación;
- [ ] regularización;
- [ ] score matrix;
- [ ] derivación 1X2;
- [ ] validación de masa probabilística.

**Gate:** outputs válidos y deterministas.

## Fase G — Experimentos
- [ ] hipótesis falsable;
- [ ] protocolo registrado;
- [ ] un candidato a la vez;
- [ ] análisis por fold/temporada;
- [ ] decisión documentada.

**Gate:** no se promueve sin evidencia OOS.

## Fase H — Calibración y evaluación final
- [ ] calibración en validación;
- [ ] test temporal final;
- [ ] incertidumbre;
- [ ] reporte final;
- [ ] registro Champion.

**Gate:** informe reproducible y limitaciones explícitas.

## Fase I — Reproducibilidad
- [ ] snapshots completos;
- [ ] comando reproduce;
- [ ] comparación de outputs;
- [ ] test end-to-end.

**Gate:** predicción histórica reconstruible.

---

# 20. Prompts para IA

## Prompt 1 — Planificador analítico

```text
Actúa como Lead Quantitative Engineer de FAIS.

Trabaja exclusivamente en el motor analítico, no en frontend, administración comercial ni autenticación.

Antes de proponer código:
1. lee este documento;
2. identifica la fase actual;
3. identifica contratos y dependencias;
4. divide el trabajo en tareas y subtareas;
5. define criterios de aceptación;
6. define tests;
7. enumera riesgos estadísticos.

No implementes fases futuras anticipadamente.
No inventes campos de datos.
No uses información futura.
No introduzcas modelos complejos sin hipótesis falsable.

Entrega un plan ejecutable para una sola fase y espera aprobación.
```

## Prompt 2 — Implementador

```text
Implementa únicamente la tarea aprobada de FAIS Analytics.

Antes de editar:
- inspecciona los módulos afectados;
- revisa contratos;
- identifica dependencias;
- confirma que no existe implementación equivalente.

Reglas:
- cambios mínimos;
- typing;
- funciones deterministas;
- tests unitarios;
- tests de integración cuando aplique;
- documentación actualizada;
- compatible con Windows 10 y 8 GB RAM.

No borres ni debilites tests.
No cambies métricas o datos de referencia para forzar aprobación.
Al finalizar, reporta archivos, comandos, resultados, limitaciones y gate.
```

## Prompt 3 — Reviewer independiente

```text
Actúa como reviewer independiente del motor analítico de FAIS.

No confíes en la explicación del implementador; inspecciona código y tests.

Busca:
- temporal leakage;
- estadísticas post-match;
- train/test contamination;
- identificación incorrecta de parámetros;
- probabilidades que no suman uno;
- métricas inconsistentes;
- comparación sobre distintos partidos;
- selección de hiperparámetros en test;
- equipos nuevos mal tratados;
- resultados no reproducibles;
- tests que no detectan errores reales.

Clasifica hallazgos por severidad.

Resultado:
PASS / PASS WITH WARNINGS / FAIL.

Toda aprobación debe citar evidencia del código, tests o logs.
```

## Prompt 4 — Investigador estadístico

```text
Formula una hipótesis estadística falsable para mejorar el modelo de goles.

Debes:
1. definir el mecanismo de fallo;
2. indicar el diagnóstico necesario;
3. establecer baseline y challenger;
4. usar los mismos folds temporales;
5. seleccionar parámetros sin mirar el test;
6. comparar métricas por fold y agregadas;
7. cuantificar incertidumbre;
8. definir el criterio de promoción antes del experimento.

No recomendar un modelo por popularidad o sofisticación.
Si la evidencia no basta, mantener el Champion.
```

---

# 21. Definition of Done

El sistema analítico está funcional cuando:
- [ ] carga datos raw;
- [ ] valida y clasifica registros;
- [ ] genera canonical reproducible;
- [ ] identifica cobertura y faltantes por temporada;
- [ ] construye historial pre-match;
- [ ] pasa tests anti-leakage;
- [ ] genera features versionadas;
- [ ] ejecuta baselines;
- [ ] produce probabilidades de marcador y 1X2 válidas;
- [ ] ejecuta walk-forward temporal;
- [ ] reporta métricas por fold y temporada;
- [ ] conserva experimentos;
- [ ] no promueve modelos automáticamente;
- [ ] reproduce predicciones históricas;
- [ ] funciona en CPU con 8 GB RAM;
- [ ] documenta límites y datos insuficientes.

---

# 22. Primera tarea

**FAIS-AN-001 — Data Contract & Source Audit**

Subtareas:
1. inspeccionar una muestra real de cada temporada;
2. identificar variaciones del JSON;
3. confirmar cómo se obtiene el marcador;
4. cuantificar registros incompletos y duplicados;
5. definir contrato raw;
6. definir canonical Match;
7. crear fixtures;
8. crear tests de mapping;
9. producir un reporte de cobertura.

**Gate:** no construir el motor estadístico hasta que la semántica del resultado, la identidad de equipos y la cobertura temporal estén verificadas.

---

# 23. Regla final

FAIS Analytics no busca el modelo más complejo. Busca la mejor distribución probabilística que demuestre utilidad fuera de muestra con datos disponibles en el momento de predicción y bajo un protocolo temporal reproducible.

Si una mejora no demuestra valor, se rechaza y se documenta.

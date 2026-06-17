# Auditoría por carpeta: propósito, estado, consolidación y riesgos

Este documento resume, por carpeta clave, el propósito funcional de cada componente, su estado actual, recomendaciones de consolidación/migración y los riesgos si no se reorganiza.

Fecha: 2025-09-18

## scripts/

| Archivo | Propósito funcional | Estado | Recomendación de consolidación o migración | Riesgos si no se reorganiza |
|---|---|---|---|---|
| ab_sesgo_fix.py | Harness A/B (Beta A–D), filtros institucionales, counters | Activo | Mantener como entry de experimentos; parametrizar vía YAML central | Deriva de parámetros; resultados no comparables entre runs |
| aplicar_modelo_costos.py | Aplicar costos/slippage a resultados | Activo | Integrar lógica en fase1_ext o en módulo de costos compartido | Inconsistencias de fees entre scripts |
| auditar_sesgo_operativo.py | Auditoría de sesgo operativo (sin ejecutar trades) | Activo | Integrar como preflight en runner institucional | Omitirlo reintroduce sesgos no controlados |
| audit_grid_survivors.py | Analiza “supervivientes” de grids | Activo | Unificar con `fase1_ext_consolidado.py` (módulo común de ranking) | Duplicación de criterios de ranking |
| checks_sanity.py | Chequeos rápidos de sanidad | Activo | Incluir en pipeline de QA previo a backtest | Falsos positivos en datos sin detectar |
| comparar_periodos.py | Comparativa entre periodos | Activo | Integrar en bloque de reporting consolidado | Métricas divergentes entre reportes |
| consolidar_costos.py | Consolidación de costos entre corridas | Activo | Fusionar con aplicar_modelo_costos.py en un único módulo | Discrepancias por orden de aplicación |
| drop_tests.py | Pruebas descartables/de desarrollo | Obsoleto | Archivar o eliminar | Confusión; ejecuciones accidentales |
| equity_drawdown_mes.py | Reporte mensual de drawdown | Activo | Integrar al reporte de portfolio consolidado | Reportería fragmentada/duplicada |
| expandir_maestro_15m.py | Expansión/reconstrucción de maestro 15m | Activo (solapado) | Unificar con `resample_y_reconstruir_maestro.py`/`reconstruir_maestro_30d.py` con flags | Maestros inconsistentes por script |
| fase1_ext_consolidado.py | Orquestación Fase 1_ext (A1–A4, B1–B6) | Activo | Mantener; extraer funciones a módulo reutilizable | Dificulta reutilización desde runner |
| fase1_visuals_and_ranking.py | Visuales y ranking Fase1 | Activo | Integrar visuales al consolidado (opcional) | Criterios de ranking duplicados |
| fase2_consolidado.py | Consolidación resultados Fase 2 | Activo | Mantener; exponer API para runner | Hardcoding de rutas/parámetros |
| fase2_por_simbolo.py | Fase 2 por símbolo (matrices TP/SL, MDs) | Activo | Mantener; escribir al YAML central | Matrices quedan “huérfanas” fuera del config |
| fase2_tp_sl_regimen.py | Optimiza TP/SL por régimen | Activo | Mantener; parametrizar desde YAML | Paridad difícil con entrypoint principal |
| gating_status.py | Estado de “gates”/guardrails | Activo | Integrar en veredicto y runner | Gates no aplicados consistentemente |
| generar_resumen_estado.py | Resumen de estado global | Activo | Fundir con reporting principal | Visión dispersa del estado |
| incorporar_simbolo.py | Incorporar símbolo nuevo | Activo | Integrar al pipeline de ingestión oficial | Altas manuales/heterogéneas |
| optimizar_parametros.py | Optimización genérica de parámetros | Obsoleto (reemplazado por Fase1_ext) | Deprecar o refactor a wrapper de Fase1_ext | Duplicación de lógica de búsqueda |
| portfolio_compare_tp_sl.py | Comparativa portfolio post TP/SL; veredicto | Activo | Mantener; ya genera commentary/veredicto | Si se separa del runner, puede quedar desincronizado |
| quick_backtest_check.py | Smoke 30d BTC/ETH | Activo (duplicado) | Mantener en scripts/ y eliminar duplicado en src/core/ | Desalineación de smokes/params |
| reconstruir_maestro_30d.py | Reconstruye maestro últimos 30d | Activo (solapado) | Unificar en único entry de maestro con flags | Diferencias en cobertura temporal |
| resample_y_reconstruir_maestro.py | Resampleo + reconstrucción | Activo (solapado) | Unificar con expandir_maestro_15m.py/reconstruir_maestro_30d.py | Maestros no comparables |
| run_backtest_15m.py | Entrada de backtest 15m | Activo | Mantener o delegar al runner institucional | Multiplicidad de entrypoints |
| run_beta_B_12m.ps1 | Runner PowerShell Beta B 12m | Activo | Sustituir por tareas VS Code/runner Python | Dependencia Windows y dispersión de flags |
| run_beta_variants.ps1 | Runner PS1 variantes Beta | Activo | Igual que arriba | Mantenimiento doble de parámetros |
| sincronizar_historicos_a_raw.py | Sincroniza históricos crudos | Activo | Integrar a pipeline (descarga/backup) | Desalineación entre raw y maestro |
| validate_maestro.py | Valida maestro | Activo (solapado) | Consolidar con `verificar_maestro_15m.py` | Doble fuente de verdad de QA |
| verificar_maestro_15m.py | QA maestro 15m (gaps/duplicados/calidad) | Activo | Mantener como gate formal | Saltos de calidad sin detección |
| walk_forward.py | Walk-forward | Activo/Legacy | Unificar con `walk_forward_refined.py` o deprecar | Resultados inconsistentes |
| walk_forward_refined.py | Walk-forward refinado | Activo | Mantener la variante única | Duplicación de pipelines de WF |
| _inspect_master_15m.py | Inspección ad-hoc | Obsoleto | Archivar/Eliminar | Ruido y uso accidental |

## src/

### src/core/

| Archivo | Propósito funcional | Estado | Recomendación de consolidación o migración | Riesgos si no se reorganiza |
|---|---|---|---|---|
| backtesting.py | Motor de backtest multi-símbolo; integra guardrails y TP/SL por régimen | Activo | Mantener como núcleo; leer YAML institucional | Divergencia con configuraciones externas |
| estrategias_bot1.py | Reglas de estrategia/signales | Activo | Mantener; documentar inputs/outputs | Ambigüedad en cambios de señales |
| gestor_indicadores.py | Gestión de indicadores | Activo | Mantener | Cálculos duplicados si se dispersa |
| indicadores_tecnicos.py | Indicadores técnicos | Activo | Mantener; tests básicos | Errores silenciosos en cálculo |
| config_estrategias.py | Parámetros base (algunos NO USADOS) | Mixto | Limpiar claves no usadas o mover a `config/experimental.yaml` | Confusión; cambios no efectivos |
| caracteristicas_ML.py | Features ML | Mixto/Legacy | Evaluar uso real; si no, mover a `archived_src/` | Superficie de mantenimiento innecesaria |
| ciclo_real.py | Loop de operación real | Mixto | Mantener aislado; parametrizar desde YAML | Divergencia entre real y backtest |
| archivo_principal.py | Entrada alternativa | Legacy | Deprecar si no se usa | Múltiples “main” confunden |
| prueba_parametros.py | Pruebas de parámetros | Activo | Mantener; usado en tarea “Smoke: Fase1_ext…” | Duplicación si se crean variantes |
| quick_backtest_check.py | Smoke 30d (duplicado del de scripts) | Duplicado | Eliminar y referenciar `scripts/quick_backtest_check.py` | Smokes desalineados |
| utilidades.py | Utilidades compartidas | Activo | Mantener | Funciones duplicadas si crecen en scripts |

### src/pipeline/

| Archivo | Propósito funcional | Estado | Recomendación de consolidación o migración | Riesgos si no se reorganiza |
|---|---|---|---|---|
| backfill_historicos.py | Backfill de históricos | Activo | Mantener; invocar desde runner | Desalineación de coberturas |
| carga_un_simbolo_combinado.py | Carga programática 1 símbolo | Activo | Mantener nombre snake_case (renombrado 2025-09-28) | Riesgo mitigado; verificar imports heredados |
| carga_datos.py | Carga de datos | Activo | Mantener | Duplicidad con otros loaders |
| conexion_api.py | Conexión API (p.e. Binance) | Activo | Mantener; aislar credenciales | Fugas de credenciales; acoplamiento |
| descarga_historicos.py | Descarga de históricos | Activo | Mantener | Inconsistencias con backfill |
| frecuencia_datos.py | Gestión de frecuencia (15m, etc.) | Activo | Mantener | Grid temporal disparejo |
| prepare_data.py | Preparación de datos | Activo | Mantener | Transformaciones dispersas |
| transformacion_datos.py | Transformación canónica | Activo | Mantener como “única verdad” | Incoherencias si no se centraliza |
| validacion_datos.py | Validación de datos | Activo | Integrar con QA maestro | Faltas de calidad no detectadas |
| verificar_maestro.py | Construye maestro/limpio desde múltiples históricos | Activo | Mantener; coordinar con QA 15m | Maestro inconsistente con QA |
| historiabot.ipynb | Notebook exploratorio | Activo (notebook) | Mover a `notebooks/` si no es pipeline | Drift entre notebook y codepath oficial |

### src/auxiliares/

| Archivo | Propósito funcional | Estado | Recomendación de consolidación o migración | Riesgos si no se reorganiza |
|---|---|---|---|---|
| simple_jsonl_writer.py | Utilidad de escritura JSONL | Activo | Mantener | Reimplementaciones ad-hoc |

## data/

| Ruta | Propósito funcional | Estado | Recomendación de consolidación o migración | Riesgos si no se reorganiza |
|---|---|---|---|---|
| data/backtesting/ | Artefactos de backtesting (CSVs/PNGs/MDs) | Activo (plano, masivo) | Estructurar por `runs/<timestamp>/…` con retención y `params_frozen.json` | Trazabilidad pobre; mezcla de ejecuciones |
| data/backup/ | Backups de datos | Activo | Definir ciclo de retención; documentar | Espacio/obsolescencia |
| data/config.env | Variables de entorno | Activo | Mover a `.env` y `.gitignore`; separar secretos | Exposición de secretos; drift de config |
| data/historiales/ | Maestros normalizados (15m, limpio) | Activo | QA obligatorio con `verificar_maestro_15m.py` | Gaps/duplicados colándose al backtest |
| data/historicos/ | Históricos por símbolo fuente | Activo | Políticas de naming; checksum/fecha | Fuentes heterogéneas; deduplicación |
| data/logs/ | Logs operativos | Activo | Mantener; rotación | Crecimiento sin control |
| data/papertrading/ | Artefactos de paper trading | Activo | Alinear formato con backtesting para comparabilidad | Métricas no comparables |
| data/parametros_seleccionados.json | Selección histórica de parámetros | Legacy | Migrar a `config/institucional.yaml` y deprecar | Fuente de verdad difusa |

## config/

| Archivo | Propósito funcional | Estado | Recomendación de consolidación o migración | Riesgos si no se reorganiza |
|---|---|---|---|---|
| config/institucional.yaml | Filtros institucionales, winners por símbolo, TP/SL por régimen, portfolio | No existe | Crear y convertirlo en fuente de verdad; autoload desde entrypoints | Paridad frágil entre scripts; cambios no trazables |
| config/grids.yaml | Definiciones A1–A4, B1–B6 y presets | No existe | Crear para Fase1_ext; versionar | Grids dispersos en flags/código |
| config/experimental.yaml | Claves heredadas/experimentales | No existe | Mover claves NO USADAS desde `config_estrategias.py` | Parámetros “fantasma” que no aplican |

---

Siguientes pasos sugeridos:
- Crear `config/institucional.yaml` y `config/grids.yaml` y adaptar los entrypoints a leerlos.
- Consolidar los scripts de maestro en 1 único CLI con flags (reconstrucción/resample/ventana).
- Eliminar duplicados (`src/core/quick_backtest_check.py`), renombrar el archivo con espacios en `src/pipeline`.
- Adoptar estructura `data/backtesting/runs/<timestamp>/...` con retención básica.

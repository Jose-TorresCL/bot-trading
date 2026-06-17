# Auditoría técnica y organizativa — Semana 5

Este informe inventaría el estado del código y artefactos, detecta duplicidades y riesgos, y propone una reorganización con un runner institucional y un flujo operativo reproducible. No se modifica ningún código; es un diagnóstico y plan de acción.

## Alcance y criterios
- Cobertura: `scripts/`, `src/` (core, pipeline, auxiliares), artefactos en `data/backtesting/` y documentación adyacente.
- Objetivo: trazabilidad de punta a punta (datos → backtest → selección → TP/SL por régimen → portfolio → veredicto/launch), con guardrails institucionales integrados.

## Inventario de componentes (alto nivel)

| Componente | Ruta | Rol | Entradas | Salidas | Estado | Notas |
|---|---|---|---|---|---|---|
| Backtesting engine | `src/core/backtesting.py` | Motor central; aplica filtros institucionales, TP/SL por régimen opcional | Maestro 15m, config | CSVs por símbolo, snapshot global | Activo | Integra `EXCLUDE_HOURS`, `MIN_ATR_PCT`, `MIN_BBW_PCT`, `TP_SL_BY_REGIME` |
| Estrategias y señales | `src/core/estrategias_bot1.py`, `src/core/gestor_indicadores.py`, `src/core/indicadores_tecnicos.py` | Señales, features e indicadores | OHLCV | Señales/columnas | Activo | Deterministas |
| Config de estrategia | `src/core/config_estrategias.py` | Parámetros base | — | Constantes | Mixto | Varias claves marcadas “NO USADAS” |
| Orquestación Fase 1_ext | `scripts/fase1_ext_consolidado.py` | Grid A1–A4, B1–B6, consolidado y robustez | Maestro 15m | CSV/MD de rankings | Activo | Usa costos/slippage fijos y counters |
| Fase 2 TP/SL por régimen | `scripts/fase2_tp_sl_regimen.py`, `scripts/fase2_por_simbolo.py`, `scripts/fase2_consolidado.py` | Optimización y consolidación TP/SL | Trades base por símbolo | Matrices TP/SL, MDs | Activo | Exporta artefactos por símbolo |
| Comparativa portfolio | `scripts/portfolio_compare_tp_sl.py` | Agregado ETH+BNB, correlaciones, rolling PF/DD, Top DDs, comentario/veredicto | Resultados por símbolo | CSV/PNG/MD; changelog y lanzamiento si OK | Activo | Añade comentario institucional automático |
| Validación maestro 15m | `scripts/verificar_maestro_15m.py` | QA de cobertura, gaps, calidad OHLCV | `historial_trading_maestro_15m.csv` | `validacion_maestro_15m.md` | Activo | Checks exhaustivos |
| Construcción maestro | `src/pipeline/verificar_maestro.py` | Normaliza múltiples históricos y genera maestro/límpio | `src/data/historicos/*.csv` | maestro+limpio | Activo | Conversión de timestamps robusta |
| Smokes y utilidades | `scripts/quick_backtest_check.py`, `src/core/quick_backtest_check.py` | Smoke de 30 días BTC/ETH | maestro 15m | Artefactos 30d | Duplicado | Mismo propósito en dos rutas |
| Ingesta/transformación | `src/pipeline/*` | Descarga, validación, preparación | Fuentes API/CSV | CSV normalizados | Activo | Nombres mixtos/es con espacios |
| Tareas VS Code | `.vscode/tasks.json` (vía tareas expuestas) | Ejecuciones reproducibles | — | Artefactos bajo `data/` | Activo | Smokes y A/B listos |

## Duplicidades e inconsistencias
- Duplicados directos:
  - `scripts/quick_backtest_check.py` y `src/core/quick_backtest_check.py` (idénticos). Proponer conservar uno (CLI en `scripts/`) y despublicar el otro.
  - Validación maestro: `scripts/verificar_maestro_15m.py` (QA) vs `src/pipeline/verificar_maestro.py` (construcción). Mantener ambos pero documentar la diferencia: “construir” vs “verificar”.
- Variantes solapadas:
  - `walk_forward.py` y `walk_forward_refined.py` → unificar o marcar uno como “legacy”.
  - Maestro: `reconstruir_maestro_30d.py` vs `resample_y_reconstruir_maestro.py` vs `expandir_maestro_15m.py` → consolidar en un único entrypoint de reconstrucción con flags.
  - PowerShell: `run_beta_B_12m.ps1` y `run_beta_variants.ps1` → centralizar en runner institucional.
- Nomenclatura/estructura:
  - Archivo con espacios y acentos: `src/pipeline/carga programática de un único símbolo combinando.py` → renombrar a `carga_un_symbolo_combinado.py` (ASCII, snake_case) para evitar problemas de import/CI.
  - `src/core/config_estrategias.py` contiene claves “NO USADAS”; mover a `config/experimental.yaml` o eliminar para claridad.
- Artefactos dispersos:
  - `data/backtesting/` contiene cientos de snapshots `indicadores_snapshot_YYYYMMDD_HHMMSS.*`. Proponer política de retención y subcarpetas por ejecución (`data/backtesting/runs/YYYYMMDD_HHMMSS/…`).

## Riesgos y gaps
- Configuración inconsistente entre entrypoints. Falta una única fuente de verdad (YAML/JSON congelable) para filtros institucionales, winners por símbolo y matrices TP/SL.
- Duplicidad de entrypoints de smoke y verificación puede inducir desalineaciones de parámetros.
- Retención y trazabilidad de artefactos: demasiados archivos “flat” en `data/backtesting/` sin agrupación por run.
- No hay pruebas automatizadas mínimas (unitarias/smoke) para CI; depender solo de tareas manuales es frágil.

## Propuesta de reorganización (sin cambios de lógica)
1. Estructura de carpetas objetivo
```
semana_5/
  config/
    institucional.yaml        # filtros, exclude-hours, floors, winners, TP/SL por símbolo y régimen
    grids.yaml                # definiciones A1–A4, B1–B6
  scripts/
    runner_institucional.py   # orquestación punta a punta (ver abajo)
    validar_maestro.py        # wrapper CLI sobre `scripts/verificar_maestro_15m.py`
    quick_smoke.py            # único smoke (30d) → BTC por defecto
  src/
    core/                     # motor, estrategias, indicadores
    pipeline/                 # ingestión y construcción de maestro
  data/
    backtesting/
      runs/YYYYMMDD_HHMMSS/   # carpeta por ejecución con CSV/PNG/MD
  reports/                    # markdowns consolidados (delta_*.md, portfolio_*.md)
  logs/
```
2. Política de artefactos
- Cada ejecución crea `data/backtesting/runs/<timestamp>/` y dentro: `symbols/`, `portfolio/`, `summary.csv`, `params_frozen.json`, `debug/`.
- Retención: conservar últimas N=20 ejecuciones + “pins” marcados por changelog/launch.
3. Configuración central (YAML)
- `institucional.yaml` con secciones:
  - `filters`: `exclude_hours`, `min_atr_pct`, `min_bbw_pct`, `strict_proximity`, `neutral_min_votes`, `mfe_mae_guardrail`.
  - `winners`: por símbolo (`BTCUSDT: A2`, etc.).
  - `tp_sl_by_regime`: matrices por símbolo y régimen.
  - `portfolio`: composición y pesos (equal/vol), capital por símbolo.
4. Carga automática de matrices/ganadores
- El entrypoint (backtesting o runner) autoload: si existen matrices Fase2 por símbolo → override de `k1_mult/k2_mult` en runtime.

## Runner institucional propuesto
Entrada: `config/institucional.yaml`.

Flujo:
1) Data QA: `scripts/verificar_maestro_15m.py` → `validacion_maestro_15m.md` (gate: overall OK).
2) Fase 1_ext (si se activa): correr grids A/B desde `scripts/fase1_ext_consolidado.py` → seleccionar ganadores por símbolo; escribir `winners` al YAML.
3) Fase 2: `scripts/fase2_tp_sl_regimen.py` y consolidación por símbolo; exportar matrices y MDs; actualizar YAML (`tp_sl_by_regime`).
4) Backtesting multi-símbolo: `src/core/backtesting.py` con filtros institucionales y overrides por régimen; generar artefactos por símbolo y snapshot global bajo `runs/<ts>/symbols/`.
5) Portfolio: `scripts/portfolio_compare_tp_sl.py` → métricas, rolling PF/DD, Top DDs, heatmap; veredicto institucional. Si positivo: generar `changelog_cierre_tecnico.md` y `lanzamiento_operativo.md` con parámetros congelados.
6) Publicación: copiar `reports/*` relevantes y `params_frozen.json` a la run.

Salidas clave:
- `runs/<ts>/symbols/<SYM>/*.csv|.png|.md`
- `runs/<ts>/portfolio/*.csv|.png|.md`
- `runs/<ts>/summary.csv`, `params_frozen.json`

Tareas VS Code sugeridas:
- “Smoke: runner institucional (BTC 30d)”
- “Full: portfolio ETH+BNB 6–12m”
- “QA maestro 15m”

## Acciones rápidas de bajo riesgo (recomendadas)
- Deprecate/elim duplicado: conservar `scripts/quick_backtest_check.py` y borrar/eliminar de rutas el de `src/core/` (o marcarlo como wrapper que importa del de `scripts/`).
- Renombrar archivo con espacios en `src/pipeline` a snake_case ASCII.
- Mover claves “NO USADAS” de `config_estrategias.py` a `config/experimental.yaml` o purgarlas.
- Agrupar snapshots de indicadores en `data/backtesting/runs/<ts>/debug/` y limpiar raíz.

## Calidad (quality gates) y control
- Build: N/A (Python script-only). Lint sugerido: `ruff`/`flake8` + `black`.
- Tests: añadir dos smokes mínimos (pytest):
  - Carga maestro y QA de grilla 15m sin fallos (BTC sample).
  - Backtesting 30d BTC con parámetros congelados y aserción de PF>0.9 y sin NaNs.
- Tareas existentes: se detectaron smokes útiles ya configurados; unificarlas bajo el runner propuesto.

## Próximos pasos
1) Aceptar estructura propuesta y crear `config/institucional.yaml` (inicialmente con filtros y winners actuales; matrices Fase2 cargadas).  
2) Implementar `scripts/runner_institucional.py` como orquestador (reutilizando los scripts actuales).  
3) Unificar duplicados y renombrar archivo con espacios.  
4) Mover artefactos de ejecuciones futuras a `data/backtesting/runs/<ts>/` y definir retención.  
5) Añadir dos pruebas smoke (pytest) y una tarea VS Code “Smoke: runner institucional (BTC 30d)”.

## Apéndice: Guardrails institucionales (estado)
- Matching por barra más cercana y `strict_proximity` configurable.
- Filtros de entrada: `EXCLUDE_HOURS`, `MIN_ATR_PCT`, `MIN_BBW_PCT`.
- Guardrails de riesgo: MFE/MAE ratio mínimo opcional.
- Votos/consenso de régimen (`neutral_min_votes`).
- TP/SL por régimen: overrides aplicados en entrada y chequeos de salida.
- Costos y slippage fijos aplicados en grids.

—
Este documento busca dejar listo el terreno para una “línea de montaje” reproducible y defendible de cara a operación institucional, con decisiones congelables y reportes autoexplicativos.

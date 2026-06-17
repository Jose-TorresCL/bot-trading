# Auditoría técnica y organizativa — Corte 2025-09-28

## 1. Resumen ejecutivo
- **Gobernanza**: `config/institucional.yaml` consolidado y consumido por `src/config_loader.py`, ahora con validación estructural, saneo de horas y hash SHA-256 congelado en `freeze_params`.
- **Contexto operativo**: se añadió `config/contexto.yaml` con historia, hitos y métricas clave, enlazando las auditorías vigentes.
- **Auditoría de sesgo**: `auditoria_sesgo_operativo.md` integra métricas por símbolo (bloqueos ADX/ATR/VOTOS y volumen de señales), habilitando modularidad por régimen.
- **Higiene de scripts**: duplicado `src/core/quick_backtest_check.py` retirado; se mantiene una sola versión en `scripts/quick_backtest_check.py`.
- **Pruebas**: suite `pytest` inicial con validación del cargador YAML y smoke del motor de backtesting.
- **Pendientes**: runner institucional unificado.

## 2. Avances desde la auditoría del 2025-09-18
| Área | Hallazgo anterior | Estado 2025-09-28 | Evidencia |
|---|---|---|---|
| Fuente de verdad institucional | No existía YAML consolidado | ✅ `config/institucional.yaml` activo y versionado | Archivo + validación en `src/config_loader.py` (líneas 14-149)
| Cargador de configuración | Sin validaciones, horas crudas | ✅ Validación de esquema, limpieza de horas y metadatos congelados | `src/config_loader.py` líneas 34-148 y 170-206
| Congelado de parámetros | Sin hash ni copia YAML | ✅ SHA-256 y copia bajo `metadata/` | `freeze_params` en `src/config_loader.py` líneas 188-206
| Duplicidad de smoke tests | Existían dos quick_backtest | ✅ Se retiró variante en `src/core/` | Carpeta `src/core/` (sin quick_backtest)
| Contexto operativo | Información dispersa | ✅ `config/contexto.yaml` documenta hitos/auditorías | Archivo creado 2025-09-28
| Auditoría de sesgo | Recomendación genérica | ✅ Métricas detalladas por símbolo | `auditoria_sesgo_operativo.md`

## 3. Estado actual por dominios
### 3.1 Configuración y gobernanza
- `config/institucional.yaml`: estándar de filtros, TP/SL y portfolio; requiere cablear TP/SL dinámico en el motor (`src/core/backtesting.py`).
- `src/config_loader.py`: aplica `_validate_schema`, normaliza `exclude_hours`, agrega hash y metadata. Sigue pendiente integrar validaciones cruzadas (e.g. pesos de portfolio) y tests automatizados.
- `config/contexto.yaml`: centraliza historia, hitos, auditorías y próximos pasos.

### 3.2 Motor de backtesting y runners
- `src/core/backtesting.py`: motor enriquecido, pero la lógica de generación de trades aún es simplificada; pendiente portar completamente el flujo institucional (Beta A2) y cablear TP/SL por régimen desde YAML.
- Runners activos: `scripts/ab_sesgo_fix.py`, `scripts/institucional_smoke.py`. Falta runner único institucional con QA → Fase1/2 → portfolio.

### 3.3 Scripts y pipelines
- Duplicidades resueltas: quick smoke consolidado en `scripts/quick_backtest_check.py`.
- Script renombrado: `src/pipeline/carga_un_simbolo_combinado.py` reemplaza al archivo con espacios y acentos.
- Scripts con riesgos: ejecutables PowerShell siguen activos; se recomienda migrarlos a tareas Python/VS Code.
- PowerShell (`run_beta_B_12m.ps1`, `run_beta_variants.ps1`) siguen operativos pero replican flags; sugerido migrar a tareas Python/VS Code.

### 3.4 Datos, QA y auditorías
- QA maestro: `scripts/verificar_maestro_15m.py` permanece como gate; sin cambios.
- Auditoría de sesgo operativo documenta tasas de bloqueo y señales aprobadas para BTC/ETH/BNB/WLD.
- Artefactos de backtesting aún distribuidos en `data/backtesting/`; pendiente migración a `runs/<timestamp>/`.

### 3.5 Documentación y bitácora
- `bitácora técnica y de reflexión.md` requiere actualización para reflejar la reorganización, uso de notebooks y lecciones de paper trading (pendiente del usuario).

## 4. Riesgos y pendientes prioritarios
1. **Runner institucional unificado**: orquestar QA maestro → Fase1/Fase2 → backtesting → portfolio con congelado automático.
2. **Portar lógica completa de Beta A2** a `src/core/backtesting.py`, incluyendo TP/SL por régimen y guardrails de MFE/MAE.
3. **Reorganizar artefactos** en `data/backtesting/runs/<timestamp>/` con política de retención.
4. **Documentar veredictos y comparativas** en dashboard longitudinal (usando notebooks/reportes consolidados).

## 5. Próximas acciones sugeridas (ordenadas)
1. Extender `src/core/backtesting.py` para leer `tp_sl_by_regime` desde `cfg.tp_sl_by_regime` y reflejarlo en `_resolve_tp_sl`/`_simulate_trades`.
2. Crear `scripts/runner_institucional.py` que integre QA + Fase1/Fase2 + backtesting + portfolio, consumiendo `config/institucional.yaml`.
3. Migrar artefactos nuevos a `data/backtesting/runs/<timestamp>/` y añadir `params_frozen.json` + copia YAML.
4. Actualizar `bitácora técnica y de reflexión.md` con aprendizajes recientes.

---
**Notas**
- Último commit analizado: rama `probandorama`, corte 2025-09-28.
- Esta auditoría complementa a `auditoria_sesgo_operativo.md` y `auditoria_tablas_por_carpeta.md`, manteniendo foco en gobernanza técnica y trazabilidad.

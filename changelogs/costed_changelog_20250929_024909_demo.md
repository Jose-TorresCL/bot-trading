# Changelog Técnico - Fase 2 Costed
## Run: 20250929_024909_demo
## Generado: 2025-09-29T02:49:09.479645+00:00

### Hash del YAML institucional
```
demo_hash_20250929_024909
```

### Versiones
- METRICS_VERSION: 1.0.0
- Motor: Beta A2 con modelo de costos trade-a-trade

### Parámetros de costo aplicados
- Fee: 0.0008 (0.08%)
- Slippage: 0.0005 (0.05%)
- Notional base: 1000.00

### Umbrales de robustez
- Min PF net: 1.0
- PF review threshold: 1.5
- Max DD threshold: 0.25

### Resumen por símbolo

#### BNBUSDT
- **Veredicto**: REVIEW
- **Razón**: Max_DD=51.84 > 0.25
- **PF Net**: 3.54
- **Expectancy Net**: 23.5250
- **Winrate Net**: 65.0%
- **Max DD Net**: 51.8447

#### BTCUSDT
- **Veredicto**: REVIEW
- **Razón**: Max_DD=660.38 > 0.25
- **PF Net**: 1.99
- **Expectancy Net**: 49.8446
- **Winrate Net**: 53.3%
- **Max DD Net**: 660.3838

#### ETHUSDT
- **Veredicto**: REVIEW
- **Razón**: Max_DD=379.85 > 0.25
- **PF Net**: 3.18
- **Expectancy Net**: 53.0176
- **Winrate Net**: 56.7%
- **Max DD Net**: 379.8459

### Resumen consolidado
- **Total símbolos**: 3
- **ACCEPT**: 0
- **REVIEW**: 3
- **REJECT**: 0

### Artefactos generados
```
runs/20250929_024909_demo/_costed/
├── <SYMBOL>/
│   ├── trades_enriched_costed.csv
│   ├── session_summary_net.csv
│   ├── grid_resultados_net.csv
│   └── veredicto.json
└── run_metadata_update.json
```

### Logs estructurados
- COST_MODEL_APPLIED: 3 símbolos procesados
- METRICS_NET_COMPUTED: Métricas netas calculadas por símbolo
- VERDICT_ISSUED: 0 ACCEPT, 3 REVIEW, 0 REJECT

---
**Etiqueta**: Fase 2 — Capa de costos y veredictos operativos

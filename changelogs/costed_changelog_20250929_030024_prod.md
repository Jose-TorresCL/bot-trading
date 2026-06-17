# Changelog Técnico - Fase 2 Costed
## Run: 20250929_030024_prod
## Generado: 2025-09-29T03:00:39.416064+00:00

### Hash del YAML institucional
```
prod_20250929_030024
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
- **Veredicto**: REJECT
- **Razón**: PF_net=0.58 < 1.0
- **PF Net**: 0.58
- **Expectancy Net**: -85.9438
- **Winrate Net**: 38.4%
- **Max DD Net**: 48526.2543

#### BTCUSDT
- **Veredicto**: REJECT
- **Razón**: PF_net=0.40 < 1.0
- **PF Net**: 0.40
- **Expectancy Net**: -14301.4212
- **Winrate Net**: 33.8%
- **Max DD Net**: 7824628.8488

#### ETHUSDT
- **Veredicto**: REJECT
- **Razón**: PF_net=0.62 < 1.0
- **PF Net**: 0.62
- **Expectancy Net**: -525.3322
- **Winrate Net**: 42.6%
- **Max DD Net**: 289220.3399

### Resumen consolidado
- **Total símbolos**: 3
- **ACCEPT**: 0
- **REVIEW**: 0
- **REJECT**: 3

### Artefactos generados
```
runs/20250929_030024_prod/_costed/
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
- VERDICT_ISSUED: 0 ACCEPT, 0 REVIEW, 3 REJECT

---
**Etiqueta**: Fase 2 — Capa de costos y veredictos operativos

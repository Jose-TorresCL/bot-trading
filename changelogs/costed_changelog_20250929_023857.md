# Changelog Técnico - Fase 2 Costed
## Run: 20250929_023857
## Generado: 2025-09-29T02:47:21.877527+00:00

### Hash del YAML institucional
```
d9e4a04f6c187fc38b8d330d9fce71be137b145721bc24bb25808c53642e225a
Timestamp: 20250929_023857
Symbol: BNBUSDT
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

### Resumen consolidado
- **Total símbolos**: 3
- **ACCEPT**: 0
- **REVIEW**: 0
- **REJECT**: 0

### Artefactos generados
```
runs/20250929_023857/_costed/
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
- VERDICT_ISSUED: 0 ACCEPT, 0 REVIEW, 0 REJECT

---
**Etiqueta**: Fase 2 — Capa de costos y veredictos operativos

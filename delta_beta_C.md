# A/B Sesgo Operativo — Ajustes mínimos por régimen

## Configuración

- months: 6
- bar_tolerance: ±6
- strict_proximity: ±3
- rsi_tolerance: ±2.0
- admission: conditional
- min_atr_pct: 0.22
- min_bbw_pct: 0.18
- exclude_hours UTC: [0, 1, 2, 12, 13, 14]

## Resumen por símbolo
| Símbolo | Δpf_net | Δexpectancy | Δmax_dd | Reducción bloqueos (ADX/VOTES) | Candidatos | Admitidos |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 0.818 | -70.21196 | -27412.352 | 43.1% | 5090 | 2192 |
| ETHUSDT | 0.989 | -0.18824 | -524.907 | 48.8% | 4963 | 2420 |
| BNBUSDT | 0.817 | -0.54331 | -175.344 | 45.6% | 5174 | 2361 |
| WLDUSDT | 0.450 | -0.00922 | -1.233 | 46.2% | 5049 | 2334 |

> Nota: Ver grid_results_sesgo_fix.csv para fees_share_pct, trades_per_day y diversidad por régimen (unique_regimes, top_regime_share).
## Criterios de aceptación
- Reducción ≥ 20% bloqueos por ADX/VOTES en regímenes afectados
- pf_net y expectancy iguales o mejores (vs baseline bloqueado ≈ 0)
- max_dd no empeora más de 10% (no aplica con baseline=0; observar valor absoluto)
- Diversidad operativa aumentada sin inflar falsos positivos (revisar trades y fees_share en análisis posterior)
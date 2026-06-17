# A/B Sesgo Operativo — Ajustes mínimos por régimen

## Configuración

- months: 6
- bar_tolerance: ±6
- strict_proximity: ±1
- rsi_tolerance: ±2.0
- admission: conditional
- min_atr_pct: 0.25
- min_bbw_pct: 0.15
- exclude_hours UTC: [0, 1, 2, 12, 13, 14]

## Resumen por símbolo
| Símbolo | Δpf_net | Δexpectancy | Δmax_dd | Reducción bloqueos (ADX/VOTES) | Candidatos | Admitidos |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 0.874 | -46.66917 | -14962.919 | 42.7% | 4960 | 2117 |
| ETHUSDT | 1.050 | 0.89731 | -479.608 | 48.1% | 4827 | 2322 |
| BNBUSDT | 0.745 | -0.78762 | -196.698 | 45.4% | 5039 | 2290 |
| WLDUSDT | 0.391 | -0.01073 | -0.949 | 45.4% | 4908 | 2227 |

> Nota: Ver grid_results_sesgo_fix.csv para fees_share_pct, trades_per_day y diversidad por régimen (unique_regimes, top_regime_share).
## Criterios de aceptación
- Reducción ≥ 20% bloqueos por ADX/VOTES en regímenes afectados
- pf_net y expectancy iguales o mejores (vs baseline bloqueado ≈ 0)
- max_dd no empeora más de 10% (no aplica con baseline=0; observar valor absoluto)
- Diversidad operativa aumentada sin inflar falsos positivos (revisar trades y fees_share en análisis posterior)
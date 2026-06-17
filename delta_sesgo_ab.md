# A/B Sesgo Operativo — Ajustes mínimos por régimen

## Configuración

- months: 12
- bar_tolerance: ±6
- strict_proximity: ±2
- rsi_tolerance: ±2.0
- admission: conditional
- min_atr_pct: 0.25
- min_bbw_pct: 0.15
- exclude_hours UTC: [0, 1, 2, 12, 13, 14]
- min_mfe_mae_ratio: 1.2

## Resumen por símbolo
| Símbolo | Δpf_net | Δexpectancy | Δmax_dd | Reducción bloqueos (ADX/VOTES) | Candidatos | Admitidos |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 0.000 | nan | 0.000 | 41.3% | 8894 | 3673 |
| ETHUSDT | 0.000 | nan | 0.000 | 46.3% | 8761 | 4053 |
| BNBUSDT | 2.159 | 2.34488 | -47.065 | 44.2% | 9145 | 4040 |
| WLDUSDT | 0.000 | nan | 0.000 | 43.7% | 8991 | 3925 |

> Nota: Ver grid_results_sesgo_fix.csv para fees_share_pct, trades_per_day y diversidad por régimen (unique_regimes, top_regime_share).
## Criterios de aceptación
- Reducción ≥ 20% bloqueos por ADX/VOTES en regímenes afectados
- pf_net y expectancy iguales o mejores (vs baseline bloqueado ≈ 0)
- max_dd no empeora más de 10% (no aplica con baseline=0; observar valor absoluto)
- Diversidad operativa aumentada sin inflar falsos positivos (revisar trades y fees_share en análisis posterior)
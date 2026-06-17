# A/B Sesgo Operativo — Ajustes mínimos por régimen

## Configuración

- months: 12
- bar_tolerance: ±6
- strict_proximity: ±2
- rsi_tolerance: ±2.0
- admission: conditional
- min_atr_pct: 0.22
- min_bbw_pct: 0.15
- exclude_hours UTC: [0, 1, 2, 12, 13, 14]
- min_mfe_mae_ratio: 1.2

## Resumen por símbolo
| Símbolo | Δpf_net | Δexpectancy | Δmax_dd | Reducción bloqueos (ADX/VOTES) | Candidatos | Admitidos |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 1.405 | 128.40826 | -17901.661 | 42.8% | 10075 | 4312 |
| ETHUSDT | 1.641 | 8.82364 | -436.012 | 48.0% | 9948 | 4780 |
| BNBUSDT | 1.715 | 1.61375 | -69.685 | 45.2% | 10378 | 4689 |
| WLDUSDT | 0.821 | -0.00369 | -0.643 | 44.9% | 10213 | 4583 |

> Nota: Ver grid_results_sesgo_fix.csv para fees_share_pct, trades_per_day y diversidad por régimen (unique_regimes, top_regime_share).
## Criterios de aceptación
- Reducción ≥ 20% bloqueos por ADX/VOTES en regímenes afectados
- pf_net y expectancy iguales o mejores (vs baseline bloqueado ≈ 0)
- max_dd no empeora más de 10% (no aplica con baseline=0; observar valor absoluto)
- Diversidad operativa aumentada sin inflar falsos positivos (revisar trades y fees_share en análisis posterior)
# Comparativa institucional 12 meses — Beta A vs Beta B

Paridad de parámetros: months=12, strict_proximity=2, min_mfe_mae_ratio(B)=1.4, min_atr_pct=0.22, min_bbw_pct=0.15, admission=conditional, neutral_min_votes=4, exclude_hours UTC=[0,1,2,12,13,14], bar_tolerance=±6, rsi_tolerance=±2.

## Resumen por símbolo (A → B)

- BTCUSDT
  - pf_net: 1.405 → 1.715
  - expectancy: 128.41 → 204.49
  - max_dd: -17,901.66 → -17,901.66 (≈ igual)
  - trades: 243 → 218 | trades/día: 0.666 → 0.597
  - fees_share_pct: 9.79% → 9.58%
- ETHUSDT
  - pf_net: 1.641 → 1.931
  - expectancy: 8.82 → 11.44
  - max_dd: -436.01 → -205.38 (mejor)
  - trades: 233 → 217 | trades/día: 0.638 → 0.595
  - fees_share_pct: 6.16% → 6.23% (≈ igual)
- BNBUSDT
  - pf_net: 1.715 → 1.915
  - expectancy: 1.61 → 1.94
  - max_dd: -69.68 → -48.62 (mejor)
  - trades: 253 → 235 | trades/día: 0.693 → 0.644
  - fees_share_pct: 8.60% → 8.48%
- WLDUSDT
  - pf_net: 0.821 → 0.928 (sigue < 1)
  - expectancy: -0.0037 → -0.00144 (sigue negativa)
  - max_dd: -0.643 → -0.617 (ligeramente mejor)
  - trades: 93 → 85 | trades/día: 0.255 → 0.233
  - fees_share_pct: 29.94% → 28.54%

## Contadores de depuración (B, 12m)

- BTCUSDT: candidatos 7,590 → admitidos 594; sin-trade-en-ventana 2,663; rechazo_admisión 2,538; dist_demasiado_lejos 974; regímenes únicos 5; top_regime_share 0.359.
- ETHUSDT: 7,476 → 582; sin-trade 2,488; rechazo 2,443; distancia 1,139; regímenes=5; top_share 0.397.
- BNBUSDT: 7,717 → 632; sin-trade 2,428; rechazo 2,634; distancia 1,193; regímenes=5; top_share 0.383.
- WLDUSDT: 7,622 → 218; sin-trade 5,983; rechazo 805; distancia 406; regímenes=5; top_share 0.468.

Observación: En WLD la conversión candidato→admitido es baja y el principal descarte es “sin trade en ventana”, lo que reduce frecuencia y dificulta superar costes.

## Conclusión ejecutiva

- Adoptar Beta B en BTC/ETH/BNB: mejora pf_net y expectancy con igual o menor drawdown; frecuencia algo menor y fees estables o menores.
- Excluir WLD de producción por ahora: pf_net < 1 y expectancy negativa; costes relativos altos y baja conversión de señales.
- Próximos pasos sugeridos:
  - Monitoreo rolling (p. ej., últimas 6–9m) para confirmar estabilidad del edge de B.
  - Ajuste selectivo de “strict_proximity” o ventanas en WLD si se quiere reintentar elevar conversión sin inflar falsos positivos.

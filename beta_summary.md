# Beta A–D (6 months) — Summary and next steps

## Artifacts generated
- grid_results_beta_A.csv, delta_beta_A.md
- grid_results_beta_B.csv, delta_beta_B.md
- grid_results_beta_C.csv, delta_beta_C.md
- grid_results_beta_D.csv, delta_beta_D.md

No trades_enriched_beta_*.csv were produced for A–D (no admitted trades under these settings).

## Quick read
- All four Beta variants (A–D) yielded 0 admitted trades for BTCUSDT, ETHUSDT, BNBUSDT, and WLDUSDT.
- This indicates the current thresholds are too tight in combination: strict_proximity in {1,2,3}, AT R/BBW quality floors, exclude_hours, and neutral-min-votes=4 leave no eligible setup within ±bar windows.
- Sanity check passed: a smoke re-run on BTCUSDT with a relaxed strict_proximity=±6 admitted 392 trades and produced trades_enriched output, confirming the pipeline is functioning after the timestamp alignment fix.

## Snapshot (from grid_results)
| Variant | strict_proximity | min_atr_pct | min_bbw_pct | min_mfe_mae_ratio | BTC | ETH | BNB | WLD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Beta A | ±2 | 0.22 | 0.15 | —   | 0 | 0 | 0 | 0 |
| Beta B | ±2 | 0.22 | 0.15 | 1.4 | 0 | 0 | 0 | 0 |
| Beta C | ±3 | 0.22 | 0.18 | —   | 0 | 0 | 0 | 0 |
| Beta D | ±1 | 0.25 | 0.15 | —   | 0 | 0 | 0 | 0 |

## Interpretation
- With the timestamp issue fixed, the zero-trade outcome now reflects gating rather than a bug.
- The added guardrails (exclude hours, quality floors, neutral min-votes, strict proximity) jointly leave few/no matches for relaxed trades near baseline-blocked signals.

## Recommended next steps
Pick one small relaxation to regain signal without overfitting. Suggested order of operations:
1) Increase only strict_proximity to ±4 or ±6 (keep other thresholds unchanged). This is the least biased change and validated by the BTCUSDT smoke (±6).
2) If still zero on some symbols, lower neutral-min-votes from 4 to 3 (only for neutral regime). This targets the most prevalent regime bottleneck.
3) Optionally relax one quality floor slightly (try min_atr_pct=0.20 or min_bbw_pct=0.12) while keeping strict_proximity at ±2 or ±3.

Optional diagnostics:
- Re-run Beta A with `--log-candidates` to print candidate/admitted counters per symbol and verify where rejections concentrate (no relaxed trade in window vs proximity vs regime thresholds).
- Export per-regime candidate counts to a small CSV for transparency if needed.

Once a variant yields non-zero admitted trades across ≥2 symbols with reasonable pf_net/expectancy and fees_share_pct, we can freeze those settings and proceed to a 12-month validation.

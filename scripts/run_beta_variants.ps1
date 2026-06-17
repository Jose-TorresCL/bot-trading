$ErrorActionPreference = 'Stop'

# Base paths
$base   = 'c:\Users\lenovo\bot_trading\semana_5'
$master = Join-Path $base 'data\historiales\historial_trading_maestro_15m.csv'
$script = Join-Path $base 'scripts\ab_sesgo_fix.py'
$bt     = 'python'
$syms   = @('BTCUSDT','ETHUSDT','BNBUSDT','WLDUSDT')
$months = 6

Write-Host "Running Beta B/C/D for months=$months on: $syms" -ForegroundColor Cyan

# Beta B
& $bt $script `
  --master $master `
  --symbols @syms `
  --months $months `
  --bar-tolerance 6 `
  --rsi-tolerance 2 `
  --admission conditional `
  --strict-proximity 2 `
  --min-atr-pct 0.22 `
  --min-bbw-pct 0.15 `
  --exclude-hours "0,1,2,12,13,14" `
  --neutral-min-votes 4 `
  --min-mfe-mae-ratio 1.4 `
  --out_csv 'grid_results_beta_B.csv' `
  --out_md 'delta_beta_B.md' `
  --out_trades 'trades_enriched_beta_B.csv' `
  --debug-csv 'debug_counters_beta_B.csv'

# Beta C
& $bt $script `
  --master $master `
  --symbols @syms `
  --months $months `
  --bar-tolerance 6 `
  --rsi-tolerance 2 `
  --admission conditional `
  --strict-proximity 3 `
  --min-atr-pct 0.22 `
  --min-bbw-pct 0.18 `
  --exclude-hours "0,1,2,12,13,14" `
  --neutral-min-votes 4 `
  --out_csv 'grid_results_beta_C.csv' `
  --out_md 'delta_beta_C.md' `
  --out_trades 'trades_enriched_beta_C.csv' `
  --debug-csv 'debug_counters_beta_C.csv'

# Beta D
& $bt $script `
  --master $master `
  --symbols @syms `
  --months $months `
  --bar-tolerance 6 `
  --rsi-tolerance 2 `
  --admission conditional `
  --strict-proximity 1 `
  --min-atr-pct 0.25 `
  --min-bbw-pct 0.15 `
  --exclude-hours "0,1,2,12,13,14" `
  --neutral-min-votes 4 `
  --out_csv 'grid_results_beta_D.csv' `
  --out_md 'delta_beta_D.md' `
  --out_trades 'trades_enriched_beta_D.csv' `
  --debug-csv 'debug_counters_beta_D.csv'

Write-Host "Completed Beta B/C/D runs." -ForegroundColor Green

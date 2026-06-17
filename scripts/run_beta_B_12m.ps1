$ErrorActionPreference = 'Stop'

$base   = 'c:\Users\lenovo\bot_trading\semana_5'
$master = Join-Path $base 'data\historiales\historial_trading_maestro_15m.csv'
$script = Join-Path $base 'scripts\ab_sesgo_fix.py'
$bt     = 'python'
$syms   = @('BTCUSDT','ETHUSDT','BNBUSDT','WLDUSDT')
$months = 12

Write-Host "Running Beta B (12m) with guardrail MMER>=1.4 on: $($syms -join ', ')" -ForegroundColor Cyan

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

Write-Host "Completed 12m Beta B run." -ForegroundColor Green
$ErrorActionPreference = 'Stop'

$base   = 'c:\Users\lenovo\bot_trading\semana_5'
$master = Join-Path $base 'data\historiales\historial_trading_maestro_15m.csv'
$script = Join-Path $base 'scripts\ab_sesgo_fix.py'

# Prefer project venv python if available
$btVenv = Join-Path $base '.venv\Scripts\python.exe'
if (Test-Path $btVenv) {
  $bt = $btVenv
} else {
  $bt = 'python'
}

$syms = @('BTCUSDT','ETHUSDT','BNBUSDT','WLDUSDT')

Write-Host "Running Beta B (12m) with guardrail MFE/MAE >= 1.4 on: $($syms -join ', ')" -ForegroundColor Cyan

& $bt $script `
  --master $master `
  --symbols @syms `
  --months 12 `
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

Write-Host "Completed Beta B (12m)." -ForegroundColor Green

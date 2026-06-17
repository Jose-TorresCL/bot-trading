import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

try:
    from scipy.stats import skew as _skew
except Exception:  # fallback simple
    def _skew(x):
        x = np.asarray(x, dtype=float)
        x = x[~np.isnan(x)]
        if len(x) < 3:
            return np.nan
        m = x.mean(); s = x.std(ddof=0)
        if s == 0:
            return 0.0
        return np.mean(((x - m)/s)**3)

RUN_ID = os.environ.get("SANITY_RUN_ID")  # optional explicit run id (YYYY-MM-DD_HH-MM)
BASE_ANALISIS = os.path.join("data", "backtesting", "ANALISIS")

# Defaults to latest timestamped folder inside ANALISIS

def latest_analisis_dir():
    if not os.path.isdir(BASE_ANALISIS):
        return None
    dirs = []
    for d in os.listdir(BASE_ANALISIS):
        full = os.path.join(BASE_ANALISIS, d)
        if os.path.isdir(full):
            # expect pattern YYYY-MM-DD_HH-MM
            if len(d) >= 16 and d[4] == '-' and d[7] == '-' and '_' in d:
                dirs.append(full)
    return sorted(dirs)[-1] if dirs else None

if RUN_ID:
    TARGET_DIR = os.path.join(BASE_ANALISIS, RUN_ID, 'modelo_costos')
else:
    _base = latest_analisis_dir()
    TARGET_DIR = os.path.join(_base, 'modelo_costos') if _base else None

if not TARGET_DIR or not os.path.isdir(TARGET_DIR):
    print("No se encontró carpeta modelo_costos para análisis de sanity.")
    raise SystemExit(1)

GLOBAL_TRADES = os.path.join(TARGET_DIR, 'trades_enriched_global.csv')
METRICS_FILE = os.path.join(TARGET_DIR, 'metrics_cost_adjusted.csv')

if not os.path.exists(GLOBAL_TRADES):
    print(f"No existe {GLOBAL_TRADES}")
    raise SystemExit(1)
if not os.path.exists(METRICS_FILE):
    print(f"No existe {METRICS_FILE}")
    raise SystemExit(1)

trades = pd.read_csv(GLOBAL_TRADES)
metrics = pd.read_csv(METRICS_FILE)

# Ensure columns
for c in ["symbol", "net_pnl", "r_multiple", "r_multiple_net", "mae", "risk_abs"]:
    if c not in trades.columns:
        # create placeholder
        trades[c] = np.nan

# Derived columns
if trades['r_multiple_net'].isna().all() and ('risk_abs' in trades and 'pnl' in trades):
    risk_abs_series = pd.to_numeric(trades['risk_abs'], errors='coerce')
    pnl_gross = pd.to_numeric(trades.get('pnl', np.nan), errors='coerce')
    trades['r_multiple_net'] = np.where((risk_abs_series.notna()) & (risk_abs_series != 0), pnl_gross / risk_abs_series, np.nan)

# Functions ---------------------------------------------------------------

def mae_efficiency(df_sym: pd.DataFrame) -> float:
    if 'mae' not in df_sym.columns or 'risk_abs' not in df_sym.columns:
        return np.nan
    mae = pd.to_numeric(df_sym['mae'], errors='coerce')
    risk = pd.to_numeric(df_sym['risk_abs'], errors='coerce')
    valid = (risk.notna()) & (risk > 0) & (mae.notna())
    if valid.sum() == 0:
        return np.nan
    eff = (mae[valid] < 0.7 * risk[valid]).mean()
    return float(eff)  # 0..1

def pf_net_flag(row):
    # row from metrics_cost_adjusted if available
    try:
        pf = float(row.get('pf_net', np.nan))
        trades_n = int(row.get('trades', 0))
        return not (pf > 3 and trades_n < 20)
    except Exception:
        return True

# Aggregation -------------------------------------------------------------

symbols = sorted([s for s in trades['symbol'].dropna().unique() if s != '__GLOBAL__'])

rows = []
flags = {}

# Total net pnl for concentration
net_tot = pd.to_numeric(trades['net_pnl'], errors='coerce').fillna(0.0).sum()

for sym in symbols:
    df_sym = trades[trades['symbol'] == sym].copy()
    n_trades = len(df_sym)
    net = pd.to_numeric(df_sym['net_pnl'], errors='coerce').fillna(0.0)
    gains = net[net > 0].sum()
    losses = net[net <= 0].sum()
    if losses < 0:
        pf_net = (gains / abs(losses)) if abs(losses) > 0 else (np.inf if gains>0 else 0)
    else:
        pf_net = np.inf if gains>0 else 0
    winrate = (net > 0).mean()*100.0 if n_trades else 0.0
    r_mult_net = pd.to_numeric(df_sym.get('r_multiple_net'), errors='coerce')
    skew_val = _skew(r_mult_net.dropna().values) if r_mult_net.notna().sum() >= 3 else np.nan
    mae_eff = mae_efficiency(df_sym)
    share = (net.sum()/net_tot) if net_tot != 0 else 0

    # Flags
    flag_min_trades = n_trades >= 30
    flag_pf_inflated = not (pf_net > 3 and n_trades < 20)  # True if OK
    flag_skew_ok = not ((skew_val is not np.nan) and (skew_val > 2 or skew_val < -2))
    flag_mae_eff_ok = (mae_eff >= 0.60) if not np.isnan(mae_eff) else False
    flag_concentration_ok = not (share > 0.50)

    flags[sym] = {
        'min_trades_ok': flag_min_trades,
        'pf_net_ok': flag_pf_inflated,
        'skew_ok': flag_skew_ok,
        'mae_eff_ok': flag_mae_eff_ok,
        'concentration_ok': flag_concentration_ok
    }

    rows.append({
        'symbol': sym,
        'trades': n_trades,
        'pf_net': float(pf_net if np.isfinite(pf_net) else 0.0),
        'winrate_net': winrate,
        'r_multiple_net_median': float(r_mult_net.median()) if r_mult_net.notna().any() else np.nan,
        'skew_r_multiple_net': float(skew_val) if skew_val is not np.nan else np.nan,
        'mae_eff_pct': mae_eff*100.0 if not np.isnan(mae_eff) else np.nan,
        'pnl_share': share*100.0
    })

# Build markdown ----------------------------------------------------------

report_lines = ["# Sanity Report del Run\n",
                f"Generado: {datetime.utcnow().isoformat()}Z\n",
                f"Origen: {TARGET_DIR}\n",
                "\n## Métricas por Símbolo\n"]
if rows:
    cols = ['symbol','trades','pf_net','winrate_net','r_multiple_net_median','skew_r_multiple_net','mae_eff_pct','pnl_share']
    header = '| ' + ' | '.join(cols) + ' |'\
             + '\n|' + '|'.join(['---']*len(cols)) + '|' 
    report_lines.append(header)
    for r in rows:
        report_lines.append('| ' + ' | '.join(str(r.get(c, '')) for c in cols) + ' |')
else:
    report_lines.append("No hay símbolos para reportar.\n")

# Alerts ------------------------------------------------------------------
alerts = []
for sym, fdict in flags.items():
    if not fdict['min_trades_ok']:
        alerts.append(f"{sym}: insuficientes trades (<30)")
    if not fdict['pf_net_ok']:
        alerts.append(f"{sym}: PF_net posiblemente inflado (PF>3 con pocos trades)")
    if not fdict['skew_ok']:
        alerts.append(f"{sym}: skew extremo en r_multiple_net")
    if not fdict['mae_eff_ok']:
        alerts.append(f"{sym}: baja eficiencia de stops (MAE<0.7R <60%)")
    if not fdict['concentration_ok']:
        alerts.append(f"{sym}: concentración de PnL >50%")

report_lines.append("\n## Alertas\n")
if alerts:
    for a in alerts:
        report_lines.append(f"- {a}")
else:
    report_lines.append("- Sin alertas críticas bajo reglas definidas.")

# Recommendations ---------------------------------------------------------
report_lines.append("\n## Recomendaciones\n")
if alerts:
    if any('PF_net' in a or 'inflado' in a for a in alerts):
        report_lines.append("- Revisar robustez (walk-forward) antes de optimizar.")
    if any('insuficientes' in a for a in alerts):
        report_lines.append("- Recolectar más datos o ampliar ventana temporal.")
    if any('skew extremo' in a for a in alerts):
        report_lines.append("- Investigar outliers; considerar trimming wins/losses extremos.")
    if any('baja eficiencia' in a for a in alerts):
        report_lines.append("- Ajustar SL/TP o trailing para reducir MAE relativa.")
    if any('concentración' in a for a in alerts):
        report_lines.append("- Rebalancear asignación o limitar riesgo en símbolo dominante.")
else:
    report_lines.append("- Condiciones dentro de parámetros; proceder con análisis temporal.")

# Save artifacts ----------------------------------------------------------
report_path = os.path.join(TARGET_DIR, 'sanity_report.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(report_lines) + '\n')

flags_path = os.path.join(TARGET_DIR, 'sanity_flags.json')
with open(flags_path, 'w', encoding='utf-8') as f:
    json.dump(flags, f, indent=2, ensure_ascii=False)

print('Reporte generado:', report_path)
print('Flags:', flags_path)

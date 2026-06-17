import os
import glob
import json
from datetime import datetime
import pandas as pd
import numpy as np

BASE_BT_DIR = os.path.join("data", "backtesting")
ANALISIS_DIR = os.path.join(BASE_BT_DIR, "ANALISIS")

# Helpers -------------------------------------------------

def find_run_dirs(base=BASE_BT_DIR):
    if not os.path.isdir(base):
        return []
    dirs = []
    for d in os.listdir(base):
        full = os.path.join(base, d)
        if not os.path.isdir(full):
            continue
        if d.upper() == "ANALISIS":
            continue
        # Heurística: comienza con YYYY-MM-DD
        if len(d) >= 10 and d[4] == '-' and d[7] == '-':
            dirs.append(full)
    return sorted(dirs)


def latest_run_dir():
    dirs = find_run_dirs()
    return dirs[-1] if dirs else None


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return np.nan


def compute_drawdown(series: pd.Series):
    if series.empty:
        return 0.0
    c = series.cumsum()
    dd = (c.cummax() - c)
    return float(dd.max()) if not dd.empty else 0.0


def summarize_symbol(df_sym: pd.DataFrame, symbol: str):
    # Ensure needed cols
    if 'net_pnl' not in df_sym.columns:
        # fallback to pnl if net_pnl missing
        if 'pnl' in df_sym.columns:
            df_sym = df_sym.copy()
            df_sym['net_pnl'] = pd.to_numeric(df_sym['pnl'], errors='coerce').fillna(0.0)
        else:
            df_sym['net_pnl'] = 0.0

    net = pd.to_numeric(df_sym['net_pnl'], errors='coerce').fillna(0.0)
    gains = net[net > 0].sum()
    losses = net[net <= 0].sum()
    if losses < 0:
        pf_net = gains / abs(losses) if abs(losses) > 0 else (np.inf if gains > 0 else 0)
    else:
        pf_net = np.inf if gains > 0 else 0

    expectancy_net = float(net.mean()) if len(net) else 0.0
    max_dd_net = compute_drawdown(net)
    winrate_net = float((net > 0).mean() * 100.0) if len(net) else 0.0

    # r_multiple_net median
    if 'r_multiple_net' not in df_sym.columns:
        if 'risk_abs' in df_sym.columns:
            df_sym = df_sym.copy()
            risk_abs = pd.to_numeric(df_sym['risk_abs'], errors='coerce')
            df_sym['r_multiple_net'] = np.where((risk_abs.notna()) & (risk_abs != 0), net / risk_abs, np.nan)
        else:
            df_sym['r_multiple_net'] = np.nan
    r_multiple_median_net = float(pd.to_numeric(df_sym['r_multiple_net'], errors='coerce').median()) if 'r_multiple_net' in df_sym.columns else np.nan

    # metadata
    def mode_or(vals, fallback=""):
        try:
            vc = vals.value_counts(dropna=True)
            if not vc.empty:
                return vc.index[0]
        except Exception:
            pass
        return fallback

    cost_model_version = mode_or(df_sym.get('cost_model_version', pd.Series([], dtype=object)), "?")
    commit_short = mode_or(df_sym.get('commit_short', pd.Series([], dtype=object)), "?")

    return {
        'symbol': symbol,
        'trades': int(len(df_sym)),
        'pf_net': float(pf_net if np.isfinite(pf_net) else 0.0),
        'expectancy_net': expectancy_net,
        'max_dd_net': max_dd_net,
        'winrate_net': winrate_net,
        'r_multiple_median_net': r_multiple_median_net,
        'cost_model_version': cost_model_version,
        'commit_short': commit_short
    }


def main():
    run_dir = latest_run_dir()
    if not run_dir:
        print("No se encontró run reciente en data/backtesting")
        return
    print(f"Usando run más reciente: {run_dir}")

    # Buscar trades_enriched_* en subcarpetas de símbolos
    enriched_files = []
    for sym_dir in glob.glob(os.path.join(run_dir, '*')):
        if not os.path.isdir(sym_dir):
            continue
        sym = os.path.basename(sym_dir)
        # ignorar archivos comunes
        pattern = os.path.join(sym_dir, 'trades_enriched_*.*csv')
        # fallback pattern correcto (sin . antes de csv)
        pattern = os.path.join(sym_dir, 'trades_enriched_*.csv')
        for f in glob.glob(pattern):
            enriched_files.append((sym, f))

    if not enriched_files:
        print("No se encontraron trades_enriched_* en el run.")
        return

    frames = []
    for sym, fpath in enriched_files:
        try:
            df = pd.read_csv(fpath)
            if 'symbol' not in df.columns:
                df['symbol'] = sym
            frames.append(df)
        except Exception as e:
            print(f"Error leyendo {fpath}: {e}")

    if not frames:
        print("No se pudieron cargar DataFrames de trades enriquecidos.")
        return

    all_trades = pd.concat(frames, ignore_index=True)

    # Directorio de salida ANALISIS/<timestamp>/modelo_costos
    ts = datetime.utcnow().strftime('%Y-%m-%d_%H-%M')
    out_dir = os.path.join(ANALISIS_DIR, ts, 'modelo_costos')
    os.makedirs(out_dir, exist_ok=True)

    global_csv = os.path.join(out_dir, 'trades_enriched_global.csv')
    all_trades.to_csv(global_csv, index=False)
    try:
        all_trades.to_json(os.path.join(out_dir, 'trades_enriched_global.json'), orient='records', force_ascii=False)
    except Exception:
        pass

    # Métricas por símbolo
    metrics_rows = []
    for symbol, df_sym in all_trades.groupby('symbol'):
        metrics_rows.append(summarize_symbol(df_sym, symbol))

    # Fila GLOBAL agregada
    metrics_rows.append(summarize_symbol(all_trades, '__GLOBAL__'))

    metrics_df = pd.DataFrame(metrics_rows)
    metrics_path = os.path.join(out_dir, 'metrics_cost_adjusted.csv')
    metrics_df.to_csv(metrics_path, index=False)

    # Generar summary_cost_model.md
    try:
        lines = ["# Resumen Modelo de Costos\n", f"Run base: {os.path.basename(run_dir)}\n", f"Generado: {ts} UTC\n", "\n## Métricas Netas por Símbolo\n"]
        cols_show = ['symbol','trades','pf_net','expectancy_net','max_dd_net','winrate_net','r_multiple_median_net']
        table_header = '| ' + ' | '.join(cols_show) + ' |'\
            + "\n|" + "|".join(['---']*len(cols_show)) + '|'
        lines.append(table_header)
        for _, r in metrics_df.iterrows():
            row_vals = [r.get(c, '') for c in cols_show]
            lines.append('| ' + ' | '.join(f"{v}" for v in row_vals) + ' |')

        # Observaciones rápidas
        obs = []
        # Detectar símbolo candidato a descarte (PF_net < 1.5 o expectancy_net <=0)
        for _, r in metrics_df.iterrows():
            sym = r['symbol']
            if sym == '__GLOBAL__':
                continue
            if r['pf_net'] < 1.5 or r['expectancy_net'] <= 0:
                obs.append(f"Posible descarte: {sym} (PF_net={r['pf_net']:.2f}, expectancy_net={r['expectancy_net']:.4f})")
        # Detectar dispersión r_multiple_median_net baja
        medians = metrics_df[metrics_df['symbol'] != '__GLOBAL__']['r_multiple_median_net'].dropna()
        if not medians.empty and medians.median() < 0.6:
            obs.append("Advertencia: mediana global de r_multiple_net < 0.6")
        if not obs:
            obs.append("Sin alertas críticas iniciales bajo umbrales heurísticos.")

        lines.append("\n## Observaciones\n")
        for o in obs:
            lines.append(f"- {o}")

        lines.append("\n## Metadata\n")
        try:
            cmv = metrics_df.loc[metrics_df['symbol'] != '__GLOBAL__','cost_model_version'].dropna().unique()
            commit_vals = metrics_df.loc[metrics_df['symbol'] != '__GLOBAL__','commit_short'].dropna().unique()
            lines.append(f"- cost_model_version detectadas: {', '.join(cmv) if len(cmv)>0 else 'N/A'}")
            lines.append(f"- commits: {', '.join(commit_vals) if len(commit_vals)>0 else 'N/A'}")
        except Exception:
            pass

        with open(os.path.join(out_dir, 'summary_cost_model.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except Exception as e:
        print(f"No se pudo generar summary_cost_model.md: {e}")

    print("Artefactos generados:")
    print(" -", global_csv)
    print(" -", metrics_path)
    print(" -", os.path.join(out_dir, 'summary_cost_model.md'))

if __name__ == '__main__':
    main()

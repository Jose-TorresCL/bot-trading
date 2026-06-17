"""Compara desempeño entre Periodo A (temprano) y Periodo B (tardío) a partir de trades_enriched_global.csv.

Objetivo: identificar degradación de edge mostrando cambios en PF, expectancy, winrate, mediana de r_multiple_net y estructura de drawdown por símbolo y global.

Uso:
  python scripts/comparar_periodos.py \
      [--trades-file PATH_AL_CSV] \
      [--split-date YYYY-MM-DD] | [--first-n-trades N] \
      [--out-dir DIR]

Reglas de split (mutuamente excluyentes):
  - --split-date: exit_time < split_date => Periodo A, >= split_date => Periodo B
  - --first-n-trades: primeras N filas (ordenadas por exit_time) => A, resto => B
Si no se especifica nada, se usa la mediana de exit_time como split.

Salidas:
  - comparacion_periodos_resumen.csv : métricas por símbolo con sufijos A_, B_ y delta_
  - comparacion_periodos_global.md   : reporte markdown
  - comparacion_periodos_equity.png  : curvas acumuladas globales A y B (segmentadas) y por símbolo

Métricas:
  trades, net_pnl, pf_net, winrate, expectancy, median_r_net, max_dd, q10_r, q90_r, iqr_r.
  Deltas = B - A.

Limitaciones: no se aplican tests estadísticos avanzados (evitamos dependencias adicionales). Para una KS test futura se podría añadir scipy.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import datetime as dt
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Comparar Periodo A vs B en trades")
    p.add_argument("--trades-file", type=Path, default=None, help="Ruta al trades_enriched_global.csv")
    p.add_argument("--split-date", type=str, default=None, help="Fecha YYYY-MM-DD que separa periodos (exclusive para A)")
    p.add_argument("--first-n-trades", type=int, default=None, help="Número de primeras trades para Periodo A (resto Periodo B)")
    p.add_argument("--out-dir", type=Path, default=None, help="Directorio salida (por defecto el del trades file)")
    return p.parse_args()


def find_latest_trades_file() -> Path:
    base = Path("data/backtesting/ANALISIS")
    if not base.exists():
        raise FileNotFoundError("No existe data/backtesting/ANALISIS")
    candidates = []
    for d in base.iterdir():
        tf = d / "modelo_costos" / "trades_enriched_global.csv"
        if tf.exists():
            candidates.append((tf.stat().st_mtime, tf))
    if not candidates:
        raise FileNotFoundError("No se hallaron trades_enriched_global.csv")
    candidates.sort(reverse=True)
    return candidates[0][1]


def compute_metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "trades": 0,
            "net_pnl": 0.0,
            "pf_net": np.nan,
            "winrate": np.nan,
            "expectancy": np.nan,
            "median_r_net": np.nan,
            "max_dd": np.nan,
            "q10_r": np.nan,
            "q90_r": np.nan,
            "iqr_r": np.nan,
        }
    wins = df[df["net_pnl"] > 0]["net_pnl"].sum()
    losses = df[df["net_pnl"] < 0]["net_pnl"].sum()  # negativo
    pf = wins / abs(losses) if losses != 0 else np.inf if wins > 0 else 0.0
    trades = len(df)
    net_pnl = df["net_pnl"].sum()
    winrate = (df["net_pnl"] > 0).mean() * 100
    expectancy = net_pnl / trades if trades else np.nan
    median_r = df["r_multiple_net"].median() if "r_multiple_net" in df else np.nan

    # Max DD: equity cumsum sobre exit_time
    df_sorted = df.sort_values("exit_time")
    equity = df_sorted["net_pnl"].cumsum()
    roll_max = equity.cummax()
    dd = equity - roll_max
    max_dd = dd.min()
    r_vals = df["r_multiple_net"].dropna() if "r_multiple_net" in df else pd.Series(dtype=float)
    q10 = r_vals.quantile(0.10) if not r_vals.empty else np.nan
    q90 = r_vals.quantile(0.90) if not r_vals.empty else np.nan
    iqr = (r_vals.quantile(0.75) - r_vals.quantile(0.25)) if not r_vals.empty else np.nan
    return {
        "trades": trades,
        "net_pnl": net_pnl,
        "pf_net": pf,
        "winrate": winrate,
        "expectancy": expectancy,
        "median_r_net": median_r,
        "max_dd": max_dd,
        "q10_r": q10,
        "q90_r": q90,
        "iqr_r": iqr,
    }


def main():
    args = parse_args()
    if args.split_date and args.first_n_trades:
        print("Error: usar sólo uno de --split-date o --first-n-trades", file=sys.stderr)
        sys.exit(1)

    trades_file = args.trades_file or find_latest_trades_file()
    out_dir = args.out_dir or trades_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Usando trades: {trades_file}")
    df = pd.read_csv(trades_file, parse_dates=["exit_time"])  # leemos todas las columnas necesarias
    # Normalizar tz
    if hasattr(df["exit_time"].dt, "tz") and df["exit_time"].dt.tz is not None:
        df["exit_time"] = df["exit_time"].dt.tz_convert("UTC").dt.tz_localize(None)

    df = df.sort_values("exit_time").reset_index(drop=True)
    total_trades = len(df)
    if total_trades == 0:
        print("No hay trades en el archivo.")
        return

    # Determinar split
    if args.split_date:
        try:
            split_dt = dt.datetime.strptime(args.split_date, "%Y-%m-%d")
        except ValueError:
            print("Formato de --split-date inválido (YYYY-MM-DD)", file=sys.stderr)
            sys.exit(1)
        mask_a = df["exit_time"] < split_dt
        criterio = f"split_date={args.split_date}"
    elif args.first_n_trades:
        n = args.first_n_trades
        mask_a = pd.Series([True]*min(n, total_trades) + [False]*max(0, total_trades - n))
        criterio = f"first_n_trades={n}"
    else:
        # split por mediana de tiempo
        median_time = df["exit_time"].median()
        mask_a = df["exit_time"] < median_time
        criterio = f"median_time={median_time.date()}"

    df_a = df[mask_a].copy()
    df_b = df[~mask_a].copy()
    print(f"Periodo A trades: {len(df_a)} | Periodo B trades: {len(df_b)} | Criterio: {criterio}")
    if df_a.empty or df_b.empty:
        print("Advertencia: un periodo quedó vacío; ajustar criterio.")

    symbols = sorted(df["symbol"].unique()) if "symbol" in df.columns else ["__ALL__"]
    rows = []
    for sym in symbols:
        da = df_a[df_a["symbol"] == sym]
        db = df_b[df_b["symbol"] == sym]
        ma = compute_metrics(da)
        mb = compute_metrics(db)
        row = {"symbol": sym}
        for k, v in ma.items():
            row[f"A_{k}"] = v
        for k, v in mb.items():
            row[f"B_{k}"] = v
        # deltas B - A
        for k in ma.keys():
            row[f"delta_{k}"] = row[f"B_{k}"] - row[f"A_{k}"] if not (pd.isna(row[f"B_{k}"]) or pd.isna(row[f"A_{k}"])) else np.nan
        rows.append(row)

    # Global
    ma_g = compute_metrics(df_a)
    mb_g = compute_metrics(df_b)
    row_g = {"symbol": "__GLOBAL__"}
    for k, v in ma_g.items():
        row_g[f"A_{k}"] = v
    for k, v in mb_g.items():
        row_g[f"B_{k}"] = v
    for k in ma_g.keys():
        row_g[f"delta_{k}"] = row_g[f"B_{k}"] - row_g[f"A_{k}"] if not (pd.isna(row_g[f"B_{k}"]) or pd.isna(row_g[f"A_{k}"])) else np.nan
    rows.append(row_g)

    out_df = pd.DataFrame(rows)
    csv_path = out_dir / "comparacion_periodos_resumen.csv"
    out_df.to_csv(csv_path, index=False)
    print(f"Guardado: {csv_path}")

    # Reporte markdown
    md_lines = ["# Comparación Periodo A vs B", "", f"Criterio: {criterio}", ""]
    def fmt(x):
        if isinstance(x, (int, np.integer)):
            return str(x)
        if isinstance(x, float):
            return f"{x:0.4f}"
        return str(x)

    # Principales deterioros (orden por delta_expectancy ascendente)
    filt_syms = out_df[out_df.symbol != "__GLOBAL__"].copy()
    if not filt_syms.empty:
        det = filt_syms.sort_values("delta_expectancy")
        worst = det.head(min(5, len(det)))
        md_lines.append("## Principales deterioros (Expectancy)")
        for _, r in worst.iterrows():
            md_lines.append(f"- {r.symbol}: A_exp={fmt(r.A_expectancy)} -> B_exp={fmt(r.B_expectancy)} (delta={fmt(r.delta_expectancy)})")
        md_lines.append("")

    # Tabla compacta
    cols_show = ["symbol", "A_trades", "B_trades", "A_net_pnl", "B_net_pnl", "delta_net_pnl", "A_pf_net", "B_pf_net", "A_expectancy", "B_expectancy", "delta_expectancy", "A_winrate", "B_winrate", "delta_winrate", "A_median_r_net", "B_median_r_net", "delta_median_r_net", "A_max_dd", "B_max_dd", "delta_max_dd"]
    intersect = [c for c in cols_show if c in out_df.columns]
    md_lines.append("## Resumen Métricas")
    md_lines.append("")
    md_lines.append("| " + " | ".join(intersect) + " |")
    md_lines.append("|" + "|".join(["---"] * len(intersect)) + "|")
    for _, r in out_df[intersect].iterrows():
        md_lines.append("| " + " | ".join(fmt(r[c]) for c in intersect) + " |")

    md_path = out_dir / "comparacion_periodos_global.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Guardado: {md_path}")

    # Gráficas equity acumulado por símbolo comparando A y B (separadas por color)
    if "symbol" in df.columns:
        plt.style.use("seaborn-v0_8")
        syms = symbols
        n = len(syms)
        fig, axes = plt.subplots(n, 1, figsize=(10, 3 * n), sharex=True)
        if n == 1:
            axes = [axes]
        for ax, sym in zip(axes, syms):
            da = df_a[df_a.symbol == sym].sort_values("exit_time")
            db = df_b[df_b.symbol == sym].sort_values("exit_time")
            eq_a = da.net_pnl.cumsum()
            eq_b = db.net_pnl.cumsum()
            ax.plot(da.exit_time, eq_a, label=f"A ({len(da)})", color="tab:blue")
            ax.plot(db.exit_time, eq_b + (eq_a.iloc[-1] if not eq_a.empty else 0), label=f"B ({len(db)})", color="tab:red")
            if not eq_a.empty:
                ax.axhline(eq_a.max(), color="tab:blue", linestyle=":", alpha=0.3)
            ax.set_title(sym)
            ax.legend(fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()
        out_png = out_dir / "comparacion_periodos_equity.png"
        fig.savefig(out_png, dpi=120)
        print(f"Guardado: {out_png}")

    print("Done.")


if __name__ == "__main__":
    main()

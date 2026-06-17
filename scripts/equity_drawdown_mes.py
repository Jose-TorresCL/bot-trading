"""Genera curvas de equity y drawdown acumulado del último mes completo por símbolo.

Uso:
  python scripts/equity_drawdown_mes.py \
      [--trades-file DATA/BACKTESTING/ANALISIS/<run_id>/modelo_costos/trades_enriched_global.csv] \
      [--out-dir <ruta_salida>] \
      [--month YYYY-MM]  # opcional, si no se da toma el último mes calendario completo respecto a hoy

Salidas:
  - equity_drawdown_mes.csv : columnas [timestamp,symbol,equity,drawdown]
  - equity_drawdown_wide.csv: pivot ancho (equity_* y dd_*)
  - equity_drawdown_mes.png : figura con 2 subplots (equity y drawdown por símbolo)

Notas:
  - Usa la columna net_pnl para la contribución por trade (ya incluye costos).
  - Equity se calcula en los timestamps de cierre de cada trade (exit_time) ordenados.
  - Drawdown = equity - max_acumulado(equity) (valor <= 0).
  - Si faltan días al inicio del mes (p.ej. histórico incompleto primeros días), se reporta cobertura.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import sys
import pandas as pd
import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Equity y drawdown último mes completo por símbolo")
    p.add_argument("--trades-file", dest="trades_file", type=Path, default=None,
                   help="Ruta al trades_enriched_global.csv. Si se omite se toma el más reciente en data/backtesting/ANALISIS/*/modelo_costos/")
    p.add_argument("--out-dir", dest="out_dir", type=Path, default=None,
                   help="Directorio de salida. Default: mismo directorio del trades file.")
    p.add_argument("--month", dest="month", type=str, default=None,
                   help="Mes a analizar en formato YYYY-MM. Si se omite se usa el último mes completo respecto a hoy.")
    return p.parse_args()


def find_latest_trades_file() -> Path:
    base = Path("data/backtesting/ANALISIS")
    if not base.exists():
        raise FileNotFoundError("No existe data/backtesting/ANALISIS para autodetección")
    candidates: list[tuple[dt.datetime, Path]] = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        tf = d / "modelo_costos" / "trades_enriched_global.csv"
        if tf.exists():
            # usar mtime como proxy de recencia
            candidates.append((dt.datetime.fromtimestamp(tf.stat().st_mtime), tf))
    if not candidates:
        raise FileNotFoundError("No se encontró ningún trades_enriched_global.csv")
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def month_bounds(month_str: str | None) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    """Devuelve (inicio_mes, fin_mes_exclusivo, etiqueta). Si month_str es None toma último mes completo."""
    if month_str is None:
        today = dt.date.today()
        first_this = today.replace(day=1)
        # último mes completo = mes anterior
        last_month_end = first_this
        last_month_first = (first_this - dt.timedelta(days=1)).replace(day=1)
        label = last_month_first.strftime("%Y-%m")
        return (pd.Timestamp(last_month_first), pd.Timestamp(last_month_end), label)
    # mes específico
    try:
        first = dt.datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
    except ValueError:
        raise ValueError("Formato de --month debe ser YYYY-MM")
    # siguiente mes
    if first.month == 12:
        next_first = first.replace(year=first.year + 1, month=1)
    else:
        next_first = first.replace(month=first.month + 1)
    label = first.strftime("%Y-%m")
    return (pd.Timestamp(first), pd.Timestamp(next_first), label)


def compute_equity_drawdown(df: pd.DataFrame) -> pd.DataFrame:
    # Asume columnas: exit_time, net_pnl, symbol
    df = df.sort_values("exit_time").copy()
    df["equity"] = df["net_pnl"].cumsum()
    df["max_equity"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] - df["max_equity"]
    return df.drop(columns=["max_equity"])


def main():
    args = parse_args()
    trades_file = args.trades_file or find_latest_trades_file()
    if not trades_file.exists():
        raise FileNotFoundError(f"No existe el archivo de trades: {trades_file}")

    out_dir = args.out_dir or trades_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    month_start, month_end, month_label = month_bounds(args.month)

    print(f"Usando trades: {trades_file}")
    print(f"Mes analizado: {month_label} ({month_start.date()} -> {month_end.date() - dt.timedelta(days=1)})")

    usecols = ["exit_time", "net_pnl", "symbol"]
    # net_pnl puede no estar; fallback a pnl si no existe
    header = pd.read_csv(trades_file, nrows=0).columns.tolist()
    pnl_col = "net_pnl" if "net_pnl" in header else ("pnl" if "pnl" in header else None)
    if pnl_col is None:
        raise ValueError("No se encontró columna net_pnl ni pnl en el CSV")
    if pnl_col != "net_pnl":
        usecols = ["exit_time", pnl_col, "symbol"]

    df = pd.read_csv(trades_file, usecols=usecols, parse_dates=["exit_time"])\
            .rename(columns={pnl_col: "net_pnl"})

    # Normalizar zona horaria: si exit_time es tz-aware convertir a UTC y luego hacer tz_localize(None)
    # Si la serie tiene zona horaria (primer elemento tz-aware) la convertimos a naive UTC
    if hasattr(df["exit_time"].dt, "tz") and df["exit_time"].dt.tz is not None:
        df["exit_time"] = df["exit_time"].dt.tz_convert("UTC").dt.tz_localize(None)
    month_start = month_start.tz_localize(None) if hasattr(month_start, 'tz') and month_start.tz is not None else month_start
    month_end = month_end.tz_localize(None) if hasattr(month_end, 'tz') and month_end.tz is not None else month_end

    # Filtrar rango de mes completo
    mask = (df["exit_time"] >= month_start) & (df["exit_time"] < month_end)
    df_month = df.loc[mask].copy()
    if df_month.empty:
        print("No hay trades en el intervalo especificado.")
        sys.exit(0)

    coverage_days = df_month["exit_time"].dt.date.nunique()
    total_days = (month_end - month_start).days
    coverage_pct = coverage_days / total_days * 100
    print(f"Cobertura de días con al menos un trade: {coverage_days}/{total_days} ({coverage_pct:.1f}%)")

    results = []
    equity_wide = {}
    dd_wide = {}
    for symbol, g in df_month.groupby("symbol"):
        eg = compute_equity_drawdown(g[["exit_time", "net_pnl", "symbol"]])
        results.append(eg)
        equity_wide[f"equity_{symbol}"] = eg.set_index("exit_time")["equity"]
        dd_wide[f"dd_{symbol}"] = eg.set_index("exit_time")["drawdown"]

    combined = pd.concat(results, axis=0, ignore_index=True)
    combined.to_csv(out_dir / f"equity_drawdown_{month_label}.csv", index=False)

    # Construir pivots
    equity_wide_df = pd.concat(equity_wide, axis=1)
    dd_wide_df = pd.concat(dd_wide, axis=1)
    wide = pd.concat([equity_wide_df, dd_wide_df], axis=1)
    wide.sort_index().to_csv(out_dir / f"equity_drawdown_wide_{month_label}.csv")

    # Figura
    plt.style.use("seaborn-v0_8")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    for col in equity_wide_df.columns:
        ax1.plot(equity_wide_df.index, equity_wide_df[col], label=col.replace("equity_", ""))
    ax1.set_title(f"Equity Curve por Símbolo - Mes {month_label}")
    ax1.set_ylabel("Equity (net PnL acumulado)")
    ax1.axhline(0, color="black", linewidth=0.8)
    ax1.legend(ncol=4, fontsize=8)

    for col in dd_wide_df.columns:
        ax2.plot(dd_wide_df.index, dd_wide_df[col], label=col.replace("dd_", ""))
    ax2.set_title("Drawdown Acumulado")
    ax2.set_ylabel("Drawdown")
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.legend(ncol=4, fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    out_png = out_dir / f"equity_drawdown_{month_label}.png"
    fig.savefig(out_png, dpi=120)
    print(f"Guardado: {out_png}")
    print(f"Guardado: {out_dir / f'equity_drawdown_{month_label}.csv'}")
    print(f"Guardado: {out_dir / f'equity_drawdown_wide_{month_label}.csv'}")

    # Resumen final por símbolo
    summary_rows = []
    for symbol, g in combined.groupby("symbol"):
        final_eq = g["equity"].iloc[-1]
        max_dd = g["drawdown"].min()
        recovery = final_eq / -max_dd if max_dd < 0 else float("inf")
        summary_rows.append({"symbol": symbol, "final_equity": final_eq, "max_drawdown": max_dd, "recovery_ratio": recovery})
    summary_df = pd.DataFrame(summary_rows).sort_values("final_equity", ascending=False)
    print("\nResumen:")
    print(summary_df.to_string(index=False, float_format=lambda x: f"{x:0.4f}"))
    summary_df.to_csv(out_dir / f"equity_drawdown_summary_{month_label}.csv", index=False)
    print(f"Guardado: {out_dir / f'equity_drawdown_summary_{month_label}.csv'}")


if __name__ == "__main__":
    main()

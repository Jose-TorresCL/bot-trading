# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
from src.reporting.metrics import profit_factor as _pf_helper

THRESH_SKEW = 2.0
MIN_TRADES = 30

def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")
    return pd.read_csv(path)

def pick_pnl_col(df: pd.DataFrame) -> pd.Series:
    for col in ["net_pnl", "ganancia", "pnl", "pnl_net"]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            return s
    return pd.Series(np.zeros(len(df)), index=df.index, dtype=float)

def profit_factor_from_pnl(pnl) -> float:
    """Delegar en helper centralizado para evitar deriva de definiciones."""
    try:
        s = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    except Exception:
        s = pd.Series([], dtype=float)
    return float(_pf_helper(s)) if len(s) else 0.0

def _to_series(x, index) -> pd.Series:
    """Asegura una Series alineada al índice dado, convirtiendo escalares/None a Series.
    Útil para columnas opcionales al normalizar tipos y satisfacer chequeos estáticos.
    """
    if isinstance(x, pd.Series):
        return pd.to_numeric(x, errors="coerce")
    # expandir escalar/None a serie del tamaño del dataframe
    return pd.Series([x] * len(index), index=index, dtype=float)

def find_col(df: pd.DataFrame, names: list[str], default=None, required=False):
    for n in names:
        if n in df.columns:
            return df[n]
    if required:
        raise ValueError(f"Faltan columnas en grid_results.csv: {names}")
    return default

def df_to_md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_string(index=False)

def autodetect_latest_trades(base_dir: Path) -> tuple[Path|None, Path|None]:
    """Devuelve (ruta_trades, run_dir) del último run bajo ANALISIS/<timestamp>/modelo_costos."""
    analisis_dir = base_dir / "data" / "backtesting" / "ANALISIS"
    if not analisis_dir.exists():
        return (None, None)
    candidates = []
    for d in analisis_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            dt = datetime.strptime(d.name, "%Y-%m-%d_%H-%M")
            candidates.append((dt, d))
        except Exception:
            continue
    if not candidates:
        return (None, None)
    _, latest_dir = sorted(candidates, key=lambda x: x[0])[-1]
    trades_path = latest_dir / "modelo_costos" / "trades_enriched_global.csv"
    return (trades_path if trades_path.exists() else None, latest_dir)

def audit_grid(grid_path: Path, summary_path: Path|None, trades_path: Path|None, out_path: Path):
    df = read_csv_safe(grid_path)

    param_cols = [c for c in df.columns if c in ("RSI_BUY","RSI_SELL","SL_MULT","TP_MULT","ATR_MULT","ADX_LIMIT","MIN_VOTES")]

    pf_s = find_col(df, ["pf_net", "PF_net", "profit_factor", "pf"], default=np.nan)
    exp_s = find_col(df, ["expectancy_net", "expectancy", "exp"], default=np.nan)
    skew_s = find_col(df, ["skew_r_multiple", "skew", "skew_r"], default=np.nan)
    rec_s = find_col(df, ["recovery_ratio", "recovery"], default=np.nan)
    trades_s = find_col(df, ["trades", "num_trades", "n_trades"], default=np.nan, required=True)

    few_trades_s = find_col(df, ["few_trades"], default=None)
    skew_extreme_s = find_col(df, ["skew_extreme"], default=None)

    table_df = pd.DataFrame({
        **({c: df[c] for c in param_cols}),
        "pf_net": _to_series(pf_s, df.index),
        "expectancy": _to_series(exp_s, df.index),
        "skew_r_multiple": _to_series(skew_s, df.index),
        "recovery_ratio": _to_series(rec_s, df.index),
        "trades": _to_series(trades_s, df.index)
    })

    if few_trades_s is None:
        table_df["few_trades"] = table_df["trades"] < MIN_TRADES
    else:
        table_df["few_trades"] = few_trades_s.astype(bool)

    if skew_extreme_s is None:
        table_df["skew_extreme"] = table_df["skew_r_multiple"].abs() > THRESH_SKEW
    else:
        table_df["skew_extreme"] = skew_extreme_s.astype(bool)

    table_df = table_df.sort_values(["expectancy","pf_net"], ascending=[False, False]).reset_index(drop=True)

    table_df["Eligible"] = (
        (table_df["expectancy"] > 0)
        & (table_df["pf_net"] > 1.0)
        & (table_df["trades"] >= MIN_TRADES)
        & (~table_df["skew_extreme"])
        & (~table_df["few_trades"])
    )

    seg_md = "No se encontró segmentación por market_regime (columna ausente)."
    if trades_path and trades_path.exists():
        tdf = read_csv_safe(trades_path)
        if "market_regime" in tdf.columns:
            pnl = pick_pnl_col(tdf)
            tdf = tdf.copy()
            tdf["__pnl__"] = pnl
            seg = tdf.groupby("market_regime").agg(
                trades=("market_regime","count"),
                pnl_net=("__pnl__","sum")
            ).reset_index()
            # PF por régimen
            pf_vals = []
            for regime in seg["market_regime"]:
                sub_series = pd.to_numeric(tdf.loc[tdf["market_regime"]==regime, "__pnl__"], errors="coerce")
                pf_vals.append(profit_factor_from_pnl(sub_series))
            seg["pf_net"] = pf_vals
            total = seg["pnl_net"].sum() if seg["pnl_net"].sum()!=0 else 1.0
            seg["pnl_share_pct"] = 100 * seg["pnl_net"] / total
            seg_md = df_to_md(seg)
        else:
            seg_md = "El archivo de trades no contiene la columna 'market_regime'."

    alerts = []
    for idx_i, (_, r) in enumerate(table_df.iterrows(), start=1):
        desc = []
        if r["few_trades"]:
            desc.append("few_trades")
        if r["skew_extreme"]:
            desc.append("skew_extreme")
        if (pd.isna(r["expectancy"]) or r["expectancy"] <= 0) or (pd.isna(r["pf_net"]) or r["pf_net"] <= 1.0):
            desc.append("unprofitable")
        params_txt = ", ".join(f"{k}={r[k]}" for k in param_cols)
    alerts.append(f"Setup #{idx_i+1} ({params_txt}): " + (", ".join(desc) if desc else "OK"))

    n_eligible = int(table_df["Eligible"].sum())
    rec = "- Recomendación: descartar todos por ahora." if n_eligible == 0 else f"- Recomendación: mantener {n_eligible} setup(s) elegible(s) para validación extendida; descartar el resto."

    lines = []
    lines.append("# Auditoría de Grid (quick)")
    lines.append("")
    if summary_path and summary_path.exists():
        try:
            md_prev = summary_path.read_text(encoding="utf-8")
            lines.append("## Resumen previo (grid_summary.md)")
            lines.append("")
            lines.append(md_prev.strip())
            lines.append("\n---\n")
        except Exception:
            pass

    lines.append("## Tabla de métricas por setup")
    lines.append("")
    printable = table_df.copy()
    printable = printable[param_cols + ["pf_net","expectancy","skew_r_multiple","recovery_ratio","trades","few_trades","skew_extreme","Eligible"]]
    lines.append(df_to_md(printable))
    lines.append("")
    lines.append("## Segmentación por market_regime (global)")
    lines.append("")
    lines.append(seg_md)
    lines.append("")
    lines.append("## Alertas por setup")
    lines.append("")
    for a in alerts:
        lines.append(f"- {a}")
    lines.append("")
    lines.append("## Recomendación")
    lines.append("")
    lines.append(rec)
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")

def main():
    base_dir = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", type=str, default=str(Path.cwd() / "grid_results.csv"))
    ap.add_argument("--summary", type=str, default=str(Path.cwd() / "grid_summary.md"))
    ap.add_argument("--trades", type=str, default="")  # vacío => autodetect
    ap.add_argument("--out", type=str, default="")     # vacío => autodetect junto al run
    args = ap.parse_args()

    trades_path = Path(args.trades) if args.trades else None
    out_path = Path(args.out) if args.out else None

    if not trades_path or not trades_path.exists():
        auto_trades, latest_dir = autodetect_latest_trades(base_dir)
        if auto_trades is None:
            raise FileNotFoundError("No se pudo autodetectar el último run ni encontrar trades_enriched_global.csv. Pasa --trades manualmente.")
        trades_path = auto_trades
        if latest_dir is None:
            raise FileNotFoundError("No se pudo determinar la carpeta del último run para ubicar el reporte.")
        if out_path is None or str(out_path) == "":
            out_path = latest_dir / "modelo_costos" / "audit_grid_survivors.md"

    if out_path is None or str(out_path) == "":
        out_path = Path.cwd() / "audit_grid_survivors.md"

    audit_grid(Path(args.grid), Path(args.summary), trades_path, out_path)
    print(f"[OK] Generado: {out_path}")

if __name__ == "__main__":
    main()
"""
prepare_data.py
----------------
Filtra `historial_trading_maestro.csv` por los últimos `min_days` por símbolo,
opcionalmente por una lista de símbolos, y guarda:
 - historial_trading_maestro_filtrado_{suffix}.csv  (timestamps ISO UTC)
 - historial_trading_limpio_filtrado_{suffix}.csv    (timestamp en ms int)
 - summary_{suffix}.json

Uso: python src/pipeline/prepare_data.py --min_days 30 --min_rows 2000 --symbols BTCUSDT,ETHUSDT
"""
from pathlib import Path
import argparse
import json
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "historiales" / "historial_trading_maestro.csv"
OUT_DIR = ROOT / "data" / "historiales"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main(min_days: int = 30, min_rows: int = 2000, symbols: list | None = None, suffix: str = "filtered"):
    if not IN_PATH.exists():
        raise FileNotFoundError(f"Maestro no encontrado en {IN_PATH}")

    df = pd.read_csv(IN_PATH, parse_dates=["timestamp"], infer_datetime_format=True)
    # asegurar tz-aware UTC
    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    except Exception:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    stats = {}
    selected_frames = []
    symbols_list = sorted(df["symbol"].dropna().unique().tolist())
    if symbols:
        # filtrar por símbolos pedidos y verificar existencia
        req = [s.strip().upper() for s in symbols]
        symbols_list = [s for s in req if s in df["symbol"].unique()]

    for sym in symbols_list:
        dsi = df[df["symbol"] == sym].sort_values("timestamp")
        if dsi.empty:
            continue
        first = dsi["timestamp"].min()
        last = dsi["timestamp"].max()
        span_days = (last - first).days
        rows = len(dsi)
        # seleccionar ventana: últimos min_days
        cutoff = last - pd.Timedelta(days=int(min_days))
        dsel = dsi[dsi["timestamp"] >= cutoff].copy()
        sel_rows = len(dsel)
        keep = True
        if sel_rows < int(min_rows):
            keep = False

        stats[sym] = {
            "first": str(first),
            "last": str(last),
            "span_days": int(span_days),
            "rows_total": int(rows),
            "rows_selected": int(sel_rows),
            "keep": bool(keep)
        }
        if keep:
            selected_frames.append(dsel)

    # Concatenate selected symbols
    if selected_frames:
        df_sel = pd.concat(selected_frames, ignore_index=True).drop_duplicates(subset=["symbol", "timestamp"]).sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    else:
        df_sel = pd.DataFrame(columns=df.columns)

    # Save maestro filtrado (ISO UTC)
    out_maestro = OUT_DIR / f"historial_trading_maestro_filtrado_{suffix}.csv"
    df_out = df_sel.copy()
    if not df_out.empty:
        df_out["timestamp"] = df_out["timestamp"].dt.tz_convert("UTC")
    df_out.to_csv(out_maestro, index=False)

    # Save limpio (timestamp ms)
    out_limpio = OUT_DIR / f"historial_trading_limpio_filtrado_{suffix}.csv"
    df_l = df_sel.copy()
    if not df_l.empty:
        # timestamp to ms int
        df_l["timestamp"] = (df_l["timestamp"].astype("int64") // 10**6).astype("int64")
    df_l.to_csv(out_limpio, index=False)

    # Save JSON summary
    out_json = OUT_DIR / f"summary_{suffix}.json"
    with open(out_json, "w", encoding="utf8") as fh:
        json.dump({"params": {"min_days": min_days, "min_rows": min_rows, "symbols": symbols}, "stats": stats}, fh, indent=2, ensure_ascii=False)

    return {
        "out_maestro": str(out_maestro),
        "out_limpio": str(out_limpio),
        "out_json": str(out_json),
        "stats": stats
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--min_days", type=int, default=30, help="Número de días a mantener hacia atrás")
    p.add_argument("--min_rows", type=int, default=2000, help="Mínimo de filas en la ventana para aceptar el símbolo")
    p.add_argument("--symbols", type=str, default=None, help="Lista CSV de símbolos a mantener (ej: BTCUSDT,ETHUSDT)")
    p.add_argument("--suffix", type=str, default="15m_30d", help="Sufijo para archivos de salida")
    args = p.parse_args()
    syms = args.symbols.split(",") if args.symbols else None
    res = main(min_days=args.min_days, min_rows=args.min_rows, symbols=syms, suffix=args.suffix)
    print("Filtrado completado. Archivos:")
    print(" -", res["out_maestro"])
    print(" -", res["out_limpio"])
    print(" -", res["out_json"])
    print("Stats:")
    for k, v in res["stats"].items():
        print(f"{k}: total={v['rows_total']} sel={v['rows_selected']} days={v['span_days']} keep={v['keep']}")

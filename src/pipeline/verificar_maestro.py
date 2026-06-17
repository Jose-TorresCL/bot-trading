"""
verificar_maestro.py
- Lee archivos historial_*.csv en src/data/historicos
- Normaliza timestamps (ISO, s, ms, us, ns)
- Concatena, elimina duplicados por symbol+timestamp
- Guarda:
    * src/data/historiales/historial_trading_maestro.csv  (timestamp ISO UTC)
    * src/data/historiales/historial_trading_limpio.csv  (timestamp en ms int)
- Muestra resumen por símbolo
"""
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import time
import logging

logger = logging.getLogger(__name__)

# intentar importar la transformación central si existe
try:
    from src.pipeline.transformacion_datos import transformar_datos
except Exception:
    try:
        from pipeline.transformacion_datos import transformar_datos
    except Exception:
        transformar_datos = None

ROOT = Path(__file__).resolve().parents[1]  # src
HIST_DIR = ROOT / "data" / "historicos"
OUT_DIR = ROOT / "data" / "historiales"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_DATE = pd.Timestamp("2017-01-01", tz="UTC")
MAX_DATE = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)

def parse_timestamp_to_datetime(val):
    """Intenta convertir val a pd.Timestamp UTC válido dentro de rango plausible."""
    if pd.isna(val):
        return pd.NaT
    s = str(val).strip()
    # 1) ISO / readable
    dt = pd.to_datetime(s, utc=True, errors="coerce")
    if pd.notna(dt) and MIN_DATE <= dt <= MAX_DATE:
        return dt
    # 2) numeric heuristics
    try:
        v = float(s)
    except Exception:
        return pd.NaT
    # Try interpreting as ns/us/ms/s by magnitude
    try_units = [
        ("ns", 1),
        ("us", 10**3),
        ("ms", 10**6),
        ("s", 10**9),
    ]
    for unit, _ in try_units:
        try:
            dt_try = pd.to_datetime(int(v), unit=unit, utc=True, errors="coerce")
            if pd.notna(dt_try) and MIN_DATE <= dt_try <= MAX_DATE:
                return dt_try
        except Exception:
            continue
    # 3) progressively scale down by 1000 and try seconds
    for _ in range(4):
        try:
            v = v / 1000.0
            dt_try = pd.to_datetime(int(v), unit="s", utc=True, errors="coerce")
            if pd.notna(dt_try) and MIN_DATE <= dt_try <= MAX_DATE:
                return dt_try
        except Exception:
            continue
    return pd.NaT

def normalize_df(df: pd.DataFrame, symbol_hint: str | None = None) -> pd.DataFrame:
    if "symbol" not in df.columns and symbol_hint:
        df["symbol"] = symbol_hint
    if "timestamp" not in df.columns:
        return pd.DataFrame()  # nothing to do
    # preserve raw then parse
    df = df.copy()
    df["timestamp_raw"] = df["timestamp"].astype(str)
    df["timestamp_dt"] = df["timestamp_raw"].apply(parse_timestamp_to_datetime)
    df = df.dropna(subset=["timestamp_dt"]).reset_index(drop=True)
    # ensure OHLCV numeric
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        else:
            df[c] = 0.0
    # standardize timestamp column as timezone-aware UTC
    df["timestamp"] = pd.to_datetime(df["timestamp_dt"], utc=True)
    keep_cols = ["timestamp", "open", "high", "low", "close", "volume", "symbol"]
    extras = [c for c in df.columns if c not in keep_cols and c not in ("timestamp_raw", "timestamp_dt")]
    return df[keep_cols + extras].reset_index(drop=True)


def validar_y_preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica transformaciones y validaciones similares a las de validacion_datos.py
    - intenta usar transformar_datos si está disponible
    - asegura columnas price, convierte numéricos, reemplaza inf, rellena NaN con media o 0
    """
    if df is None or df.empty:
        return pd.DataFrame()

    # aplicar transformación central si existe
    if callable(transformar_datos):
        try:
            df = transformar_datos(df)
        except Exception:
            pass

    # asegurar price
    if "price" not in df.columns and "close" in df.columns:
        df["price"] = df["close"]

    # eliminar filas sin close o timestamp
    subset_to_check = [c for c in ("close", "timestamp") if c in df.columns]
    if subset_to_check:
        df = df.dropna(subset=subset_to_check, how="any")

    # coerción numérica y limpieza
    required_fields = ["open", "high", "low", "close", "volume", "price"]
    for field in required_fields:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors="coerce")
            df[field] = df[field].replace([np.inf, -np.inf], np.nan)
            mean_value = df[field].mean(skipna=True)
            fill_value = 0.0 if pd.isna(mean_value) else float(mean_value)
            df[field] = df[field].fillna(fill_value)

    # asegurar tipos flotantes
    for col in df.select_dtypes(include=["int64", "float64"]).columns:
        try:
            df[col] = df[col].astype(float)
        except Exception:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df.reset_index(drop=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", type=str, default=None, help="Lista CSV de símbolos a procesar (ej: BTCUSDT,ETHUSDT)")
    p.add_argument("--min_days", type=int, default=30, help="Recortar cada símbolo a los últimos N días")
    args = p.parse_args()

    requested = None
    if args.symbols:
        requested = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    # list only explicit historial_{SYMBOL}.csv files
    files = []
    for sym_file in sorted(HIST_DIR.glob("historial_*.csv")):
        name = sym_file.name
        # exclude backup files that include '.bak' in name
        if ".bak" in name:
            continue
        # if symbols requested, only include those matching exactly
        if requested:
            sym = name.replace("historial_", "").replace(".csv", "").upper()
            if sym in requested:
                files.append(sym_file)
        else:
            files.append(sym_file)
    if not files:
        print("No se encontraron archivos en", HIST_DIR)
        return
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str)
        except Exception:
            df = pd.read_csv(f, low_memory=False)
        symbol_hint = None
        name = f.name.lower()
        if name.startswith("historial_") and name.endswith(".csv"):
            symbol_hint = f.name.replace("historial_", "").replace(".csv", "").upper()
        df_norm = normalize_df(df, symbol_hint=symbol_hint)
        if df_norm.empty:
            continue
        # aplicar validación/transformación adicional
        df_norm = validar_y_preparar(df_norm)
        if df_norm.empty:
            continue
        # recortar a últimos N días
        if args.min_days and "timestamp" in df_norm.columns:
            last = df_norm["timestamp"].max()
            cutoff = last - pd.Timedelta(days=int(args.min_days))
            df_norm = df_norm[df_norm["timestamp"] >= cutoff].reset_index(drop=True)
        if not df_norm.empty:
            dfs.append(df_norm)
    if not dfs:
        print("No se generó ningún DataFrame válido. Verifica los CSV en", HIST_DIR)
        return
    df_all = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    # dedupe and sort
    df_all = df_all.drop_duplicates(subset=["symbol", "timestamp"]).sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    # Save maestro (ISO UTC)
    maestro_path = OUT_DIR / "historial_trading_maestro.csv"
    df_maestro = df_all.copy()
    # timestamp as ISO string (UTC)
    df_maestro["timestamp"] = df_maestro["timestamp"].dt.tz_convert("UTC")
    df_maestro.to_csv(maestro_path, index=False)
    # Save limpio (timestamp in ms)
    limpio_path = OUT_DIR / "historial_trading_limpio.csv"
    df_limpio = df_all.copy()
    # evitar FutureWarning: usar astype en lugar de view
    df_limpio["timestamp"] = (df_limpio["timestamp"].astype("int64") // 10**6).astype("int64")
    df_limpio.to_csv(limpio_path, index=False)
    # Summary
    print("Maestro regenerado:")
    print(" -", maestro_path)
    print(" -", limpio_path)
    print("Símbolos:", df_all["symbol"].dropna().unique().tolist())
    print("Registros totales:", len(df_all))
    # per-symbol ranges
    for sym in df_all["symbol"].dropna().unique():
        dsi = df_all[df_all["symbol"] == sym]
        first = dsi["timestamp"].min()
        last = dsi["timestamp"].max()
        duration = last - first
        print(f"{sym}: {first} --> {last}  (Duración: {duration})")

if __name__ == "__main__":
    main()
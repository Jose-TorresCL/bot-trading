"""
fusionar_historicos.py (mejorado)
- Lee data/historicos/historial_*.csv
- Normaliza timestamps y columnas
- Detecta/descarta filas con timestamp inválido
- Concatena y deduplica (por symbol+timestamp), guarda maestro (ISO UTC) y limpio (timestamp ms)
- Reporte por símbolo
"""
from pathlib import Path
import pandas as pd
import logging
import sys
import re
from typing import Optional

LOG = logging.getLogger("fusionar_historicos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

ROOT = Path(__file__).resolve().parents[1]  # proyecto/src nivel
DATA_HIST = ROOT / "data" / "historicos"
OUT_DIR = ROOT / "src" / "data" / "historiales"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_DATE = pd.Timestamp("2017-01-01", tz="UTC")
MAX_DATE = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2)

STD_COLS = ["timestamp", "open", "high", "low", "close", "volume", "symbol"]


def parse_timestamp(val) -> Optional[pd.Timestamp]:
    """Intentar parsear val a pd.Timestamp UTC dentro del rango plausible."""
    if val is None:
        return pd.NaT
    s = str(val).strip()
    # ISO / natural
    dt = pd.to_datetime(s, utc=True, errors="coerce")
    if pd.notna(dt) and MIN_DATE <= dt <= MAX_DATE:
        return dt
    # eliminar comas/espacios
    s_num = re.sub(r"[^\d\-\.]", "", s)
    if s_num == "":
        return pd.NaT
    try:
        v = float(s_num)
    except Exception:
        return pd.NaT

    # heurística por magnitud
    try:
        if v > 10**14:  # nanoseconds
            dt = pd.to_datetime(int(v), unit="ns", utc=True, errors="coerce")
        elif v > 10**12:  # milliseconds
            dt = pd.to_datetime(int(v), unit="ms", utc=True, errors="coerce")
        elif v > 10**9:  # seconds
            dt = pd.to_datetime(int(v), unit="s", utc=True, errors="coerce")
        else:
            # probar escalando hacia arriba (s -> ms -> us)
            dt = pd.to_datetime(int(v), unit="s", utc=True, errors="coerce")
        if pd.notna(dt) and MIN_DATE <= dt <= MAX_DATE:
            return dt
    except Exception:
        pass

    # fallback: probar escalando por /1000 repetido (ns->us->ms->s)
    for _ in range(4):
        try:
            v = v / 1000.0
            dt = pd.to_datetime(int(v), unit="s", utc=True, errors="coerce")
            if pd.notna(dt) and MIN_DATE <= dt <= MAX_DATE:
                return dt
        except Exception:
            continue
    return pd.NaT


def read_csv_robust(path: Path) -> pd.DataFrame:
    """Leer CSV saltando primera línea si empieza con '//' o contiene filepath marker."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    # detectar y quitar encabezados no-CSV
    lines = text.splitlines()
    start = 0
    while start < len(lines) and (lines[start].strip().startswith("//") or lines[start].lower().startswith("filepath:")):
        start += 1
    cleaned = "\n".join(lines[start:])
    from io import StringIO
    try:
        df = pd.read_csv(StringIO(cleaned), dtype=str)
    except Exception as e:
        LOG.warning("pd.read_csv fallo en %s: %s - intento con low_memory=False", path.name, e)
        df = pd.read_csv(StringIO(cleaned), dtype=str, low_memory=False)
    return df


def normalize_df(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    """Normalizar columnas y timestamps; añadir columna 'source' con filename."""
    df = df.copy()
    # inferir symbol desde filename si no existe
    if "symbol" not in df.columns:
        m = re.search(r"historial_([A-Za-z0-9]+)\.csv", filename, re.IGNORECASE)
        if m:
            df["symbol"] = m.group(1).upper()
    # conservar solo columnas estándar + extras
    cols_keep = [c for c in df.columns if c in STD_COLS] + [c for c in df.columns if c not in STD_COLS]
    df = df[cols_keep]
    # normalizar timestamp raw
    if "timestamp" not in df.columns:
        LOG.warning("%s no contiene columna 'timestamp', se descartará", filename)
        return pd.DataFrame(columns=STD_COLS + ["source"])
    df["timestamp_raw"] = df["timestamp"].astype(str)
    # aplicar parser escalar (map para evitar advertencias de tipos)
    df["timestamp_dt"] = df["timestamp_raw"].map(parse_timestamp)
    # drop invalid timestamps
    before = len(df)
    df = df.dropna(subset=["timestamp_dt"]).reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        LOG.info("%s: descartadas %d filas sin timestamp válido", filename, dropped)
    # convertir ohlcv a num
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = pd.NA
    # timestamp como tz-aware UTC
    df["timestamp"] = pd.to_datetime(df["timestamp_dt"], utc=True)
    df["symbol"] = df["symbol"].astype(str).str.upper()
    df["source"] = filename
    # keep standard order
    extras = [c for c in df.columns if c not in ("timestamp", "open", "high", "low", "close", "volume", "symbol", "timestamp_raw", "timestamp_dt", "source")]
    return df[["timestamp", "open", "high", "low", "close", "volume", "symbol", "source"] + extras].reset_index(drop=True)


def main():
    files = sorted([p for p in DATA_HIST.glob("historial_*.csv")])
    if not files:
        LOG.error("No se encontraron archivos en %s", DATA_HIST)
        sys.exit(1)

    dfs = []
    for f in files:
        try:
            df0 = read_csv_robust(f)
            dfn = normalize_df(df0, f.name)
            if not dfn.empty:
                dfs.append(dfn)
                LOG.info("Leído %s -> %d filas válidas", f.name, len(dfn))
            else:
                LOG.info("No filas válidas en %s", f.name)
        except Exception as e:
            LOG.exception("Error procesando %s: %s", f.name, e)

    if not dfs:
        LOG.error("No se generó ningún DataFrame válido")
        sys.exit(1)

    # concatenar y deduplicar: preferir filas de archivos procesados más tarde -> keep='last'
    df_all = pd.concat(dfs, ignore_index=True)
    # eliminar duplicados por symbol+timestamp (mantener last para priorizar archivos posteriores en la lista)
    df_all = df_all.sort_values(["symbol", "timestamp", "source"]).drop_duplicates(subset=["symbol", "timestamp"], keep="last").reset_index(drop=True)
    df_all = df_all.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    # Guardar maestro (ISO UTC)
    maestro_path = OUT_DIR / "historial_trading_maestro.csv"
    df_maestro = df_all.copy()
    # timestamp ISO (timezone-aware). to_csv will format datetimes reasonably.
    df_maestro.to_csv(maestro_path, index=False)
    LOG.info("Maestro guardado: %s (%d filas)", maestro_path, len(df_maestro))

    # Guardar limpio: timestamp en ms integer
    limpio_path = OUT_DIR / "historial_trading_limpio.csv"
    df_limpio = df_all.copy()
    # convertir timestamp a int ms de forma segura según si es tz-aware o no
    from pandas.api.types import is_datetime64tz_dtype
    ts = df_limpio["timestamp"]
    try:
        if is_datetime64tz_dtype(ts.dtype):
            # convertir a UTC y quitar tz para poder pasar a int64
            ts_naive = ts.dt.tz_convert("UTC").dt.tz_localize(None)
        else:
            ts_naive = pd.to_datetime(ts, utc=False)
        df_limpio["timestamp"] = (ts_naive.astype("int64") // 10**6).astype("int64")
    except Exception:
        # fallback seguro por elemento (más lento) si hay valores raros
        df_limpio["timestamp"] = df_limpio["timestamp"].apply(
            lambda x: int(pd.to_datetime(x, utc=True).value // 10**6) if pd.notna(x) else pd.NA
        ).astype("Int64")
    # conservar solo columnas necesarias para backtesting
    cols_out = ["timestamp", "open", "high", "low", "close", "volume", "symbol"]
    for c in cols_out:
        if c not in df_limpio.columns:
            df_limpio[c] = pd.NA
    df_limpio[cols_out].to_csv(limpio_path, index=False)
    LOG.info("Limpio guardado: %s (%d filas)", limpio_path, len(df_limpio))

    # Informe rápido por símbolo
    report = []
    for sym in df_all["symbol"].unique():
        dsi = df_all[df_all["symbol"] == sym]
        start = dsi["timestamp"].min()
        end = dsi["timestamp"].max()
        rows = len(dsi)
        # estimar huecos para frecuencia 1 minuto (si hay suficientes datos)
        missing = None
        try:
            if rows > 10:
                idx = pd.DatetimeIndex(dsi["timestamp"].sort_values())
                freq = "1T"
                expected = pd.date_range(idx.min(), idx.max(), freq=freq)
                missing = len(expected.difference(idx))
        except Exception:
            missing = None
        report.append((sym, rows, start, end, missing))
    LOG.info("Resumen por símbolo:")
    for sym, rows, start, end, missing in report:
        LOG.info(" - %s: %d filas  %s --> %s   missing(1T)=%s", sym, rows, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"), missing if missing is not None else 0)
    LOG.info("✅ Proceso completado exitosamente.")


if __name__ == "__main__":
    main()
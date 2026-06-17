"""
carga_datos.py
--------------
Funciones para cargar y guardar datos históricos de trading en formato CSV.
Incluye validación de columnas y manejo de rutas relativas.
"""

import os
import logging
import pandas as pd
from datetime import UTC
from pandas import DateOffset

logger = logging.getLogger("carga_datos")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(h)
logger.propagate = False
logger.setLevel(logging.INFO)

CANDIDATE_TS_COLS = ["timestamp", "open_time", "date", "datetime", "time", "fecha"]

def _detect_timestamp_col(df: pd.DataFrame) -> str | None:
    for c in CANDIDATE_TS_COLS:
        if c in df.columns:
            return c
    return None

def _parse_timestamp(series: pd.Series):
    # intenta numérico (ms/s) luego parse string
    s = series.copy()
    if pd.api.types.is_numeric_dtype(s):
        s = pd.to_datetime(
            s.astype("int64"),
            unit="ms" if s.max() > 1e12 else "s",
            errors="coerce",
            utc=True
        )
    else:
        # quitar espacios/comas
        s = pd.to_datetime(s.astype(str).str.strip(), errors="coerce", utc=True)
    return s

def cargar_y_combinar_datos(
    csv_file: str,
    client=None,
    symbol: str = "WLDUSDT",
    interval: str = "1m",
    limit: int = 1500,
    acum_file: str = "data/historiales/historial_trading_acumulado.csv",
    meses: int = 3,
    api_fetch: bool = False          # <-- agregado
) -> pd.DataFrame:
    frames = []

    def _safe_read(path):
        try:
            return pd.read_csv(path)
        except Exception as e:
            logger.warning("No se pudo leer %s: %s", path, e)
            return pd.DataFrame()

    if os.path.exists(csv_file):
        frames.append(_safe_read(csv_file))
    else:
        logger.warning("Archivo base no existe: %s", csv_file)

    if acum_file and os.path.exists(acum_file):
        frames.append(_safe_read(acum_file))

    # (Opcional) API si se activa
    if api_fetch and client:
        try:
            # import robusto con fallbacks
            try:
                from src.pipeline.conexion_api import get_historical_data
            except Exception:
                try:
                    from pipeline.conexion_api import get_historical_data
                except Exception:
                    from conexion_api import get_historical_data

            df_api = get_historical_data(client, symbol=symbol, interval=interval, limit=limit)
            # aceptar lista/dict --> DataFrame
            if isinstance(df_api, list):
                df_api = pd.DataFrame(df_api)
            if df_api is not None and not df_api.empty:
                frames.append(df_api)
        except Exception as e:
            logger.warning("API falló %s: %s", symbol, e)

    if not frames:
        logger.error("Sin datos combinables (%s)", symbol)
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Si hay columna 'symbol', filtrar por el símbolo solicitado para evitar mezclar activos
    if "symbol" in df.columns:
        uniques = df["symbol"].dropna().unique().tolist()
        if symbol not in uniques:
            logger.warning("Dataset combinado no contiene filas para %s. Símbolos presentes: %s", symbol, uniques[:10])
        df = df.loc[df["symbol"] == symbol].reset_index(drop=True)

    # Buscar columna temporal
    ts_col = _detect_timestamp_col(df)
    if ts_col is None:
        logger.error("No se encontró columna temporal en dataset (%s)", symbol)
        return pd.DataFrame()

    df[ts_col] = _parse_timestamp(df[ts_col])

    # Renombrar a timestamp unificado
    if ts_col != "timestamp":
        df.rename(columns={ts_col: "timestamp"}, inplace=True)

    # Limpiar NaT
    before = len(df)
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        logger.error("Todas las filas sin timestamp válido (%s)", symbol)
        return pd.DataFrame()

    # Orden y únicos
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"])

    # Filtro meses (solo si hay más de 0)
    if meses and meses > 0:
        cutoff = pd.Timestamp.now(tz=UTC) - DateOffset(months=meses)
        df = df[df["timestamp"] >= cutoff]

    # SANITY: rango real y advertencia si es mucho menor a meses esperado
    start = df[ts_col].min()
    end = df[ts_col].max()
    span_days = (end - start).days if pd.notna(start) and pd.notna(end) else 0

    # expected_days sólo si 'meses' es un entero válido; si meses es None -> no comprobación estricta
    expected_days = None
    if meses is not None:
        try:
            expected_days = int(meses) * 30
        except Exception:
            expected_days = None

    logger.info("Dataset %d filas tras filtro meses=%s (desde %s hasta %s)", len(df), meses, start, end)
    if expected_days is not None and span_days < max(1, expected_days // 6):
        logger.warning("Rango temporal inesperado para %s (%s meses): %s --> %s (%d días). Esperado ~%d días.",
                       symbol, meses, start, end, span_days, expected_days)

    # Normalizar OHLCV
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"]).reset_index(drop=True)

    logger.info(
        "Dataset %s filas tras filtro meses=%s (desde %s hasta %s)",
        len(df), meses,
        df["timestamp"].min(), df["timestamp"].max()
    )

    # Debug: muestra columnas presentes la primera vez
    if before > 0 and len(df) == 0:
        logger.warning("Filtro eliminó todo. Revisa rango temporal y formato de timestamps.")
    return df
"""
frecuencia_datos.py
--------------------
Utilidades para:
 - Detectar frecuencia temporal de un DataFrame OHLCV
 - Resamplear a una frecuencia objetivo (por defecto 15min)
 - Asegurar que un archivo crudo (raw) sea transformado y guardado en `processed/`
 - Preparar listado de archivos procesados para construir el maestro uniforme

Convenciones:
 - Se espera una columna `timestamp` (datetime o convertible) o se intenta inferir.
 - Columnas OHLCV estándar: open, high, low, close, volume.
 - Resampleo sólo se realiza de una frecuencia MÁS FINA a una MÁS GRUESA (ej: 1m -> 15m). No se hace upsampling.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import logging
from typing import Literal, Optional, Tuple

logger = logging.getLogger("frecuencia_datos")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(h)
logger.propagate = False
logger.setLevel(logging.INFO)

CANDIDATE_TS = ["timestamp", "open_time", "date", "datetime", "time", "fecha"]
AGG_OHLCV = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}

FREQ_MAP_SECONDS = {
    60: "1min",
    120: "2min",
    180: "3min",
    300: "5min",
    600: "10min",
    900: "15min",
    1800: "30min",
    3600: "60min",
}

TARGET_FREQ = "15min"  # frecuencia estándar del sistema

# ---------------------------------------------------------
# Detección de frecuencia
# ---------------------------------------------------------

def _detect_timestamp_col(df: pd.DataFrame) -> Optional[str]:
    for c in CANDIDATE_TS:
        if c in df.columns:
            return c
    return None

def detectar_frecuencia(df: pd.DataFrame) -> Optional[str]:
    """Intenta detectar la frecuencia (en alias tipo '15min') de un DataFrame.
    Se basa en la mediana de la diferencia entre timestamps consecutivos.
    """
    if df is None or df.empty:
        return None
    ts_col = _detect_timestamp_col(df)
    if ts_col is None:
        return None
    s = pd.to_datetime(df[ts_col], errors="coerce", utc=True).dropna().sort_values()
    if len(s) < 3:
        return None
    deltas = s.diff().dropna().dt.total_seconds()
    if deltas.empty:
        return None
    med = int(deltas.median())
    # map exact match
    if med in FREQ_MAP_SECONDS:
        return FREQ_MAP_SECONDS[med]
    # fallback heurística (ej: 600-900 range -> 15min si cercano)
    closest = min(FREQ_MAP_SECONDS.keys(), key=lambda x: abs(x - med))
    if abs(closest - med) <= 5:  # tolerancia de 5s
        return FREQ_MAP_SECONDS[closest]
    return None

# ---------------------------------------------------------
# Resampleo
# ---------------------------------------------------------

def resamplear(df: pd.DataFrame, target_freq: str = TARGET_FREQ) -> pd.DataFrame:
    """Resamplea un DataFrame OHLCV a target_freq.
    Requiere que la frecuencia original sea más fina (ej: 1min -> 15min).
    """
    if df.empty:
        return df
    ts_col = _detect_timestamp_col(df) or "timestamp"
    df = df.copy()
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df.dropna(subset=[ts_col]).sort_values(ts_col)
    df = df.drop_duplicates(subset=[ts_col])
    df.set_index(ts_col, inplace=True)
    # Sólo mantener columnas OHLCV que existan
    cols = [c for c in AGG_OHLCV.keys() if c in df.columns]
    # Asegurar volumen al menos
    if not cols:
        raise ValueError("No hay columnas OHLCV para resampleo")
    agg_dict = {c: AGG_OHLCV[c] for c in cols}
    # mypy/pylance puede quejarse por dict[str,str] pero pandas lo acepta
    df_res = df.resample(target_freq).agg(agg_dict)  # type: ignore[arg-type]
    # Eliminar intervals sin datos (open NaN)
    if "open" in df_res.columns:
        df_res = df_res.dropna(subset=["open"])  # sólo conserva buckets con al menos un dato
    df_res = df_res.reset_index().rename(columns={"index": "timestamp"})
    return df_res

# ---------------------------------------------------------
# Asegurar archivo procesado
# ---------------------------------------------------------

def preparar_archivo_procesado(raw_path: Path, processed_dir: Path, target_freq: str = TARGET_FREQ) -> Optional[Path]:
    """Garantiza que un archivo en raw sea convertido a la frecuencia target.
    Devuelve la ruta al archivo procesado (nueva o existente).
    """
    if not raw_path.exists():
        logger.warning("Raw no existe: %s", raw_path)
        return None
    try:
        df_raw = pd.read_csv(raw_path)
    except Exception as e:
        logger.error("Error leyendo %s: %s", raw_path, e)
        return None
    ts_col = _detect_timestamp_col(df_raw)
    if ts_col is None:
        # intentar inferir si no existe timestamp
        logger.error("No se detectó columna temporal en %s", raw_path)
        return None
    # Conversión robusta: si la columna es numérica determinar unidad probable
    if pd.api.types.is_numeric_dtype(df_raw[ts_col]):
        med_val = float(pd.Series(df_raw[ts_col]).dropna().median())
        # Heurísticas: segundos ~1e9, ms ~1e12, micro ~1e15
        if 1e11 < med_val < 1e13:
            df_raw[ts_col] = pd.to_datetime(df_raw[ts_col], unit="ms", errors="coerce", utc=True)
        elif 1e14 < med_val < 1e17:
            df_raw[ts_col] = pd.to_datetime(df_raw[ts_col], unit="us", errors="coerce", utc=True)
        elif 1e8 < med_val < 1e11:
            df_raw[ts_col] = pd.to_datetime(df_raw[ts_col], unit="s", errors="coerce", utc=True)
        else:
            df_raw[ts_col] = pd.to_datetime(df_raw[ts_col], errors="coerce", utc=True)
    else:
        df_raw[ts_col] = pd.to_datetime(df_raw[ts_col], errors="coerce", utc=True)
    # Si la mayoría son números grandes tipo epoch ms no parseados (quedaron NaT), reintentar conversión explícita
    if df_raw[ts_col].isna().mean() > 0.9:
        try:
            nums = pd.to_numeric(df_raw[ts_col].astype(str), errors="coerce")
            # detectar ms vs s
            if nums.dropna().median() > 1e12:
                df_raw[ts_col] = pd.to_datetime(nums, unit="ms", errors="coerce", utc=True)
            else:
                df_raw[ts_col] = pd.to_datetime(nums, unit="s", errors="coerce", utc=True)
        except Exception:
            pass
    df_raw = df_raw.dropna(subset=[ts_col]).sort_values(ts_col)

    freq = detectar_frecuencia(df_raw)
    if freq is None:
        # Fallback heurístico: calcular delta mediana manualmente
        ts_col = _detect_timestamp_col(df_raw) or "timestamp"
        deltas = df_raw[ts_col].sort_values().diff().dt.total_seconds().dropna()
        if not deltas.empty:
            med = float(deltas.median())
            # si la mediana es <=90s asumimos serie granular (1min)
            if med <= 90:
                freq = "1min"
                logger.info(
                    "Frecuencia no detectada explícitamente; asumiendo 1min (mediana %.2fs) para %s",
                    med,
                    raw_path.name,
                )
            else:
                logger.warning(
                    "No se pudo inferir frecuencia usable (mediana %.2fs) para %s",
                    med,
                    raw_path.name,
                )
    symbol_guess = raw_path.stem.split("_")[0].upper()  # WLDUSDT o WLDUSDT_1m -> WLDUSDT
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Nombre salida
    out_name = f"{symbol_guess}_{target_freq}.csv"
    out_path = processed_dir / out_name

    if freq == target_freq:
        # Normalizar columnas + guardar (copy)
        logger.info("%s ya está en %s, copiando normalizado", symbol_guess, target_freq)
        df_norm = df_raw.copy()
        # ordenar columnas OHLCV si existen
        ordered = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in df_norm.columns]
        df_norm = df_norm[ordered]
        df_norm.to_csv(out_path, index=False)
        return out_path

    # Si frecuencia detectada es menor (más granular) -> resamplear
    mapping_order = list(FREQ_MAP_SECONDS.values())
    try:
        if freq is None:
            logger.warning("Frecuencia aún indeterminada; se omite %s", symbol_guess)
            return None
        if freq not in mapping_order:
            logger.warning("Frecuencia '%s' no reconocida en mapping; omitiendo %s", freq, symbol_guess)
            return None
        if mapping_order.index(freq) < mapping_order.index(target_freq):
            logger.info("Resampleando %s de %s a %s", symbol_guess, freq, target_freq)
            df_res = resamplear(df_raw, target_freq=target_freq)
            # ordenar columnas
            ordered = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in df_res.columns]
            df_res = df_res[ordered]
            df_res.to_csv(out_path, index=False)
            return out_path
        elif mapping_order.index(freq) == mapping_order.index(target_freq):
            logger.info("%s ya coincide con frecuencia target (%s)", symbol_guess, target_freq)
            df_norm = df_raw.copy()
            ordered = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in df_norm.columns]
            df_norm = df_norm[ordered]
            df_norm.to_csv(out_path, index=False)
            return out_path
        else:
            logger.warning("No se hace upsample de %s (%s -> %s).", symbol_guess, freq, target_freq)
            return None
    except Exception as e:
        logger.warning("Error en comparación de frecuencias para %s (%s): %s", symbol_guess, freq, e)
        return None

# ---------------------------------------------------------
# Construcción maestro
# ---------------------------------------------------------

def construir_maestro(processed_dir: Path, out_path: Path, target_freq: str = TARGET_FREQ) -> Path:
    """Concatena todos los archivos procesados en un maestro uniforme.
    Valida duplicados y alineación de frecuencia.
    """
    processed_dir.mkdir(parents=True, exist_ok=True)
    archivos = sorted(processed_dir.glob("*.csv"))
    frames = []
    for f in archivos:
        try:
            df = pd.read_csv(str(f), parse_dates=["timestamp"])  # infer_datetime_format deprecated
        except Exception as e:
            logger.warning("No se pudo leer %s: %s", f.name, e)
            continue
        # Validación de frecuencia (rápida): mediana delta == target
        freq = detectar_frecuencia(df)
        if freq != target_freq:
            logger.warning("Archivo %s no está en %s (detectado %s). Se omite.", f.name, target_freq, freq)
            continue
        symbol = f.stem.replace(f"_{target_freq}", "").upper()
        df["symbol"] = symbol
        frames.append(df)
    if not frames:
        logger.error("Sin archivos válidos en %s", processed_dir)
        return out_path
    maestro = pd.concat(frames, ignore_index=True)
    # Eliminar duplicados
    maestro = maestro.drop_duplicates(subset=["symbol", "timestamp"]).sort_values(["symbol", "timestamp"])  # noqa

    # Chequear huecos por símbolo (diagnóstico)
    gaps_report = {}
    for sym, group in maestro.groupby("symbol"):
        g = group.sort_values("timestamp")
        deltas = g["timestamp"].diff().dropna().dt.total_seconds()
        expected = 900  # 15min
        gaps = (deltas != expected).sum()
        gaps_report[sym] = int(gaps)
        if gaps > 0:
            logger.warning("%s: %d gaps detectados (intervalos != %ss)", sym, gaps, expected)

    maestro.to_csv(out_path, index=False)
    logger.info("Maestro generado: %s (%d filas, %d símbolos)", out_path, len(maestro), maestro['symbol'].nunique())
    return out_path

# ---------------------------------------------------------
# Helper principal
# ---------------------------------------------------------

def asegurar_y_construir(raw_dir: Path, processed_dir: Path, out_maestro: Path, target_freq: str = TARGET_FREQ) -> Path:
    """Pipeline completo:
     1. Itera archivos crudos en raw_dir
     2. Asegura cada símbolo a target_freq escribiendo en processed_dir
     3. Construye maestro final
    """
    raw_dir = Path(raw_dir)
    processed_dir = Path(processed_dir)
    out_maestro = Path(out_maestro)

    if not raw_dir.exists():
        raise FileNotFoundError(f"Directorio raw no existe: {raw_dir}")

    for raw_file in sorted(raw_dir.glob("*.csv")):
        preparar_archivo_procesado(raw_file, processed_dir, target_freq=target_freq)

    construir_maestro(processed_dir, out_maestro, target_freq=target_freq)
    return out_maestro

__all__ = [
    "detectar_frecuencia",
    "resamplear",
    "preparar_archivo_procesado",
    "construir_maestro",
    "asegurar_y_construir",
]

# =========================================================
# Extensiones para extracción y resampleo desde maestro grande
# =========================================================

def extraer_symbol_desde_maestro(maestro_path: Path, symbol: str, raw_out: Path, timestamp_col: str = "timestamp", chunksize: int = 300_000) -> Path | None:
    """Extrae todas las filas de un símbolo desde un CSV maestro potencialmente grande.

    - Lee en chunks para limitar memoria.
    - Filtra columnas OHLCV si existen.
    - Escribe archivo raw con nombre SYMBOLUSDT_raw.csv (sin modificar frecuencia original).
    """
    symbol = symbol.upper()
    maestro_path = Path(maestro_path)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    if not maestro_path.exists():
        logger.error("Maestro no encontrado: %s", maestro_path)
        return None
    cols_basicas = [timestamp_col, "symbol", "open", "high", "low", "close", "volume"]
    encontrados = []
    try:
        for chunk in pd.read_csv(maestro_path, chunksize=chunksize):
            if "symbol" not in chunk.columns:
                logger.error("El maestro no tiene columna 'symbol'")
                return None
            if timestamp_col not in chunk.columns:
                # intentar detectar timestamp
                for c in CANDIDATE_TS:
                    if c in chunk.columns:
                        chunk.rename(columns={c: timestamp_col}, inplace=True)
                        break
            sub = chunk.loc[chunk["symbol"].astype(str).str.upper() == symbol]
            if sub.empty:
                continue
            # conservar sólo columnas relevantes si existen
            keep_cols = [c for c in cols_basicas if c in sub.columns]
            sub = sub[keep_cols]
            encontrados.append(sub)
    except Exception as e:
        logger.error("Error leyendo maestro en chunks: %s", e)
        return None
    if not encontrados:
        logger.warning("No se hallaron filas para %s en maestro", symbol)
        return None
    df = pd.concat(encontrados, ignore_index=True)
    df.to_csv(raw_out, index=False)
    logger.info("Archivo raw extraído %s (%d filas)", raw_out, len(df))
    return raw_out


def incorporar_nuevo_simbolo(maestro_path: Path, symbol: str, raw_dir: Path, processed_dir: Path, out_maestro: Path, target_freq: str = TARGET_FREQ) -> Path | None:
    """Pipeline para agregar (o regenerar) un símbolo:
      1. Extrae símbolo desde maestro grande (si no existe raw específico)
      2. Resamplea / normaliza a target_freq en processed
      3. Reconstruye maestro final (incluyendo todos los processed existentes)
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{symbol.upper()}_raw.csv"
    if not raw_file.exists():
        extraer_symbol_desde_maestro(maestro_path, symbol, raw_file)
    preparar_archivo_procesado(raw_file, processed_dir, target_freq=target_freq)
    construir_maestro(processed_dir, out_maestro, target_freq=target_freq)
    return out_maestro

__all__ += [
    "extraer_symbol_desde_maestro",
    "incorporar_nuevo_simbolo",
]

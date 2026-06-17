"""
gestor_indicadores.py
---------------------
Cálculo y orquestación de indicadores técnicos.
"""

from typing import Optional, Dict, Iterable, Any
import logging
import os
import numpy as np
import pandas as pd

# pandas_ta es opcional; usar si está instalado
try:
    import pandas_ta as ta  # type: ignore
except Exception:
    ta = None

# Import relativo preferido para evitar problemas de Pylance/paquetes
# Los fallbacks deben respetar la firma original para evitar warnings de tipos.
try:
    from .indicadores_tecnicos import (
        calculate_atr,
        calculate_ichimoku,
    )
except Exception:
    try:
        from src.core.indicadores_tecnicos import (
            calculate_atr,
            calculate_ichimoku,
        )
    except Exception:
        def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
            """Fallback compatible: devuelve pd.Series de NaNs con índice apropiado."""
            length = len(df) if df is not None else 0
            s = pd.Series([np.nan] * length, dtype="float64")
            s.index = pd.RangeIndex(length)
            return s

        def calculate_ichimoku(prices: Iterable, highs: Iterable, lows: Iterable,
                               period_tenkan: int = 9, period_kijun: int = 26, period_senkou: int = 52
                               ) -> Optional[Dict[str, Optional[float]]]:
            """Fallback compatible: firma igual que la implementación real; retorna None."""
            return None

# Logger local
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def safe_series(col_like: Any, length: int) -> pd.Series:
    """Devuelve pd.Series numérica con la longitud esperada, rellenando NaN si es necesario."""
    if col_like is None:
        s = pd.Series([np.nan] * length, dtype="float64")
        s.index = pd.RangeIndex(length)
        return s
    if isinstance(col_like, pd.Series):
        s = pd.to_numeric(col_like, errors="coerce").astype("float64")
    else:
        try:
            s = pd.Series(list(col_like)).apply(pd.to_numeric, errors="coerce").astype("float64")
        except Exception:
            s = pd.Series([np.nan] * length, dtype="float64")
    if len(s) < length:
        s = s.reindex(range(length))
    s.index = pd.RangeIndex(len(s))
    return s


def calcular_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI sencillo (serie)"""
    length = len(series) if series is not None else 0
    s = safe_series(series, length)
    if s.empty:
        return s
    delta = s.diff()
    up = delta.clip(lower=0).rolling(period, min_periods=1).mean()
    down = -delta.clip(upper=0).rolling(period, min_periods=1).mean()
    rs = up / down.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.ffill()


def calcular_todos_los_indicadores(df: pd.DataFrame, export_snapshot: bool = True, snapshot_prefix: str = None):
    """
    Calcula y devuelve indicadores por fila (lista de dicts).
    """
    if df is None or df.empty:
        return []

    df2 = df.copy().reset_index(drop=True)
    n = len(df2)

    # Columnas seguras
    close = safe_series(df2["close"] if "close" in df2.columns else None, n)
    high = safe_series(df2["high"] if "high" in df2.columns else None, n)
    low = safe_series(df2["low"] if "low" in df2.columns else None, n)

    # ATR
    try:
        atr = calculate_atr(df2, period=14)
        if not isinstance(atr, pd.Series):
            atr = pd.Series(atr).reindex(range(n)).astype("float64")
    except Exception:
        atr = pd.Series([np.nan] * n, dtype="float64")

    # RSI
    rsi = calcular_rsi(close, period=14)

    # BB Width
    if not close.empty:
        mb = close.rolling(20, min_periods=1).mean()
        std = close.rolling(20, min_periods=1).std().fillna(0)
        upper = mb + 2 * std
        lower = mb - 2 * std
        with np.errstate(divide="ignore", invalid="ignore"):
            bbw = ((upper - lower) / mb).replace([np.inf, -np.inf], np.nan)
        bbw = bbw.reindex(range(n)).astype("float64")
    else:
        bbw = pd.Series([np.nan] * n, dtype="float64")

    # ADX (pandas_ta opcional)
    if ta is not None and not high.empty and not low.empty and not close.empty:
        try:
            adx_df = ta.adx(high=high, low=low, close=close, length=14)
            adx_col = next((c for c in adx_df.columns if "ADX" in c.upper()), None)
            if adx_col is not None and adx_col in adx_df.columns:
                adx = adx_df[adx_col].reset_index(drop=True).reindex(range(n)).astype("float64")
            else:
                adx = pd.Series([np.nan] * n, dtype="float64")
        except Exception:
            adx = pd.Series([np.nan] * n, dtype="float64")
    else:
        adx = pd.Series([np.nan] * n, dtype="float64")

    # Ichimoku (fallback devuelve None o dict)
    ichimoku_vals = None
    try:
        ichimoku_vals = calculate_ichimoku(close, high, low)
    except Exception:
        ichimoku_vals = None

    ich_cols = {
        "Tenkan": np.nan,
        "Kijun": np.nan,
        "SenkouA": np.nan,
        "SenkouB": np.nan,
        "Chikou": np.nan
    }
    if isinstance(ichimoku_vals, dict):
        ich_cols["Tenkan"] = ichimoku_vals.get("tenkan", np.nan)
        ich_cols["Kijun"] = ichimoku_vals.get("kijun", np.nan)
        ich_cols["SenkouA"] = ichimoku_vals.get("senkou_a", np.nan)
        ich_cols["SenkouB"] = ichimoku_vals.get("senkou_b", np.nan)
        ich_cols["Chikou"] = ichimoku_vals.get("chikou", np.nan)

    ichimoku_df = pd.DataFrame({k: [float(v) if v is not None and not pd.isna(v) else np.nan] * n for k, v in ich_cols.items()})

    # MACD (pandas_ta opcional)
    macd_df = pd.DataFrame({"macd": [np.nan] * n, "signal": [np.nan] * n, "hist": [np.nan] * n})
    if ta is not None and not close.empty:
        try:
            macd_tmp = ta.macd(close=close, fast=12, slow=26, signal=9)
            cols = list(macd_tmp.columns) if macd_tmp is not None else []
            macd_col = next((c for c in cols if c.upper().startswith("MACD_") and "_H" not in c.upper()), None)
            signal_col = next((c for c in cols if "MACDs" in c or c.upper().endswith("_S")), None)
            hist_col = next((c for c in cols if "MACDh" in c or c.upper().endswith("_H")), None)
            if macd_col and macd_col in macd_tmp.columns:
                macd_df["macd"] = macd_tmp[macd_col].reset_index(drop=True).reindex(range(n)).astype("float64")
            if signal_col and signal_col in macd_tmp.columns:
                macd_df["signal"] = macd_tmp[signal_col].reset_index(drop=True).reindex(range(n)).astype("float64")
            if hist_col and hist_col in macd_tmp.columns:
                macd_df["hist"] = macd_tmp[hist_col].reset_index(drop=True).reindex(range(n)).astype("float64")
        except Exception:
            pass

    # Construir DataFrame de salida
    indicadores_df = pd.DataFrame({
        "RSI": rsi.values if hasattr(rsi, "values") else np.array(rsi, dtype="float64"),
        "ATR": atr.values if hasattr(atr, "values") else np.array(atr, dtype="float64"),
        "BB_Width": bbw.values if hasattr(bbw, "values") else np.array(bbw, dtype="float64"),
        "ADX": adx.values if hasattr(adx, "values") else np.array(adx, dtype="float64")
    })

    indicadores_df = pd.concat([indicadores_df.reset_index(drop=True), ichimoku_df.reset_index(drop=True)], axis=1)
    indicadores_df = pd.concat([indicadores_df.reset_index(drop=True), macd_df.reset_index(drop=True)], axis=1)
    indicadores_df["votes"] = 1

    for c in indicadores_df.columns:
        indicadores_df[c] = pd.to_numeric(indicadores_df[c], errors="coerce")

    out_list = indicadores_df.fillna(value=np.nan).to_dict(orient="records")

    # Export snapshot opcional
    if export_snapshot:
        try:
            os.makedirs("data/backtesting", exist_ok=True)
            ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            prefix = snapshot_prefix or f"indicadores_snapshot_{ts}"
            indicadores_df.to_csv(os.path.join("data/backtesting", f"{prefix}.csv"), index=False)
            indicadores_df.to_json(os.path.join("data/backtesting", f"{prefix}.json"), orient="records", force_ascii=False)
        except Exception:
            logger.debug("No se pudo exportar snapshot de indicadores; se ignora.", exc_info=True)

    return out_list


def evaluar_indicadores(indicadores_lista):
    """
    Evaluación simple de señales basada en el último registro.
    Función auxiliar no usada en el flujo principal por defecto.
    """
    recomendaciones = []

    if not indicadores_lista or not isinstance(indicadores_lista, list):
        logger.warning("⚠️ No hay datos suficientes para evaluar indicadores.")
        return recomendaciones

    ultimo_registro = indicadores_lista[-1]

    # RSI
    rsi_actual = ultimo_registro.get("RSI")
    if isinstance(rsi_actual, (int, float, np.floating)):
        if rsi_actual < 30:
            recomendaciones.append("Posible señal de compra (RSI < 30)")
        if rsi_actual > 70:
            recomendaciones.append("Posible señal de venta (RSI > 70)")

    # ADX simple
    adx = ultimo_registro.get("ADX")
    if adx is not None and isinstance(adx, (int, float, np.floating)) and adx > 25:
        recomendaciones.append("Tendencia fuerte detectada (ADX > 25)")

    logger.info("Evaluación de indicadores completada.")
    return recomendaciones


def calcular_trailing_ok(indicadores, trailing_global=True, adx_trailing_thr=25.0):
    """
    Determina si el trailing stop debe estar activo según los indicadores.
    """
    try:
        adx_val = float(indicadores.get("ADX", 0.0)) if isinstance(indicadores, dict) else 0.0
        tenkan = indicadores.get("Tenkan") if isinstance(indicadores, dict) else None
        kijun = indicadores.get("Kijun") if isinstance(indicadores, dict) else None
        ichimoku_ok = False
        if tenkan is not None and kijun is not None:
            try:
                ichimoku_ok = float(tenkan) > float(kijun)
            except Exception:
                ichimoku_ok = False
        return bool(trailing_global) and (adx_val >= adx_trailing_thr or ichimoku_ok)
    except Exception:
        return bool(trailing_global)


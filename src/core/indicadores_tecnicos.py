"""
indicadores_tecnicos.py
-----------------------
Funciones para calcular indicadores técnicos personalizados para trading.
Las funciones aceptan iterables (list/ndarray/Series). Devuelven:
- para indicadores "puntuales" (RSI, BB, MACD, ADX, Ichimoku): el último valor calculado (float o tuple de floats) o None si no hay suficiente data.
- para indicadores que tienen sentido como series (ATR): pd.Series alineada a la longitud de entrada.
Se utilizan pandas internamente para robustez en parsing y rolling.
"""

from typing import Iterable, Optional, Tuple, Dict
import logging

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)


def _to_series(values: Iterable) -> pd.Series:
    """Convertir entrada a pd.Series segura."""
    if isinstance(values, pd.Series):
        # forzar conversión numérica segura
        return pd.to_numeric(values, errors="coerce").astype("float64")
    # proteger contra strings (iterable de caracteres)
    if isinstance(values, (str, bytes)):
        vals = [values]
    else:
        try:
            vals = list(values)
        except Exception:
            vals = [values]
    # crear Series con dtype explícito para evitar warnings de tipos
    try:
        return pd.Series(vals, dtype="float64")
    except Exception:
        # fallback más permisivo
        return pd.Series(vals).apply(pd.to_numeric, errors="coerce").astype("float64")


def calculate_rsi(prices: Iterable, period: int = 14) -> Optional[float]:
    """
    Calcula RSI (último valor) usando smoothing tipo Wilder (EWMA con adjust=False).
    Retorna float o None si no hay suficiente data.
    """
    s = _to_series(prices)
    if s.dropna().shape[0] < period + 1:
        return None
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    # Wilder smoothing
    ma_up = up.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = ma_up / ma_down
    rsi = 100 - (100 / (1 + rs))
    last = rsi.iloc[-1]
    try:
        return float(last) if pd.notna(last) else None
    except Exception:
        return None


def calculate_bollinger_bands(prices: Iterable, period: int = 20, n_std: float = 2.0) -> Optional[Tuple[float, float, float]]:
    """
    Calcula Bandas de Bollinger (SMA, upper, lower) y devuelve los últimos tres valores.
    Retorna (sma, upper, lower) o None si no hay suficiente data.
    """
    s = _to_series(prices)
    if s.dropna().shape[0] < period:
        return None
    sma = s.rolling(window=period, min_periods=period).mean()
    std = s.rolling(window=period, min_periods=period).std()
    sma_last = sma.iloc[-1]
    std_last = std.iloc[-1]
    if pd.isna(sma_last) or pd.isna(std_last):
        return None
    upper = float(sma_last + n_std * std_last)
    lower = float(sma_last - n_std * std_last)
    return float(sma_last), upper, lower


def calculate_macd(prices: Iterable, short_period: int = 12, long_period: int = 26, signal_period: int = 9) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calcula MACD (últimos valores): (macd_line, signal_line, macd_hist).
    Devuelve tupla de floats o (None, None, None) si no hay suficiente data.
    """
    s = _to_series(prices)
    if s.dropna().shape[0] < long_period:
        return None, None, None
    ema_short = s.ewm(span=short_period, adjust=False).mean()
    ema_long = s.ewm(span=long_period, adjust=False).mean()
    macd_line = ema_short - ema_long
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    hist = macd_line - signal_line
    try:
        return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(hist.iloc[-1])
    except Exception:
        return None, None, None


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calcula ATR (Average True Range) como pd.Series alineada a df (index preserved).
    Acepta DataFrame con columnas 'high','low','close' (case-insensitive).
    Retorna pd.Series (llenada con 0 si no hay suficientes datos).
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    # Normalizar nombres
    d = df.copy()
    cols = {c.lower(): c for c in d.columns}
    high = pd.to_numeric(d[cols.get("high", "high")], errors="coerce") if "high" in cols else pd.Series([np.nan] * len(d))
    low = pd.to_numeric(d[cols.get("low", "low")], errors="coerce") if "low" in cols else pd.Series([np.nan] * len(d))
    close = pd.to_numeric(d[cols.get("close", "close")], errors="coerce") if "close" in cols else pd.Series([np.nan] * len(d))

    prev_close = close.shift(1)
    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean()
    # usar ffill() en lugar de fillna(method="ffill") para evitar mensaje de Pylance
    atr = atr.ffill().fillna(0.0)
    atr.index = d.index
    return atr


def calculate_adx(highs: Iterable, lows: Iterable, closes: Iterable, period: int = 14) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calcula ADX simplificado y devuelve (adx, plus_di, minus_di) como floats o (None, None, None) si no hay suficiente data.
    Esta implementación usa métodos clásicos pero simplifica algunos pasos para robustez.
    """
    hs = _to_series(highs)
    ls = _to_series(lows)
    cs = _to_series(closes)
    if min(hs.dropna().shape[0], ls.dropna().shape[0], cs.dropna().shape[0]) < period + 1:
        return None, None, None

    # True Range components
    prev_close = cs.shift(1)
    high_diff = hs - hs.shift(1)
    low_diff = ls.shift(1) - ls

    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)

    tr1 = (hs - ls).abs()
    tr2 = (hs - prev_close).abs()
    tr3 = (ls - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Smooth using Wilder (EMA with alpha=1/period)
    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr)

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    try:
        adx_last = float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else None
        pdi_last = float(plus_di.iloc[-1]) if pd.notna(plus_di.iloc[-1]) else None
        mdi_last = float(minus_di.iloc[-1]) if pd.notna(minus_di.iloc[-1]) else None
        return adx_last, pdi_last, mdi_last
    except Exception:
        return None, None, None


def calculate_ichimoku(prices: Iterable, highs: Iterable, lows: Iterable,
                       period_tenkan: int = 9, period_kijun: int = 26, period_senkou: int = 52) -> Optional[Dict[str, Optional[float]]]:
    """
    Calcula componentes Ichimoku (últimos valores) y devuelve diccionario con claves:
    'tenkan', 'kijun', 'senkou_a', 'senkou_b', 'chikou' o None si no hay suficiente data.
    Los valores individuales pueden ser float o None.
    """
    ps = _to_series(prices)
    hs = _to_series(highs)
    ls = _to_series(lows)
    min_req = max(period_tenkan, period_kijun, period_senkou)
    if min(ps.dropna().shape[0], hs.dropna().shape[0], ls.dropna().shape[0]) < min_req:
        return None

    try:
        tenkan = ((hs.rolling(window=period_tenkan).max() + ls.rolling(window=period_tenkan).min()) / 2).iloc[-1]
        kijun = ((hs.rolling(window=period_kijun).max() + ls.rolling(window=period_kijun).min()) / 2).iloc[-1]
        senkou_a = ((tenkan + kijun) / 2)  # note: senkou_a normally shifted forward, here we return computed value
        senkou_b = ((hs.rolling(window=period_senkou).max() + ls.rolling(window=period_senkou).min()) / 2).iloc[-1]
        chikou = ps.iloc[-1]
        return {
            "tenkan": float(tenkan) if pd.notna(tenkan) else None,
            "kijun": float(kijun) if pd.notna(kijun) else None,
            "senkou_a": float(senkou_a) if pd.notna(senkou_a) else None,
            "senkou_b": float(senkou_b) if pd.notna(senkou_b) else None,
            "chikou": float(chikou) if pd.notna(chikou) else None
        }
    except Exception as e:
        _log.exception("Error calculando ichimoku: %s", e)
        return None

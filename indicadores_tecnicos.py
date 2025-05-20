import numpy as np
import logging

def calculate_rsi(prices, period=14):
    """
    Calcula el RSI (Relative Strength Index).
    """
    if len(prices) < period:
        return None  # No loguea, es esperado en backtesting

    deltas = np.diff(prices)
    gains = np.maximum(deltas, 0)
    losses = np.abs(np.minimum(deltas, 0))

    avg_gain = np.mean(gains[:period]) if len(gains) >= period else 0
    avg_loss = np.mean(losses[:period]) if len(losses) >= period else 0

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi if not np.isnan(rsi) else None

def calculate_bollinger_bands(prices, period=20):
    """
    Calcula las Bandas de Bollinger después de validar y limpiar los datos.
    """
    try:
        if len(prices) < period:
            return None  # No loguea, es esperado en backtesting
        prices = [p for p in prices if isinstance(p, (int, float)) and not np.isnan(p)]
        if len(prices) < period:
            return None  # No loguea, es esperado en backtesting
        sma = np.mean(prices[-period:])
        std_dev = np.std(prices[-period:])
        if std_dev == 0:
            logging.warning(f"⚠️ Desviación estándar es 0, lo que indica que los precios no varían.")
            return sma, sma, sma
        upper_band = sma + (2 * std_dev)
        lower_band = sma - (2 * std_dev)
        return sma, upper_band, lower_band
    except Exception as e:
        logging.error(f"❌ Error inesperado al calcular Bandas de Bollinger: {e}")
        return None

def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    """
    Calcula el MACD (Moving Average Convergence Divergence).
    """
    if len(prices) < max(short_period, long_period, signal_period):
        return None, None, None  # No loguea, es esperado en backtesting

    short_ema = np.mean(prices[:short_period])
    multiplier_short = 2 / (short_period + 1)
    for price in prices[short_period:]:
        short_ema = (price - short_ema) * multiplier_short + short_ema

    long_ema = np.mean(prices[:long_period])
    multiplier_long = 2 / (long_period + 1)
    for price in prices[long_period:]:
        long_ema = (price - long_ema) * multiplier_long + long_ema

    macd_line = short_ema - long_ema

    signal_line = macd_line
    multiplier_signal = 2 / (signal_period + 1)
    for _ in range(signal_period):
        signal_line = (macd_line - signal_line) * multiplier_signal + signal_line

    macd_histogram = macd_line - signal_line
    return macd_line, signal_line, macd_histogram

def calculate_atr(highs, lows, closes, period=14):
    """
    Calcula el ATR (Average True Range) después de validar y limpiar los datos.
    """
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None  # No loguea, es esperado en backtesting
    highs = [h for h in highs if h is not None and not np.isnan(h)]
    lows = [l for l in lows if l is not None and not np.isnan(l)]
    closes = [c for c in closes if c is not None and not np.isnan(c)]
    true_ranges = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        true_ranges.append(tr)
    if len(true_ranges) < period:
        return None  # No loguea, es esperado en backtesting
    atr = np.mean(true_ranges[-period:])
    return atr if not np.isnan(atr) else None

def calculate_adx(highs, lows, closes, period=14):
    """
    Calcula el ADX (Average Directional Index).
    """
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None, None, None  # No loguea, es esperado en backtesting

    plus_dm = []
    minus_dm = []
    true_ranges = []

    for i in range(1, len(highs)):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]
        true_ranges.append(
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        )
        plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
        minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)

    if len(true_ranges) < period or len(plus_dm) < period or len(minus_dm) < period:
        return None, None, None  # No loguea, es esperado en backtesting

    atr = np.mean(true_ranges[:period])
    plus_di = 100 * (np.mean(plus_dm[:period]) / atr) if atr != 0 else 0
    minus_di = 100 * (np.mean(minus_dm[:period]) / atr) if atr != 0 else 0

    dx = [
        100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) != 0 else 0
        for i in range(period, len(true_ranges))
    ]

    if len(dx) < period:
        return None, plus_di, minus_di  # No loguea, es esperado en backtesting

    adx = np.mean(dx[:period])
    for i in range(period, len(dx)):
        adx = ((adx * (period - 1)) + dx[i]) / period

    return adx if not np.isnan(adx) else None, plus_di, minus_di

def calculate_ichimoku(prices, highs, lows, period_tenkan=9, period_kijun=26, period_senkou=52):
    """
    Calcula los componentes del Ichimoku Cloud después de validar y limpiar los datos.
    """
    if len(highs) < max(period_tenkan, period_kijun, period_senkou) or len(lows) < max(period_tenkan, period_kijun, period_senkou) or len(prices) < period_kijun:
        return None  # No loguea, es esperado en backtesting
    highs = [h for h in highs if h is not None and not np.isnan(h)]
    lows = [l for l in lows if l is not None and not np.isnan(l)]
    prices = [p for p in prices if p is not None and not np.isnan(p)]
    tenkan_sen = (max(highs[-period_tenkan:]) + min(lows[-period_tenkan:])) / 2
    kijun_sen = (max(highs[-period_kijun:]) + min(lows[-period_kijun:])) / 2
    senkou_span_a = (tenkan_sen + kijun_sen) / 2
    senkou_span_b = (max(highs[-period_senkou:]) + min(lows[-period_senkou:])) / 2
    chikou_span = prices[-1]
    return {
        "Tenkan-Sen": tenkan_sen,
        "Kijun-Sen": kijun_sen,
        "Senkou Span A": senkou_span_a,
        "Senkou Span B": senkou_span_b,
        "Chikou Span": chikou_span
    }

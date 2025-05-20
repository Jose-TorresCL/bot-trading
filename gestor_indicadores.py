import logging
import numpy as np
import pandas as pd                         
import pandas_ta as ta
from indicadores_tecnicos import (
    calculate_rsi, calculate_bollinger_bands, calculate_macd,
    calculate_atr, calculate_adx, calculate_ichimoku
)

# Configuración de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Wrapper seguro para indicadores
def safe_indicator(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logging.debug(f"Indicador {func.__name__} no calculado: {e}")
        return None

# 📌 Configuración dinámica de indicadores con verificación de parámetros
indicadores_config = {
    "RSI": {"function": calculate_rsi, "params": ["close"], "min_values": 12},
    "ATR": {"function": calculate_atr, "params": ["high", "low", "close"], "min_values": 13},
    "ADX": {"function": calculate_adx, "params": ["high", "low", "close"], "min_values": 13},
    "Ichimoku": {"function": calculate_ichimoku, "params": ["price", "high", "low"], "min_values": 50},
    "MACD": {"function": calculate_macd, "params": ["price"], "min_values": 15},
    "Bollinger": {"function": calculate_bollinger_bands, "params": ["price"], "min_values": 15}
}

def calcular_todos_los_indicadores(df):
    # Asegura que los precios sean float
    for col in ["close", "open", "high", "low"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # RSI
    df["RSI"] = ta.rsi(df["close"], length=14)
    # MACD
    macd = ta.macd(df["close"])
    df["MACD"] = macd["MACD_12_26_9"]
    df["MACD_signal"] = macd["MACDs_12_26_9"]
    df["MACD_hist"] = macd["MACDh_12_26_9"]
    # ATR
    df["ATR"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    # ADX
    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    df["ADX"] = adx["ADX_14"]
    df["Plus_DI"] = adx["DMP_14"]
    df["Minus_DI"] = adx["DMN_14"]
    # Bollinger Bands
    bb = ta.bbands(df["close"], length=20)
    df["BB_Middle"] = bb["BBM_20_2.0"]
    df["BB_Upper"] = bb["BBU_20_2.0"]
    df["BB_Lower"] = bb["BBL_20_2.0"]
    # Ichimoku (usa los nombres reales de columnas de pandas_ta)
    ichi = ta.ichimoku(df["high"], df["low"], df["close"])
    ichi_df = ichi[0]
    df["Ichimoku_Tenkan"] = ichi_df["ITS_9"] if "ITS_9" in ichi_df else np.nan
    df["Ichimoku_Kijun"] = ichi_df["IKS_26"] if "IKS_26" in ichi_df else np.nan
    df["Ichimoku_SpanA"] = ichi_df["ISA_9"] if "ISA_9" in ichi_df else np.nan
    df["Ichimoku_SpanB"] = ichi_df["ISB_26"] if "ISB_26" in ichi_df else np.nan
    df["Ichimoku_Chikou"] = ichi_df["ICS_26"] if "ICS_26" in ichi_df else np.nan

    return df.to_dict(orient="records")

def evaluar_indicadores(indicadores_lista):
    """
    Evalúa señales de trading basadas en indicadores técnicos desde una lista de diccionarios.
    """
    recomendaciones = []

    if not indicadores_lista or not isinstance(indicadores_lista, list):
        logging.warning("⚠️ No hay datos suficientes para evaluar indicadores.")
        return recomendaciones

    ultimo_registro = indicadores_lista[-1]  # Último conjunto de indicadores

    # RSI
    rsi_actual = ultimo_registro.get("RSI")
    if isinstance(rsi_actual, (int, float, np.floating)):
        if rsi_actual < 30:
            recomendaciones.append("🔹 Posible señal de compra (RSI < 30)")
        if rsi_actual > 70:
            recomendaciones.append("🔹 Posible señal de venta (RSI > 70)")

    # MACD y su señal
    macd_line = ultimo_registro.get("MACD")
    macd_signal = ultimo_registro.get("MACD_signal")
    if macd_line is not None and macd_signal is not None:
        if macd_line > macd_signal:
            recomendaciones.append("✅ MACD alcista (MACD > Signal) - posible compra")
        elif macd_line < macd_signal:
            recomendaciones.append("❌ MACD bajista (MACD < Signal) - posible venta")

    # Bollinger Bands
    close = ultimo_registro.get("close")
    bb_upper = ultimo_registro.get("BB_Upper")
    bb_lower = ultimo_registro.get("BB_Lower")
    if close is not None and bb_upper is not None and bb_lower is not None:
        if close > bb_upper:
            recomendaciones.append("🔺 Precio por encima de la banda superior de Bollinger (sobrecompra)")
        elif close < bb_lower:
            recomendaciones.append("🔻 Precio por debajo de la banda inferior de Bollinger (sobreventa)")

    # ADX
    adx = ultimo_registro.get("ADX")
    if adx is not None and adx > 25:
        recomendaciones.append("📈 Tendencia fuerte detectada (ADX > 25)")

    # Ichimoku (ejemplo simple)
    span_a = ultimo_registro.get("Ichimoku_SpanA")
    span_b = ultimo_registro.get("Ichimoku_SpanB")
    if span_a is not None and span_b is not None:
        if span_a > span_b:
            recomendaciones.append("🌤️ Ichimoku alcista (SpanA > SpanB)")
        elif span_a < span_b:
            recomendaciones.append("🌧️ Ichimoku bajista (SpanA < SpanB)")

    logging.info(f"📊 Evaluación de indicadores completada: {recomendaciones}")
    return recomendaciones
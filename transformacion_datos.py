import pandas as pd
import numpy as np
import logging

def transformar_datos(datos):
    """Transforma los datos históricos con validaciones y conversión eficiente."""
    
    # 🚀 Verificar si `datos` está vacío o no es un DataFrame
    if datos is None or len(datos) == 0:
        logging.warning("⚠️ No hay datos para transformar.")
        return pd.DataFrame()  # 🚀 Retorno seguro como DataFrame vacío
    
    df = pd.DataFrame(datos)

    # 🔍 Registrar columnas antes de aplicar cualquier transformación
    logging.info(f"🔍 Columnas ANTES de transformación: {df.columns.tolist()}")
    

    # 🚀 PASO 1: Validar que las columnas esenciales existen
    required_columns = ["open", "high", "low", "close", "volume"]
    missing_cols = [col for col in required_columns if col not in df.columns]

    if missing_cols:
        logging.warning(f"⚠️ Faltan columnas esenciales para transformación: {missing_cols}. Se intentará corregir...")
        for col in missing_cols:
            df[col] = 0.0  # 🚀 Asignamos un valor por defecto para evitar pérdida de datos

    # 🚀 PASO 2: Crear la columna "price" si falta, a partir de "close"
    if "price" not in df.columns:
        logging.warning("⚠️ La columna 'price' no está disponible, se creará desde 'close'...")
        df["price"] = df["close"].copy()  # 🔹 Creamos "price" como una copia de "close"

    # 🚀 PASO 3: Manejo seguro de valores NaN e infinitos en el DataFrame
    df.ffill(inplace=True) # 🔹 Rellenar valores faltantes con forward fill seguro
    df.replace([np.inf, -np.inf], 0.0, inplace=True)  # 🔹 Corregir valores infinitos

    # 🚀 PASO 4: Convertir columnas numéricas a float de manera segura
    for col in required_columns + ["price"]:  # 🔹 Incluimos "price" en la conversión
        if col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)  # 🚀 Convierte y maneja errores sin perder datos
            except Exception as e:
                logging.error(f"❌ Error al convertir {col} a float: {e}. Se usará 0.0 en valores no convertibles.")
                df[col] = 0.0  # 🔹 Asignamos un valor por defecto en caso de error

    # 🔍 Verificar columnas después de la transformación")
    logging.info(f"✅ Transformación completada. Registros finales: {len(df)}")

    return df  # 🚀 Retorno seguro de un DataFrame limpio



# 🔹 Estructuración de datos para cálculos técnicos

def estructurar_datos(datos):
    """ Extrae listas de valores clave para los cálculos de indicadores. """
    if not datos:
        logging.error("❌ No hay datos estructurados para procesar.")
        return [], [], [], []

    logging.info(f"🔄 Estructurando datos... Registros antes de estructuración: {len(datos)}")

    highs = [record["high"] for record in datos if "high" in record and record["high"] is not None]
    lows = [record["low"] for record in datos if "low" in record and record["low"] is not None]
    closes = [record["close"] for record in datos if "close" in record and record["close"] is not None]
    prices = [record.get("price", record.get("close", 0.0)) for record in datos]

    # 🚨 Si las listas están vacías, usa el promedio en lugar de ceros
    if not highs or not lows or not closes:
        logging.warning("⚠️ Datos insuficientes tras estructuración, rellenando con promedios.")
        highs = highs if highs else [0.0] * len(datos)
        lows = lows if lows else [0.0] * len(datos)
        closes = closes if closes else [0.0] * len(datos)
        prices = prices if prices else [0.0] * len(datos)

    if len(prices) != len(datos):
        logging.warning(f"⚠️ Desalineación detectada: {len(prices)} prices vs {len(datos)} datos.")

    logging.info(f"✅ Datos estructurados correctamente: {len(highs)} highs, {len(lows)} lows, {len(closes)} closes, {len(prices)} prices.")

    return highs, lows, closes, prices
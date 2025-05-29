import os
import logging
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from conexion_api import connect_to_binance, get_historical_data
from indicadores_tecnicos import (
    calculate_rsi, calculate_bollinger_bands, calculate_macd,
    calculate_atr, calculate_adx, calculate_ichimoku
)

# Cargar variables de entorno desde config.env
load_dotenv("config.env")

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SYMBOL = os.getenv("SYMBOL", "ETHUSDT")
INTERVAL = os.getenv("INTERVAL", "1m,5m,15m,1h,1d")

# Configuración de logs (solo si este archivo se ejecuta solo)
# Si ya configuras logs en el archivo principal, puedes comentar la siguiente línea
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def inicializar_bot():
    """Inicializa la conexión con Binance y obtiene datos históricos."""
    logging.info("🔗 Conectando a Binance...")
    client = connect_to_binance()

    if not client:
        logging.error("❌ Falló la conexión con Binance. Verifica la API Key.")
        return None, None

    historical_prices = obtener_datos_historicos(client)
    return client, historical_prices

def obtener_datos_historicos(client, symbol=SYMBOL, interval=INTERVAL):
    """Obtiene datos históricos y maneja errores."""
    logging.info(f"📊 Obteniendo datos históricos de {symbol} en intervalo {interval}...")
    historical_prices = get_historical_data(client, symbol, interval)

    if historical_prices is None or (hasattr(historical_prices, "empty") and historical_prices.empty) or len(historical_prices) < 50:
        logging.error("❌ Error: `historical_prices` está vacío o tiene menos de 50 registros.")
        return pd.DataFrame()  # Retorno seguro como DataFrame vacío

    logging.info(f"✅ Datos históricos obtenidos con {len(historical_prices)} registros.")
    return historical_prices

def generar_datos_simulados():
    """Genera datos simulados con fluctuaciones más naturales."""
    logging.warning("⚠️ Generando datos simulados para pruebas...")

    fechas = pd.date_range(end=pd.Timestamp.now(), periods=1000, freq="1min")
    precios_base = 1800 + np.sin(np.linspace(0, 10, 1000)) * 20  
    precios_simulados = precios_base + np.random.normal(scale=5, size=1000)

    simulated_data = [
        {
            "timestamp": fecha.timestamp(),
            "open": float(precio),
            "high": float(precio + np.random.uniform(1, 5)),
            "low": float(precio - np.random.uniform(1, 5)),
            "close": float(precio),
            "volume": float(1000 + np.random.randint(-200, 200))
        }
        for fecha, precio in zip(fechas, precios_simulados)
    ]

    logging.info(f"✅ Datos simulados generados: {len(simulated_data)} registros.")
    return simulated_data

def calcular_indicadores(historical_prices):
    """Calcula indicadores técnicos y verifica la calidad de datos antes de procesarlos."""
    # Si es DataFrame, conviértelo a lista de dicts
    if isinstance(historical_prices, pd.DataFrame):
        historical_prices = historical_prices.to_dict("records")

    if not historical_prices or len(historical_prices) < 50:
        logging.warning("⚠️ Datos insuficientes para calcular indicadores.")
        return {}

    # Asegura que los precios sean float
    precios = [float(data.get("close")) for data in historical_prices if "close" in data and data.get("close") is not None]
    if not precios or len(precios) < 50:
        logging.error("❌ Los datos históricos no contienen precios válidos.")
        return {}

    logging.info("📈 Calculando indicadores técnicos...")

    try:
        return {
            "RSI": calculate_rsi(precios),
            "SMA": calculate_bollinger_bands(precios)[0],  
            "Upper Band": calculate_bollinger_bands(precios)[1],
            "Lower Band": calculate_bollinger_bands(precios)[2],
            "MACD Line": calculate_macd(precios)[0], 
            "MACD Signal": calculate_macd(precios)[1],
            "MACD Histogram": calculate_macd(precios)[2],
            "ATR": calculate_atr(precios, precios, precios),
            "ADX": calculate_adx(precios, precios, precios)[0],
            "Plus DI": calculate_adx(precios, precios, precios)[1],
            "Minus DI": calculate_adx(precios, precios, precios)[2],
            "Ichimoku": calculate_ichimoku(precios, precios, precios),
        }
    except Exception as e:
        logging.error(f"❌ Error al calcular indicadores técnicos: {e}")
        return {}
"""
funciones_generales.py
----------------------
Funciones utilitarias para inicializar el bot, obtener datos históricos y calcular indicadores técnicos.
Centraliza la conexión, simulación y cálculo de indicadores.
"""

import os
import logging
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from src.conexion_api import connect_to_binance, get_historical_data
from src.indicadores_tecnicos import (
    calculate_rsi, calculate_bollinger_bands, calculate_macd,
    calculate_atr, calculate_adx, calculate_ichimoku
)

# Cargar variables de entorno desde config.env en carpeta data
load_dotenv("data/config.env")

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SYMBOL = os.getenv("SYMBOL", "ETHUSDT")
INTERVAL = os.getenv("INTERVAL", "1m")

# Configuración de logs (solo si este archivo se ejecuta solo)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def inicializar_bot():
    """
    Inicializa la conexión con Binance y obtiene datos históricos.
    """
    logging.info("🔗 Conectando a Binance...")
    client = connect_to_binance()
    if not client:
        logging.error("❌ Falló la conexión con Binance. Verifica la API Key.")
        return None, None

    historical_prices = obtener_datos_historicos(client)
    return client, historical_prices

def obtener_datos_historicos(client, symbol=SYMBOL, interval=INTERVAL):
    """
    Obtiene datos históricos y maneja errores.
    """
    logging.info(f"📊 Obteniendo datos históricos de {symbol} en intervalo {interval}...")
    historical_prices = get_historical_data(client, symbol, interval)
    if historical_prices is None or (hasattr(historical_prices, "empty") and historical_prices.empty) or len(historical_prices) < 50:
        logging.error("❌ Error: `historical_prices` está vacío o tiene menos de 50 registros.")
        return pd.DataFrame()  # Retorno seguro como DataFrame vacío
    logging.info(f"✅ Datos históricos obtenidos con {len(historical_prices)} registros.")
    return historical_prices

def generar_datos_simulados():
    """
    Genera datos simulados con fluctuaciones más naturales.
    """
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

# La función calcular_indicadores ha sido eliminada.
# El cálculo de indicadores ahora está centralizado en gestor_indicadores.py
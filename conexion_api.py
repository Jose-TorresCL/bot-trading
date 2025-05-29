import os
import logging
from binance.client import Client
from dotenv import load_dotenv
import pandas as pd
import time



# Cargar variables de entorno desde config.env
load_dotenv("config.env")
# Configuración de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def verificar_credenciales():
    """Verifica si las credenciales de Binance están correctamente configuradas."""
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    print(f"🔍 API_KEY: {api_key[:5]}********")
    print(f"🔍 API_SECRET: {api_secret[:5]}********")
    if not api_key or not api_secret:
        logging.error("❌ No se encontraron credenciales. Verifica config.env")
        return None, None
    
    return api_key, api_secret
def connect_to_binance():
    """ Establece conexión con Binance usando API KEY y SECRET. """
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")

    if not api_key or not api_secret:
        logging.error("❌ No se encontraron credenciales. Verifica config.env")
        return None

    try:
        client = Client(api_key, api_secret)
        client.ping()  # Verifica conexión activa
        logging.info("✅ Conexión exitosa con Binance.")
        return client
    except Exception as e:
        logging.error(f"❌ Error al conectar con Binance: {e}")
        return None


def get_historical_data(client, symbol="ETHUSDT", interval="1m", limit=5000, retries=3):
    """Obtiene datos históricos desde Binance con validaciones, reconexión y salida como DataFrame."""
    valid_intervals = ["1m", "3m", "5m", "15m", "1h", "1d"]
    if interval not in valid_intervals:
        logging.error(f"❌ Intervalo no válido: {interval}. Intervalos permitidos: {valid_intervals}")
        return pd.DataFrame()  # 🚀 Retorno seguro como DataFrame vacío

    logging.info(f"📌 Solicitando datos históricos ({limit} registros) desde Binance...")
    all_data = []

    for attempt in range(retries):
        try:
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)

            # 🚀 Validar que los datos obtenidos no estén vacíos ni sean insuficientes
            if not klines or len(klines) < 52:
                logging.warning(f"⚠️ Datos insuficientes ({len(klines) if klines else 0}) en intento {attempt + 1}. Reintentando...")
                time.sleep(2)
                continue

            all_data.extend(klines)
            if len(all_data) >= limit:  # 🔹 Detener cuando tenemos suficientes registros
                break

        except Exception as e:
            logging.error(f"❌ Error al obtener datos históricos: {e}")
            time.sleep(2)

    # 🚀 Convertir lista a DataFrame con estructura correcta
    num_registros = len(all_data)
    logging.debug(f"📊 Total de registros obtenidos antes de cálculos: {num_registros}")

    if num_registros < 52:
        logging.warning(f"⚠️ Registros insuficientes para cálculos ({num_registros}). Se generarán datos simulados.")
        return generar_datos_simulados()

    df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume", "extra1", "extra2", "extra3", "extra4", "extra5", "extra6"])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]  # 🔍 Filtrar solo las columnas necesarias
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")  # Convertir timestamp a datetime
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)  # Convertir valores numéricos

    logging.info(f"✅ Datos históricos listos: {len(df)} registros.")
    return df

def generar_datos_simulados():
    """Genera datos simulados en caso de falla en Binance."""
    logging.warning("⚠️ Generando datos simulados para pruebas...")

    fechas = pd.date_range(end=pd.Timestamp.now(), periods=5000, freq="1min")  
    precios_simulados = [1800 + i * 2 + (5 - i % 10) for i in range(5000)]

    simulated_data = [
        {
            "timestamp": fecha.timestamp(),
            "open": precio,
            "high": precio + 2,
            "low": precio - 2,
            "close": precio,
            "volume": 5000 + (i % 10) * 50
        }
        for i, (fecha, precio) in enumerate(zip(fechas, precios_simulados))
    ]

    logging.info(f"✅ Datos simulados generados: {len(simulated_data)} registros.")
    return simulated_data
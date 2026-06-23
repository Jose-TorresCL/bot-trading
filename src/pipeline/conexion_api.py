"""
conexion_api.py
---------------
Funciones para conectar con la API de Binance, obtener datos históricos y manejar credenciales.
Incluye validación de credenciales, manejo de errores y generación de datos simulados para pruebas.

Notas:
- Las funciones `verificar_credenciales` y `generar_datos_simulados` NO se usan directamente en el flujo principal,
  pero se mantienen para pruebas, debug o como fallback en caso de error.
"""

import os
import logging
import time
from pathlib import Path
from typing import Any
import pandas as pd
from binance.client import Client
from dotenv import load_dotenv

# Raiz del proyecto: este archivo vive en src/pipeline/, subir 2 niveles.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Cargar variables de entorno desde config.env (en carpeta data), anclado a la
# raiz del proyecto para no depender del directorio de trabajo actual (CWD).
# Esto evita que la carga de credenciales falle silenciosamente cuando otro
# proceso (p. ej. el agente Lautaro) arranca el bot desde otra ruta.
load_dotenv(_PROJECT_ROOT / "data" / "config.env")

# Configuración de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def verificar_credenciales():
    """
    [NO USADA EN EL FLUJO PRINCIPAL]
    Verifica si las credenciales de Binance están correctamente configuradas.
    Se mantiene para debug o pruebas manuales.
    """
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    # No imprimir nunca fragmentos de credenciales por stdout: si Lautaro captura
    # la salida para responder al usuario o por Telegram, se filtrarian.
    logger.debug("Credenciales API cargadas: key=%s secret=%s",
                 "OK" if api_key else "FALTA",
                 "OK" if api_secret else "FALTA")
    if not api_key or not api_secret:
        logging.error("❌ No se encontraron credenciales. Verifica data/config.env")
        return None, None
    return api_key, api_secret

def connect_to_binance():
    """
    Establece conexión con Binance usando API KEY y SECRET.
    """
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    if not api_key or not api_secret:
        logging.error("❌ No se encontraron credenciales. Verifica data/config.env")
        return None
    try:
        client = Client(api_key, api_secret)
        client.ping()  # Verifica conexión activa
        logging.info("✅ Conexión exitosa con Binance.")
        return client
    except Exception as e:
        logging.error(f"❌ Error al conectar con Binance: {e}")
        return None

def generar_datos_simulados(periods: int = 1500, freq: str = "1min") -> pd.DataFrame:
    """
    Genera un DataFrame con datos simulados y timestamps UTC.
    """
    logger.warning("Cliente API no disponible o datos insuficientes: generando datos simulados (%d filas).", periods)
    fechas = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=periods, freq=freq)
    base = 1000.0
    precios = [base + (i * 0.01) + ((-1) ** i) * 0.2 for i in range(periods)]
    df = pd.DataFrame({
        "timestamp": (fechas.view("int64") // 10**6),  # ms
        "open": precios,
        "high": [p + 0.5 for p in precios],
        "low": [p - 0.5 for p in precios],
        "close": precios,
        "volume": [100 + (i % 10) for i in range(periods)],
        "symbol": None
    })
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.reset_index(drop=True)

def _normalize_df_from_api(all_data: Any) -> pd.DataFrame:
    """
    Convierte la salida de la API en DataFrame y normaliza timestamps y tipos.
    Acepta listas de listas (klines), listas de dicts o DataFrame.
    """
    if isinstance(all_data, pd.DataFrame):
        df = all_data.copy()
    else:
        try:
            df = pd.DataFrame(all_data)
        except Exception:
            return pd.DataFrame()

    # Normalizar nombres de columna de timestamp
    for col in ("timestamp", "open_time", "time", "date"):
        if col in df.columns and "timestamp" not in df.columns:
            df = df.rename(columns={col: "timestamp"})
            break

    if "timestamp" not in df.columns:
        return pd.DataFrame()

    # Detectar y convertir unidades (ms/s) o strings
    try:
        sample = df["timestamp"].dropna().iloc[0]
        if pd.api.types.is_numeric_dtype(df["timestamp"]):
            max_ts = int(df["timestamp"].abs().max())
            unit = "ms" if max_ts > 10**12 else "s"
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit=unit, errors="coerce", utc=True)
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype(str).str.strip(), errors="coerce", utc=True)
    except Exception:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

    df = df.dropna(subset=["timestamp"])

    # Asegurar columnas OHLCV y tipos numéricos
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        else:
            df[c] = 0.0

    return df.reset_index(drop=True)[["timestamp", "open", "high", "low", "close", "volume"] + ([c for c in df.columns if c not in ["timestamp","open","high","low","close","volume"]])]

def get_historical_data(client, symbol: str = "ETHUSDT", interval: str = "1m", limit: int = 1500, retries: int = 3, startTime: int | None = None, endTime: int | None = None) -> pd.DataFrame:
    """
    Obtiene datos históricos desde el cliente (p.ej. Binance). Devuelve siempre pd.DataFrame.
    Si client es None o la respuesta no es adecuada, retorna datos simulados.
    """
    valid_intervals = {"1m", "3m", "5m", "15m", "1h", "1d"}
    if interval not in valid_intervals:
        logger.error("Intervalo no válido: %s", interval)
        return pd.DataFrame()

    if client is None:
        return generar_datos_simulados(limit, freq="1min" if interval.endswith("m") else "1H")

    all_data = []
    for attempt in range(1, retries + 1):
        try:
            # Manejar clientes que devuelven listas o DataFrame
            klines = getattr(client, "get_klines", None)
            if callable(klines):
                # pasar startTime/endTime si están disponibles (ms epoch)
                kwargs = {"symbol": symbol, "interval": interval, "limit": limit}
                if startTime is not None:
                    kwargs["startTime"] = int(startTime)
                if endTime is not None:
                    kwargs["endTime"] = int(endTime)
                resp = client.get_klines(**kwargs)
            else:
                # fallback: intentar método genérico
                resp = client.get_historical(symbol=symbol, interval=interval, limit=limit) if hasattr(client, "get_historical") else None

            if resp is None:
                logger.warning("Intento %d: respuesta nula para %s. Reintentando...", attempt, symbol)
                time.sleep(1)
                continue

            # Añadir respuesta (lista/dict/DataFrame)
            if isinstance(resp, list):
                all_data.extend(resp)
            elif isinstance(resp, pd.DataFrame):
                all_data.extend(resp.to_dict(orient="records"))
            else:
                # si es iterador o similar
                try:
                    all_data.extend(list(resp))
                except Exception:
                    logger.warning("Respuesta de API en formato inesperado. Intento %d", attempt)

            if len(all_data) >= limit:
                break
        except Exception as e:
            logger.error("Error obteniendo datos históricos (intento %d): %s", attempt, e)
            time.sleep(1)

    if not all_data or len(all_data) < 52:
        logger.warning("Datos insuficientes (%d registros). Usando simulados.", len(all_data))
        return generar_datos_simulados(limit, freq="1min" if interval.endswith("m") else "1H")

    df = _normalize_df_from_api(all_data)
    if df.empty:
        return generar_datos_simulados(limit, freq="1min" if interval.endswith("m") else "1H")

    logger.info("Datos históricos obtenidos: %d registros para %s %s", len(df), symbol, interval)
    return df
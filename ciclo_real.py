import logging
from conexion_api import get_historical_data, connect_to_binance
from estrategias_bot import estrategia_compra, estrategia_venta, registrar_decisiones
from gestor_indicadores import calcular_todos_los_indicadores, evaluar_indicadores

# Configuración de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def obtener_datos_historicos(symbol="ETHUSDT", limit=500):
    """Obtiene datos históricos solo desde Binance."""
    logging.info("🌍 Conectando a Binance para obtener datos reales...")
    client = connect_to_binance()
    if not client:
        logging.error("❌ No se pudo conectar a Binance. Se detiene el bot.")
        return None
    historical_data = get_historical_data(client, symbol=symbol, limit=limit)

    if (
        historical_data is None
        or (hasattr(historical_data, "empty") and historical_data.empty)
        or len(historical_data) < 50
    ):
        logging.error("❌ No se pudieron obtener suficientes datos históricos.")
        return None

    logging.info(f"✅ Datos históricos obtenidos con {len(historical_data)} registros.")
    return historical_data

def ejecutar_ciclo():
    """ Ejecuta un ciclo del bot en modo paper trading (solo simula operaciones). """
    logging.info("🔄 Iniciando ciclo de trading...")

    historical_data = obtener_datos_historicos()
    if (
        historical_data is None
        or (hasattr(historical_data, "empty") and historical_data.empty)
        or len(historical_data) < 50
    ):
        logging.error("❌ No se pudieron obtener suficientes datos históricos para el ciclo.")
        return

    indicadores_lista = calcular_todos_los_indicadores(historical_data)
    if not indicadores_lista:
        logging.warning("⚠️ No se generaron indicadores válidos.")
        return

    recomendaciones = evaluar_indicadores(indicadores_lista)
    logging.info(f"📊 Recomendaciones basadas en indicadores: {recomendaciones}")

    # Acceso seguro al último registro
    if hasattr(historical_data, "iloc"):
        ultima_data = historical_data.iloc[-1]
        precio_actual = ultima_data["close"]
    else:
        ultima_data = historical_data[-1]
        precio_actual = ultima_data.get("close", 0)

    # Usar solo el último conjunto de indicadores para la decisión
    ultimo_indicador = indicadores_lista[-1] if indicadores_lista else {}

    # Validar que los indicadores clave no sean None
    indicadores_clave = ["RSI", "MACD", "ATR"]  # Ajusta según tus estrategias
    if not (isinstance(ultimo_indicador, dict) and ultimo_indicador and all(ultimo_indicador.get(k) is not None for k in indicadores_clave)):
        logging.warning("⚠️ Indicadores clave no disponibles o no válidos para estrategia.")
        decision = None
    else:
        decision = tomar_decision(ultimo_indicador)

    if decision:
        registrar_decisiones(decision, precio_actual, ultimo_indicador, "simulada")
    logging.info("✅ Ciclo de trading completado.")
    return historical_data

def tomar_decision(indicadores):
    """Evalúa la estrategia de compra o venta y devuelve la decisión."""
    if estrategia_compra(indicadores):
        logging.info("✅ Oportunidad de compra detectada (SIMULADA).")
        return "compra"
    elif estrategia_venta(indicadores):
        logging.info("✅ Oportunidad de venta detectada (SIMULADA).")
        return "venta"
    return None

if __name__ == "__main__":
    ejecutar_ciclo()  # 🔹 Solo paper trading con datos reales
import logging
import time
import json
import os
import pandas as pd
from conexion_api import get_historical_data, connect_to_binance
from estrategias_bot1 import estrategia_compra, estrategia_venta, registrar_decisiones, gestion_riesgo
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

def ejecutar_ciclo_paper_trading(intervalo=60):
    # Cargar parámetros óptimos
    with open("parametros_seleccionados.json") as f:
        params = json.load(f)

    # Estado inicial
    saldo = 10000  # saldo simulado inicial
    operacion_abierta = False
    precio_entrada = None
    timestamp_entrada = None
    historial = []

    # Si existe un historial previo, cargarlo
    if os.path.exists("historial_papertrading.json"):
        with open("historial_papertrading.json") as f:
            historial = json.load(f)

    logger = logging.getLogger()
    logger.info("🔄 Iniciando ciclo de paper trading...")

    while True:
        try:
            client = connect_to_binance()
            datos = get_historical_data(client, symbol="ETHUSDT", interval="1m", limit=200)
            df = pd.DataFrame(datos)
            if df.empty:
                logger.warning("No hay datos nuevos.")
                time.sleep(intervalo)
                continue

            indicadores = calcular_todos_los_indicadores(df)[-1]  # último registro
            precio_actual = df["close"].iloc[-1]
            timestamp_actual = df["timestamp"].iloc[-1]

            if not operacion_abierta:
                resultado, usados = estrategia_compra(
                    indicadores,
                    rsi_limit=params["RSI_LIMIT_COMPRA"],
                    adx_limit=params["ADX_LIMIT"],
                    min_votes=params["MIN_VOTES"]
                )
                if resultado:
                    operacion_abierta = True
                    precio_entrada = precio_actual
                    timestamp_entrada = timestamp_actual
                    logger.info(f"🟢 COMPRA SIMULADA a {precio_entrada}")
            else:
                # Gestión de riesgo: SL y TP
                sl = params["SL_MULT"]
                tp = params["TP_MULT"]
                if precio_actual <= precio_entrada - sl:
                    ganancia = -sl
                    logger.info(f"🛑 Stop Loss alcanzado. Venta simulada a {precio_actual}, pérdida: {ganancia}")
                    motivo = "SL"
                elif precio_actual >= precio_entrada + tp:
                    ganancia = tp
                    logger.info(f"🎯 Take Profit alcanzado. Venta simulada a {precio_actual}, ganancia: {ganancia}")
                    motivo = "TP"
                else:
                    # Aquí puedes agregar lógica para venta por señal
                    resultado, usados = estrategia_venta(
                        indicadores,
                        rsi_limit=params["RSI_LIMIT_VENTA"],
                        adx_limit=params["ADX_LIMIT"],
                        min_votes=params["MIN_VOTES"]
                    )
                    if resultado:
                        ganancia = precio_actual - precio_entrada
                        motivo = "Señal"
                        logger.info(f"🔴 VENTA SIMULADA a {precio_actual} | Ganancia: {ganancia:.2f} | Motivo: {motivo}")
                        logger.info(f"Saldo simulado actual: {saldo:.2f} USDT")
                        logger.info(f"Historial de operaciones: {historial[-1]}")

                        # Registrar operación
                        operacion = {
                            "tipo": "venta",
                            "precio_entrada": precio_entrada,
                            "precio_salida": precio_actual,
                            "ganancia": ganancia,
                            "timestamp_entrada": timestamp_entrada,
                            "timestamp_salida": timestamp_actual,
                            "motivo_cierre": "TP" if ganancia > 0 else "SL",
                            "saldo_post": saldo
                        }
                        historial.append(operacion)
                        with open("historial_papertrading.json", "w") as f:
                            json.dump(historial, f, indent=4)

                        operacion_abierta = False
                        precio_entrada = None
                        timestamp_entrada = None
                    else:
                        # Gestión de riesgo avanzada
                        riesgo = gestion_riesgo(
                            precio_compra=precio_entrada,
                            precio_actual=precio_actual,
                            indicadores=indicadores,
                            mejor_precio=None,
                            modo="compra",
                            sl_mult=params["SL_MULT"],
                            tp_mult=params["TP_MULT"],
                            trailing_stop=True,
                            atr_min=params["ATR_MIN"]  # <-- agrega esto
                        )
                        if riesgo and riesgo.get("accion") == "vender":
                            ganancia = precio_actual - precio_entrada
                            motivo = riesgo.get("motivo")
                            logger.info(f"🔴 VENTA SIMULADA a {precio_actual} | Ganancia: {ganancia:.2f} | Motivo: {motivo}")
                            logger.info(f"Saldo simulado actual: {saldo:.2f} USDT")
                            logger.info(f"Historial de operaciones: {historial[-1]}")

                            # Registrar operación
                            operacion = {
                                "tipo": "venta",
                                "precio_entrada": precio_entrada,
                                "precio_salida": precio_actual,
                                "ganancia": ganancia,
                                "timestamp_entrada": timestamp_entrada,
                                "timestamp_salida": timestamp_actual,
                                "motivo_cierre": "TP" if ganancia > 0 else "SL",
                                "saldo_post": saldo
                            }
                            historial.append(operacion)
                            with open("historial_papertrading.json", "w") as f:
                                json.dump(historial, f, indent=4)

                            operacion_abierta = False
                            precio_entrada = None
                            timestamp_entrada = None
                        else:
                            time.sleep(intervalo)
                            continue

                saldo += ganancia

        except Exception as e:
            logger.error(f"Error en ciclo de paper trading: {e}")

        time.sleep(intervalo)

if __name__ == "__main__":
    ejecutar_ciclo_paper_trading()
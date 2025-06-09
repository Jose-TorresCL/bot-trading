import logging
import json
import numpy as np
import pandas as pd
from conexion_api import get_historical_data, connect_to_binance
from funciones_generales import inicializar_bot
from ciclo_real import ejecutar_ciclo_paper_trading, ejecutar_ciclo
from carga_datos import obtener_datos_historicos, guardar_datos_csv, cargar_datos_csv
from validacion_datos import validar_datos
from transformacion_datos import transformar_datos
from gestor_indicadores import calcular_todos_los_indicadores
from estrategias_bot1 import estrategia_compra, estrategia_venta, registrar_decisiones
from utilidades import log_operation_json
# 🚀 ML opcional
try:
    from caracteristicas_ML import generar_features, train_random_forest, predict_price
    ML_ENABLED = True
except ImportError:
    logging.warning("⚠️ Módulo ML no encontrado. Ejecutando sin predicción.")
    ML_ENABLED = False

# 🔹 Configuración de logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("bot.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # <-- Cambiado aquí
console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)

logger.handlers = []
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def main():
    print("=======================================")
    print("      BOT DE TRADING AUTOMÁTICO")
    print("=======================================")
    print("Selecciona el modo de operación:")
    print("1. Paper Trading (simulación en tiempo real)")
    print("2. Análisis normal (solo señales y análisis)")
    modo = input("Elige una opción (1 o 2): ").strip()

    if modo == "1":
        print("🚦 Iniciando bot en modo PAPER TRADING (simulación en tiempo real)...")
        ejecutar_ciclo_paper_trading(intervalo=60)
    elif modo == "2":
        print("🚦 Iniciando bot en modo normal (análisis y señales)...")
        inicializar_bot()

        # 🔗 Conexión con Binance
        client = connect_to_binance()
        if client is None:
            logging.error("❌ No se pudo conectar a Binance.")
            return

        # 📥 Descargar datos históricos
        symbol = "ETHUSDT"
        interval = "1m"
        limit = 3000
        logging.info(f"📥 Obteniendo {limit} registros de {symbol}...")

        # 🔥 PASO 1: Cargar datos históricos desde archivo CSV
        historical_data = obtener_datos_historicos("historial_trading.csv")
        logging.info(f"📊 Registros obtenidos desde CSV: {len(historical_data)}")

        # 🔥 PASO 2: Obtener datos en tiempo real desde Binance
        live_data = get_historical_data(client, symbol=symbol, interval=interval, limit=limit)
        logging.info(f"📊 Registros obtenidos en tiempo real: {len(live_data)}")

        # 🔥 PASO 3: Fusionar datos históricos con datos en tiempo real
        df_historical = pd.DataFrame(historical_data)
        df_live = pd.DataFrame(live_data)

        # Asegúrate de que las columnas coincidan
        missing_cols = set(df_historical.columns) ^ set(df_live.columns)
        if missing_cols:
            logging.warning(f"⚠️ Diferencia de columnas entre históricos y live: {missing_cols}")

        df_combined = pd.concat([df_historical, df_live], ignore_index=True)
        df_combined = df_combined.drop_duplicates()
        logging.info(f"📊 Registros en df_combined antes de validación: {len(df_combined)}")
        logging.info(f"🔍 Columnas en df_combined: {df_combined.columns.tolist()}")
        logging.info(f"📊 Primeros 5 registros:\n{df_combined.head()}")

        # Validación
        df_validated = validar_datos(df_combined, required_fields=["open", "high", "low", "close", "price", "volume"])
        if df_validated is None or df_validated.empty:
            logging.error("❌ No hay datos válidos después de la validación.")
            return

        # Cálculo de indicadores
        indicadores_lista = calcular_todos_los_indicadores(df_validated)
        ultima_indicacion = indicadores_lista[-1] if indicadores_lista else {}

        # Validar que los indicadores clave no sean None
        indicadores_clave = ["RSI", "MACD", "ATR"]  # Ajusta según tus estrategias
        if not (isinstance(ultima_indicacion, dict) and ultima_indicacion and all(ultima_indicacion.get(k) is not None for k in indicadores_clave)):
            logging.warning("⚠️ Indicadores clave no disponibles o no válidos para estrategia.")
            return

        # 🧠 Evaluación de estrategia
        try:
            precio_actual = df_validated.iloc[-1]["close"]
            if estrategia_compra(ultima_indicacion):
                logging.info(f"🟢 Señal de COMPRA detectada a ${precio_actual}")
                registrar_decisiones("compra", precio_actual, ultima_indicacion, "aprobado")
                log_operation_json("💡 Decisión de compra", "INFO", {
                    "precio": precio_actual,
                    "indicadores": ultima_indicacion
                })

            elif estrategia_venta(ultima_indicacion):
                logging.info(f"🔴 Señal de VENTA detectada a ${precio_actual}")
                registrar_decisiones("venta", precio_actual, ultima_indicacion, "aprobado")
                log_operation_json("💡 Decisión de venta", "INFO", {
                    "precio": precio_actual,
                    "indicadores": ultima_indicacion
                })

            else:
                logging.info("⚠️ No hay condiciones claras de compra/venta.")
        except Exception as e:
            logging.error(f"❌ Error al ejecutar estrategias: {e}")
            return

        # 🔄 Guardar nuevos datos históricos al CSV (solo los que no están ya)
        nuevos_registros = df_live[~df_live['timestamp'].isin(df_historical['timestamp'])]
        if not nuevos_registros.empty:
            guardar_datos_csv(nuevos_registros.to_dict(orient="records"), filename="historial_trading.csv")
            logging.info(f"✅ {len(nuevos_registros)} nuevos registros añadidos al historial.")
        else:
            logging.info("ℹ️ No hay nuevos registros para añadir al historial.")

        # 🔄 Continuar ciclo
         ejecutar_ciclo()
    else:
        print("Opción no válida. Por favor, ejecuta de nuevo el programa.")

if __name__ == "__main__":
    main()

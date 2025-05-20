import os
import logging
import pandas as pd
import matplotlib.pyplot as plt
import json
from collections import Counter
from conexion_api import get_historical_data, connect_to_binance
from gestor_indicadores import calcular_todos_los_indicadores
from estrategias_bot import estrategia_venta, registrar_decisiones, gestion_riesgo
import webbrowser

logger = logging.getLogger(__name__)

# Convierte todos los Timestamps a string
def convertir_timestamps_a_str(obj):
    import pandas as pd
    import numpy as np
    import datetime
    if isinstance(obj, dict):
        return {k: convertir_timestamps_a_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convertir_timestamps_a_str(i) for i in obj]
    elif isinstance(obj, (pd.Timestamp, datetime.datetime, datetime.date)):
        return str(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj

# Configuración avanzada de logs: archivo + terminal
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)

file_handler = logging.FileHandler("estrategias.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

if not logger.hasHandlers():
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)




def cargar_y_combinar_datos(csv_file, client, symbol="ETHUSDT", interval="1m"):
    """
    Carga el CSV de historial, obtiene datos en tiempo real y los fusiona.
    Si existe historial_trading_acum.csv, solo carga ese archivo y no consulta Binance.
    """
    acum_file = "historial_trading_acum.csv"
    if os.path.exists(acum_file):
        try:
            df_acum = pd.read_csv(acum_file)
            logger.info(f"✅ Datos cargados solo desde {acum_file}: {len(df_acum)} registros.")
            return df_acum
        except Exception as e:
            logger.error(f"❌ Error al leer el archivo acumulado: {e}")
            return None

    try:
        # Validar archivo CSV
        if not os.path.exists(csv_file):
            logger.error(f"❌ El archivo {csv_file} no existe.")
            return None
        
        try:
            df_historical = pd.read_csv(csv_file)
            if df_historical.empty:
                logger.warning(f"⚠️ El archivo {csv_file} está vacío.")
                return None
        except Exception as e:
            logger.error(f"❌ Error al leer el CSV: {e}")
            return None
        
        logger.info(f"✅ Datos históricos cargados: {len(df_historical)} registros.")

        # Obtener datos en tiempo real
        try:
            live_data = get_historical_data(client, symbol=symbol, interval=interval)  # Eliminamos 'limit'
            df_live = pd.DataFrame(live_data)
            if df_live.empty:
                logger.warning("⚠️ No se obtuvieron datos en tiempo real, se utilizarán solo datos históricos.")
                df_live = pd.DataFrame(columns=df_historical.columns)
        except Exception as e:
            logger.error(f"❌ Error al obtener datos en tiempo real: {e}")
            df_live = pd.DataFrame(columns=df_historical.columns)
        
        logger.info(f"✅ Datos en tiempo real obtenidos: {len(df_live)} registros.")

        # Homogeneizar columnas antes de fusionar
        all_cols = sorted(set(df_historical.columns) | set(df_live.columns))
        df_historical = df_historical.reindex(columns=all_cols)
        df_live = df_live.reindex(columns=all_cols)

        # Fusionar y eliminar duplicados
        df_combined = pd.concat([df_historical, df_live], ignore_index=True).drop_duplicates()
        logger.info(f"✅ Datos combinados finales: {len(df_combined)} registros.")

        # Convertir columnas de precios a float
        price_cols = ["close", "high", "low", "open", "price"]
        for col in price_cols:
            if col in df_combined.columns:
                df_combined[col] = pd.to_numeric(df_combined[col], errors="coerce")

        # Guardar datos actualizados para backtesting
        df_combined.to_csv(csv_file, index=False)

        # Acumular en historial total sin recargar todo el archivo
        acum_file = "historial_trading_acum.csv"
        if os.path.exists(acum_file):
            try:
                df_nuevos = df_combined.copy()
                df_nuevos.to_csv(acum_file, mode="a", header=False, index=False)
            except Exception as e:
                logger.error(f"❌ Error al actualizar el archivo acumulado: {e}")
        else:
            df_combined.to_csv(acum_file, index=False)

        return df_combined

    except Exception as e:
        logger.error(f"❌ Error al cargar y combinar datos: {e}")
        return None

def estrategia_compra(indicadores, rsi_limit=60, min_votes=1):
    rsi = indicadores.get("RSI")
    resultado = rsi is not None and rsi < rsi_limit
    usados = []
    if resultado:
        usados.append("RSI")
    return resultado, usados

def backtesting(df):
    """Ejecuta el backtesting sobre el DataFrame completo y exporta resultados y métricas."""
    indicadores_lista = calcular_todos_los_indicadores(df)
    if not isinstance(indicadores_lista, list):
        logger.error("❌ calcular_todos_los_indicadores no retornó una lista.")
        return []
    resultados = []
    posicion_abierta = False
    precio_compra = None
    duraciones = []
    mejor_precio = None  # Para trailing stop
    stops_activados = 0

    for i, indicadores in zip(df.index, indicadores_lista):
        if not isinstance(indicadores, dict):
            logger.error(f"❌ Indicadores inválidos en fila {i}: {indicadores}")
            continue
        precio_actual = df.loc[i, "close"]
        timestamp = df.loc[i, "timestamp"] if "timestamp" in df.columns else i
        tipo_mercado = df.loc[i, "market_type"] if "market_type" in df.columns else "desconocido"
        if not posicion_abierta:
            resultado_compra, usados_compra = estrategia_compra(indicadores)
            if resultado_compra:
                registrar_decisiones("compra", precio_actual, indicadores, "simulada")
                resultados.append({
                    "tipo": "compra",
                    "precio": precio_actual,
                    "indice": i,
                    "timestamp": timestamp,
                    "tipo_mercado": tipo_mercado,
                    "indicadores_usados": usados_compra
                })
                posicion_abierta = True
                precio_compra = precio_actual
                compra_indice = i
                mejor_precio = precio_actual  # Inicializa mejor precio
        elif posicion_abierta:
            # Actualiza mejor_precio para trailing stop
            mejor_precio = max(mejor_precio, precio_actual) if mejor_precio is not None else precio_actual

            # Gestión de riesgo dinámica
            riesgo = gestion_riesgo(precio_compra, precio_actual, indicadores, sl_mult=1.5, tp_mult=3, trailing_stop=True, mejor_precio=mejor_precio)
            if riesgo in ["vender_por_perdida", "vender_por_ganancia"]:
                if riesgo == "vender_por_perdida":
                    stops_activados += 1
                registrar_decisiones("venta", precio_actual, indicadores, riesgo)
                duracion = i - compra_indice if 'compra_indice' in locals() else None
                resultados.append({
                    "tipo": "venta",
                    "precio": precio_actual,
                    "indice": i,
                    "ganancia": precio_actual - precio_compra if precio_compra is not None else None,
                    "timestamp": timestamp,
                    "duracion": duracion,
                    "tipo_mercado": tipo_mercado,
                    "indicadores_usados": []
                })
                if duracion is not None:
                    duraciones.append(duracion)
                posicion_abierta = False
                precio_compra = None
                mejor_precio = None
                continue  # Salta a la siguiente iteración

            resultado_venta, usados_venta = estrategia_venta(indicadores)
            if resultado_venta:
                registrar_decisiones("venta", precio_actual, indicadores, "simulada")
                duracion = i - compra_indice if 'compra_indice' in locals() else None
                resultados.append({
                    "tipo": "venta",
                    "precio": precio_actual,
                    "indice": i,
                    "ganancia": precio_actual - precio_compra if precio_compra is not None else None,
                    "timestamp": timestamp,
                    "duracion": duracion,
                    "tipo_mercado": tipo_mercado,
                    "indicadores_usados": usados_venta
                })
                if duracion is not None:
                    duraciones.append(duracion)
                posicion_abierta = False
                precio_compra = None
                mejor_precio = None

    # Métricas extendidas con validaciones
    total_compras = sum(1 for r in resultados if r["tipo"] == "compra")
    total_ventas = sum(1 for r in resultados if r["tipo"] == "venta")
    ganancias = [r["ganancia"] for r in resultados if r["tipo"] == "venta" and r.get("ganancia") is not None]
    operaciones_ganadoras = [g for g in ganancias if g > 0]
    operaciones_perdedoras = [g for g in ganancias if g <= 0]
    winrate = (len(operaciones_ganadoras) / len(ganancias) * 100) if ganancias else 0
    profit_factor = (sum(operaciones_ganadoras) / abs(sum(operaciones_perdedoras))) if operaciones_perdedoras else float('inf')
    equity_curve = pd.Series(ganancias).cumsum() if ganancias else pd.Series([0])
    max_drawdown = (equity_curve.cummax() - equity_curve).max() if not equity_curve.empty else 0
    total_ganancia = sum(ganancias)
    avg_gain = (sum(operaciones_ganadoras) / len(operaciones_ganadoras)) if operaciones_ganadoras else 0
    avg_loss = (sum(operaciones_perdedoras) / len(operaciones_perdedoras)) if operaciones_perdedoras else 0
    expectancy = ((winrate/100) * avg_gain + (1 - winrate/100) * avg_loss) if ganancias else 0
    avg_duration = sum(duraciones) / len(duraciones) if duraciones else 0

    num_ganadoras = len(operaciones_ganadoras)
    num_perdedoras = len(operaciones_perdedoras)
    porc_ganadoras = (num_ganadoras / len(ganancias) * 100) if ganancias else 0
    porc_perdedoras = (num_perdedoras / len(ganancias) * 100) if ganancias else 0

    avg_gain = (sum(operaciones_ganadoras) / num_ganadoras) if num_ganadoras else 0
    avg_loss = (sum(operaciones_perdedoras) / num_perdedoras) if num_perdedoras else 0

    logger.info(f"📊 Resumen Backtesting - Compras: {total_compras}, Ventas: {total_ventas}, Total operaciones: {len(resultados)}")
    logger.info(f"📈 Ganancia total simulada: {total_ganancia:.2f}")
    logger.info(f"🏆 Winrate: {winrate:.2f}%")
    logger.info(f"💰 Profit Factor: {profit_factor:.2f}")
    logger.info(f"📉 Drawdown máximo: {max_drawdown:.2f}")
    logger.info(f"📊 Expectancy: {expectancy:.2f}")
    logger.info(f"⏳ Duración promedio de trades: {avg_duration:.2f} velas")
    logger.info(f"✅ Backtesting completado. Total operaciones: {len(resultados)}")

    # Mostrar resumen en la terminal
    resumen_str = (
        f"\n--- RESUMEN BACKTESTING ---\n"
        f"Total compras: {total_compras}\n"
        f"Total ventas: {total_ventas}\n"
        f"Total operaciones: {len(resultados)}\n"
        f"Ganancia total simulada: {total_ganancia:.2f}\n"
        f"Winrate: {winrate:.2f}%\n"
        f"Profit Factor: {profit_factor:.2f}\n"
        f"Drawdown máximo: {max_drawdown:.2f}\n"
        f"Expectancy: {expectancy:.2f}\n"
        f"Duración promedio de trades: {avg_duration:.2f} velas\n"
        f"Operaciones ganadoras: {num_ganadoras} ({porc_ganadoras:.2f}%) | Promedio: {avg_gain:.2f}\n"
        f"Operaciones perdedoras: {num_perdedoras} ({porc_perdedoras:.2f}%) | Promedio: {avg_loss:.2f}\n"
        f"---------------------------"
    )
    print(resumen_str)
    print(f"Total stops-loss activados: {stops_activados}")

    # Exportar resultados a CSV solo si hay resultados
    if resultados:
        pd.DataFrame(resultados).to_csv("resultados_backtesting.csv", index=False)
        # Acumular en archivo histórico de operaciones
        acum_ops = "acumulado_operaciones.csv"
        if os.path.exists(acum_ops):
            pd.DataFrame(resultados).to_csv(acum_ops, mode='a', header=False, index=False)
        else:
            pd.DataFrame(resultados).to_csv(acum_ops, index=False)
        resumen = {
            "total_compras": total_compras,
            "total_ventas": total_ventas,
            "ganancia_total": total_ganancia,
            "winrate": winrate,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "expectancy": expectancy,
            "avg_duration": avg_duration
        }
        pd.DataFrame([resumen]).to_csv("resumen_backtesting.csv", index=False)
        logger.info("✅ Resultados exportados a resultados_backtesting.csv, resumen_backtesting.csv y acumulado_operaciones.csv")
        # Graficar equity curve y drawdown
        if ganancias:
            plot_equity_and_drawdown(ganancias)
            plot_histograma_ganancias(ganancias)
            plot_trades_on_price(df, resultados)
            webbrowser.open("equity_curve.png")
            webbrowser.open("histograma_ganancias.png")
            webbrowser.open("trades_on_price.png")
    else:
        logger.warning("⚠️ No hay resultados para exportar.")

    # Analizar indicadores más frecuentes
    indicadores_ganadores = []
    indicadores_perdedores = []

    for r in resultados:
        if r["tipo"] == "venta" and r.get("ganancia") is not None:
            usados = r.get("indicadores_usados", [])
            if r["ganancia"] > 0:
                indicadores_ganadores.extend(usados)
            else:
                indicadores_perdedores.extend(usados)

    print("Indicadores más frecuentes en operaciones GANADORAS:", Counter(indicadores_ganadores).most_common())
    print("Indicadores más frecuentes en operaciones PERDEDORAS:", Counter(indicadores_perdedores).most_common())

    resumen = {
        "total_compras": total_compras,
        "total_ventas": total_ventas,
        "ganancia_total": total_ganancia,
        "winrate": winrate,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "expectancy": expectancy,
        "avg_duration": avg_duration
    }
    return resultados, resumen  # <-- Devuelve el resumen en vez de resultados

def plot_equity_and_drawdown(ganancias, filename="equity_curve.png"):
    if not ganancias:
        logger.warning("⚠️ No hay ganancias para graficar.")
        return
    equity_curve = pd.Series(ganancias).cumsum()
    drawdown = (equity_curve.cummax() - equity_curve)
    plt.figure(figsize=(12, 6))
    plt.subplot(2, 1, 1)
    plt.plot(equity_curve, label="Equity Curve", color="blue")
    plt.title("Evolución de Ganancia Acumulada")
    plt.ylabel("Ganancia acumulada")
    plt.legend()
    plt.grid()
    plt.subplot(2, 1, 2)
    plt.plot(drawdown, label="Drawdown", color="red")
    plt.title("Drawdown")
    plt.xlabel("Operación")
    plt.ylabel("Drawdown")
    plt.legend()
    plt.grid()
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()
    plt.close()
    logger.info(f"✅ Gráfico de equity y drawdown guardado en {filename}")

def plot_histograma_ganancias(ganancias, filename="histograma_ganancias.png"):
    if not ganancias:
        logger.warning("⚠️ No hay ganancias para graficar histograma.")
        return
    plt.figure(figsize=(8, 4))
    plt.hist(ganancias, bins=30, color="purple", alpha=0.7)
    plt.title("Histograma de Ganancias por Trade")
    plt.xlabel("Ganancia por operación")
    plt.ylabel("Frecuencia")
    plt.grid()
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()
    logger.info(f"✅ Histograma de ganancias guardado en {filename}")

def plot_trades_on_price(df, resultados, filename="trades_on_price.png"):
    if df.empty or not resultados:
        logger.warning("⚠️ No hay datos para graficar operaciones sobre el precio.")
        return
    plt.figure(figsize=(12, 5))
    plt.plot(df["close"], label="Precio Close", color="black", alpha=0.7)
    compras = [r["indice"] for r in resultados if r["tipo"] == "compra"]
    ventas = [r["indice"] for r in resultados if r["tipo"] == "venta"]
    plt.scatter(compras, df.loc[compras, "close"], marker="^", color="green", label="Compra", zorder=5)
    plt.scatter(ventas, df.loc[ventas, "close"], marker="v", color="red", label="Venta", zorder=5)
    plt.title("Operaciones de Compra/Venta sobre el Precio")
    plt.xlabel("Índice")
    plt.ylabel("Precio")
    plt.legend()
    plt.grid()
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()
    logger.info(f"✅ Gráfico de operaciones sobre el precio guardado en {filename}")

def mostrar_rango_temporal(df):
    """
    Imprime el rango temporal de los datos del DataFrame.
    Especifica el formato si lo conoces para evitar advertencias de pandas.
    """
    import pandas as pd
    time_col = None
    for col in ["timestamp", "open_time", "date", "time"]:
        if col in df.columns:
            time_col = col
            break

    if time_col is not None:
        try:
            ts_sample = df[time_col].iloc[0]
            if pd.api.types.is_numeric_dtype(df[time_col]):
                unit = 'ms' if int(ts_sample) > 1e12 else 's'
                df[time_col] = pd.to_datetime(df[time_col], unit=unit, errors='coerce')
                print(f"Columna {time_col} detectada como numérica, usando unit='{unit}' para conversión.")
            else:
                # Especifica el formato si lo sabes, por ejemplo "%Y-%m-%d %H:%M:%S"
                formato = "%Y-%m-%d %H:%M:%S"
                df[time_col] = pd.to_datetime(df[time_col], errors='coerce', format=formato)
                print(f"Columna {time_col} detectada como string, usando formato explícito: {formato}.")
        except Exception as e:
            print(f"Error al convertir la columna de tiempo: {e}")
            df[time_col] = pd.to_datetime(df[time_col], errors='coerce')

        start = df[time_col].min()
        end = df[time_col].max()
        print(f"\n⏳ Rango temporal de los datos: {start}  -->  {end}")
        print(f"📅 Duración total: {end - start}\n")
    else:
        print("No se encontró columna de tiempo en el DataFrame.")

if __name__ == "__main__":
    import logging
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # Archivo
    file_handler = logging.FileHandler("backtesting.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    # Consola solo WARNING+
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.handlers = []
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("🚀 Iniciando backtesting...")
    client = connect_to_binance()
    df = cargar_y_combinar_datos("historial_trading.csv", client)
    if df is not None:
        mostrar_rango_temporal(df)
        backtesting(df)
        decision = convertir_timestamps_a_str(df.to_dict(orient="records"))
        json.dump(decision, open("decision.json", "w"), indent=4)
        import json



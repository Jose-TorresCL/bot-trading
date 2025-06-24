import os
import logging
import pandas as pd
import matplotlib.pyplot as plt
import json
from collections import Counter
from conexion_api import get_historical_data, connect_to_binance
from gestor_indicadores import calcular_todos_los_indicadores
from estrategias_bot1 import estrategia_venta, estrategia_compra, registrar_decisiones, gestion_riesgo
import webbrowser
from config_estrategias import (
    RSI_LIMIT_COMPRA, MIN_VOTES_COMPRA,
    RSI_LIMIT_VENTA, MIN_VOTES_VENTA,
    SL_MULT, TP_MULT,
    ADX_LIMIT   # <-- Agrega esto
)

def configurar_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    if logger.hasHandlers():
        logger.handlers.clear()
    file_handler = logging.FileHandler("estrategias.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

logger = configurar_logging()

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

def cargar_y_combinar_datos(
    csv_file,
    client,
    symbol="ETHUSDT",
    interval="1m",
    limit=3000,
    acum_file="historial_trading_acum.csv",
    meses=6  # <-- Nuevo parámetro para rango de meses
):
    """
    Carga el CSV de historial, obtiene datos en tiempo real y los fusiona.
    Acumula todos los datos en historial_trading_acum.csv, sin duplicados.
    Filtra solo los últimos 'meses' meses de datos.
    """
    try:
        # Leer CSV histórico
        if not os.path.exists(csv_file):
            logger.error(f"❌ El archivo {csv_file} no existe.")
            return None
        try:
            df_historical = pd.read_csv(csv_file, low_memory=False)
            if df_historical.empty:
                logger.warning(f"⚠️ El archivo {csv_file} está vacío.")
                return None
        except Exception as e:
            logger.error(f"❌ Error al leer el CSV: {e}")
            return None
        logger.info(f"✅ Datos históricos cargados: {len(df_historical)} registros.")

        # Obtener datos en tiempo real
        try:
            live_data = get_historical_data(client, symbol=symbol, interval=interval, limit=limit)
            df_live = pd.DataFrame(live_data)
            if df_live.empty:
                logger.warning("⚠️ No se obtuvieron datos en tiempo real, se utilizarán solo datos históricos.")
                df_live = pd.DataFrame(columns=df_historical.columns)
        except Exception as e:
            logger.error(f"❌ Error al obtener datos en tiempo real: {e}")
            df_live = pd.DataFrame(columns=df_historical.columns)
        logger.info(f"✅ Datos en tiempo real obtenidos: {len(df_live)} registros.")

        # Homogeneizar columnas
        all_cols = sorted(set(df_historical.columns) | set(df_live.columns))
        df_historical = df_historical.reindex(columns=all_cols)
        df_live = df_live.reindex(columns=all_cols)

        # Fusionar y eliminar duplicados por clave (por ejemplo 'timestamp' y 'symbol')
        unique_keys = [col for col in ['timestamp', 'symbol', 'open_time'] if col in all_cols]
        if unique_keys:
            df_combined = pd.concat([df_historical, df_live], ignore_index=True)
            df_combined = df_combined.drop_duplicates(subset=unique_keys)
        else:
            df_combined = pd.concat([df_historical, df_live], ignore_index=True).drop_duplicates()
        logger.info(f"✅ Datos combinados finales: {len(df_combined)} registros.")

        # Convertir columnas de precios a float
        price_cols = ["close", "high", "low", "open", "price"]
        for col in price_cols:
            if col in df_combined.columns:
                df_combined[col] = pd.to_numeric(df_combined[col], errors="coerce")

        # Guardar combinado en el archivo original
        df_combined.to_csv(csv_file, index=False)

        # Procesar acumulado global
        if os.path.exists(acum_file):
            try:
                df_acum = pd.read_csv(acum_file, low_memory=False)
                # Eliminar duplicados al combinar
                if unique_keys:
                    df_total = pd.concat([df_acum, df_combined], ignore_index=True)
                    df_total = df_total.drop_duplicates(subset=unique_keys)
                else:
                    df_total = pd.concat([df_acum, df_combined], ignore_index=True).drop_duplicates()
                df_total.to_csv(acum_file, index=False)
                logger.info(f"✅ Actualizado {acum_file}: {len(df_total)} registros totales.")
            except Exception as e:
                logger.error(f"❌ Error al actualizar el archivo acumulado: {e}")
        else:
            df_combined.to_csv(acum_file, index=False)
            logger.info(f"✅ Creado archivo acumulado {acum_file}.")

        # --- FILTRAR SOLO LOS ÚLTIMOS 'meses' MESES ---
        if "timestamp" in df_combined.columns:
            df_combined["timestamp"] = pd.to_numeric(df_combined["timestamp"], errors="coerce")
            # Detectar si el timestamp está en ms o s
            ts_sample = df_combined["timestamp"].dropna().iloc[0] if not df_combined["timestamp"].dropna().empty else None
            if ts_sample is not None:
                if ts_sample > 1e12:
                    # Milisegundos
                    logger.info("⏱️ Timestamp detectado en milisegundos.")
                    factor = 1
                elif ts_sample > 1e9:
                    # Segundos
                    logger.info("⏱️ Timestamp detectado en segundos, convirtiendo a milisegundos.")
                    factor = 1000
                    df_combined["timestamp"] *= factor
                else:
                    logger.warning("⏱️ Timestamp fuera de rango esperado, revisa tus datos.")
                    factor = 1
                now = pd.Timestamp.now()
                rango = now - pd.DateOffset(months=meses)
                rango_ts = int(rango.timestamp() * 1000)
                df_combined = df_combined[df_combined["timestamp"] >= rango_ts].copy()
                logger.info(f"✅ Filtrado a los últimos {meses} meses: {len(df_combined)} registros.")
            else:
                logger.warning("No se pudo detectar un timestamp válido para filtrar por fecha.")

        # Limpiar filas con NaN en columnas clave
        columnas_clave = ["timestamp", "close", "open", "high", "low"]
        columnas_presentes = [col for col in columnas_clave if col in df_combined.columns]
        df_combined = df_combined.dropna(subset=columnas_presentes)
        logger.info(f"✅ Después de limpiar NaN: {len(df_combined)} registros.")

        return df_combined
    except Exception as e:
        logger.error(f"❌ Error al cargar y combinar datos: {e}")
        return None

def mostrar_rango_temporal(df):
    import pandas as pd
    time_col = None
    for col in ["timestamp", "open_time", "date", "time"]:
        if col in df.columns:
            time_col = col
            break
    if time_col is not None:
        try:
            ts_sample = df[time_col].dropna().iloc[0]
            # Si es string pero parece número, intenta convertir
            if isinstance(ts_sample, str) and ts_sample.isdigit():
                df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
                ts_sample = df[time_col].dropna().iloc[0]
            # Ahora decide si es ms o s
            if pd.api.types.is_numeric_dtype(df[time_col]):
                unit = 'ms' if int(ts_sample) > 1e12 else 's'
                df[time_col] = pd.to_datetime(df[time_col], unit=unit, errors='coerce')
                print(f"Columna {time_col} detectada como numérica, usando unit='{unit}' para conversión.")
            else:
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

def backtesting(
    df,
    rsi_limit_compra=None,
    rsi_limit_venta=None,
    adx_limit=None,
    min_votes_compra=None,
    min_votes_venta=None,
    sl_mult=None,
    tp_mult=None,
    atr_min=None   # <-- AGREGA ESTA LÍNEA
):
    # Usa los valores pasados o los de config_estrategias por defecto
    rsi_limit_compra = rsi_limit_compra if rsi_limit_compra is not None else RSI_LIMIT_COMPRA
    rsi_limit_venta = rsi_limit_venta if rsi_limit_venta is not None else RSI_LIMIT_VENTA
    adx_limit = adx_limit if adx_limit is not None else ADX_LIMIT
    min_votes_compra = min_votes_compra if min_votes_compra is not None else MIN_VOTES_COMPRA
    min_votes_venta = min_votes_venta if min_votes_venta is not None else MIN_VOTES_VENTA
    sl_mult = sl_mult if sl_mult is not None else SL_MULT
    tp_mult = tp_mult if tp_mult is not None else TP_MULT

    indicadores_lista = calcular_todos_los_indicadores(df)
    rsi_vals = [x.get("RSI") for x in indicadores_lista if x.get("RSI") is not None and not pd.isna(x.get("RSI"))]
    print(f"Valores válidos de RSI: {len(rsi_vals)}")
    if not isinstance(indicadores_lista, list):
        logger.error("❌ calcular_todos_los_indicadores no retornó una lista.")
        return []
    resultados = []
    posicion_abierta = False
    precio_compra = None
    compra_indice = None
    duraciones = []

    for i, indicadores in zip(df.index, indicadores_lista):
        if not isinstance(indicadores, dict):
            logger.error(f"❌ Indicadores inválidos en fila {i}: {indicadores}")
            continue
        precio_actual = df.loc[i, "close"]
        timestamp = df.loc[i, "timestamp"] if "timestamp" in df.columns else i
        tipo_mercado = df.loc[i, "market_type"] if "market_type" in df.columns else "desconocido"
        atr = indicadores.get("ATR")

        if not posicion_abierta:
            resultado_compra, usados_compra = estrategia_compra(
                indicadores,
                rsi_limit=rsi_limit_compra,
                adx_limit=adx_limit,
                min_votes=min_votes_compra,
                atr_min=atr_min
            )
            if resultado_compra:
                registrar_decisiones("compra", precio_actual, indicadores, "simulada")
                resultados.append({
                    "tipo": "compra",
                    "precio": precio_actual,
                    "indice": i,
                    "timestamp": timestamp,
                    "tipo_mercado": tipo_mercado,
                    "indicadores_usados": usados_compra,
                    "rsi": rsi_limit_compra,
                    "adx": adx_limit,
                    "votes": min_votes_compra,
                    "sl": sl_mult,
                    "tp": tp_mult
                })
                posicion_abierta = True
                precio_compra = precio_actual
                compra_indice = i
                if atr is not None and atr > 0:
                    stop_loss_val = precio_compra - sl_mult * atr
                    take_profit_val = precio_compra + tp_mult * atr
                else:
                    stop_loss_val = None
                    take_profit_val = None
        elif posicion_abierta:
            riesgo = gestion_riesgo(
                precio_compra,
                precio_actual,
                indicadores,
                mejor_precio=None,
                modo="compra",
                sl_mult=sl_mult,
                tp_mult=tp_mult,
                trailing_stop=True,
                atr_min=atr_min  # <-- agrega esto
            )
            if riesgo and riesgo.get("accion") == "vender":
                # Ejecutar venta por SL/TP
                resultado_venta, usados_venta = estrategia_venta(
                    indicadores,
                    rsi_limit=rsi_limit_venta,
                    adx_limit=adx_limit,
                    min_votes=min_votes_venta
                )
                registrar_decisiones("venta", precio_actual, indicadores, "simulada")
                duracion = i - compra_indice if compra_indice is not None else None
                usados_final = usados_venta.copy()
                if riesgo:
                    usados_final.append(riesgo)
                resultados.append({
                    "tipo": "venta",
                    "precio": precio_actual,
                    "indice": i,
                    "ganancia": precio_actual - precio_compra if precio_compra is not None else None,
                    "timestamp": timestamp,
                    "duracion": duracion,
                    "tipo_mercado": tipo_mercado,
                    "indicadores_usados": usados_final,
                    "rsi": rsi_limit_venta,
                    "adx": adx_limit,
                    "votes": min_votes_venta,
                    "sl": sl_mult,
                    "tp": tp_mult
                })
                if duracion is not None:
                    duraciones.append(duracion)
                posicion_abierta = False
                precio_compra = None
                compra_indice = None

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

    # Exportar resultados a CSV solo si hay resultados
    if resultados:
        pd.DataFrame(resultados).to_csv("resultados_backtesting.csv", index=False)
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
    else:
        logger.warning("⚠️ No hay resultados para exportar.")
        resumen = {
            "total_compras": 0,
            "total_ventas": 0,
            "ganancia_total": 0.0,
            "winrate": 0.0,
            "profit_factor": float('inf'),
            "max_drawdown": 0.0,
            "expectancy": 0.0,
            "avg_duration": 0.0
        }

    indicadores_ganadores = []
    indicadores_perdedores = []

    for r in resultados:
        if r["tipo"] == "venta" and r.get("ganancia") is not None:
            usados = r.get("indicadores_usados", [])
            if r["ganancia"] > 0:
                indicadores_ganadores.extend([u for u in usados if isinstance(u, str)])
            else:
                indicadores_perdedores.extend([u for u in usados if isinstance(u, str)])

    # NUEVO: Análisis de indicadores usados en compras
    indicadores_compras = []
    for r in resultados:
        if r["tipo"] == "compra":
            usados = r.get("indicadores_usados", [])
            indicadores_compras.extend(usados)

    print("Indicadores más frecuentes en operaciones GANADORAS:", Counter(indicadores_ganadores).most_common())
    print("Indicadores más frecuentes en operaciones PERDEDORAS:", Counter(indicadores_perdedores).most_common())
    print("Indicadores más frecuentes en operaciones de COMPRA:", Counter(indicadores_compras).most_common())

    return resultados, resumen

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

def ejecutar_backtesting(csv_file):
    """
    Ejecuta el backtesting sobre el archivo CSV y retorna resultados y resumen.
    """
    df = pd.read_csv(csv_file)
    resultados = backtesting(df)
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

    resumen = {
        "ganancia_total": total_ganancia,
        "winrate": winrate,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "expectancy": expectancy,
        "avg_gain": avg_gain,
        "avg_loss": avg_loss
    }
    return resultados, resumen

if __name__ == "__main__":
    import logging
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)  # Solo warnings y errores en consola
    file_handler = logging.FileHandler("backtesting.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.handlers = []
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("🚀 Iniciando backtesting...")
    client = connect_to_binance()
    df = cargar_y_combinar_datos("historial_trading.csv", client, meses=12)
    if df is not None:
        mostrar_rango_temporal(df)
        # Cargar parámetros óptimos
        with open("parametros_seleccionados.json") as f:
            params = json.load(f)
        rsi = params.get("RSI_LIMIT_COMPRA", 14)
        adx = params.get("ADX_LIMIT", 25)
        sl = params.get("SL_MULT", 1.5)
        tp = params.get("TP_MULT", 3)
        votes = params.get("MIN_VOTES", 2)
        atr_min = params.get("ATR_MIN", None)
        rsi_venta = params.get("RSI_LIMIT_VENTA", 86)

        resultados, resumen = backtesting(
            df,
            rsi_limit_compra=rsi,
            rsi_limit_venta=rsi_venta,
            adx_limit=adx,
            min_votes_compra=votes,
            min_votes_venta=votes,
            sl_mult=sl,
            tp_mult=tp,
            atr_min=atr_min
        )
        # Solo imprime el resumen y los indicadores más frecuentes
        print(f"Filas después del filtro de meses: {len(df)}")
        mostrar_rango_temporal(df)
        # --- Elimina o comenta los prints detallados de timestamp, precios, tipos de datos, NaN, etc. ---
        # print(df["timestamp"].head(10))
        # print(df["timestamp"].dtype)
        # print("Primeras filas de precios:")
        # print(df[["close", "high", "low", "open"]].head(10))
        # print("Tipos de datos:")
        # print(df[["close", "high", "low", "open"]].dtypes)
        # print("Valores NaN por columna:")
        # print(df.isna().sum())

        # --- Si quieres, puedes dejar solo este resumen de indicadores ---
        indicadores_lista = calcular_todos_los_indicadores(df)
        for ind in ["RSI", "ATR", "ADX"]:
            vals = [x.get(ind) for x in indicadores_lista if x.get(ind) is not None and not pd.isna(x.get(ind))]
            print(f"Valores válidos de {ind}: {len(vals)}")
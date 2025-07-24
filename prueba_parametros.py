import itertools
import importlib
import config_estrategias
import backtesting
import estrategias_bot1
import json
import os
import pandas as pd
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

# Define los rangos de parámetros a probar
rsi_limits = [30, 40, 45]
adx_limits = [20, 23, 25]
min_votes = [3, 4, 5]
sl_mults = [1.0, 1.5, 2.0]
tp_mults = [2.0, 3.0, 3.5]
ATR_MIN_range = [0.5, 1, 2, 3, 5]

# Verifica si el archivo de datos existe y es válido
if not os.path.exists("historial_trading_acum.csv"):
    print("❌ El archivo 'historial_trading_acum.csv' no existe. Por favor, verifica la ruta.")
    exit()

df = pd.read_csv("historial_trading_acum.csv")
if df.empty:
    print("⚠️ El archivo 'historial_trading_acum.csv' está vacío. Por favor, verifica los datos.")
    exit()

# Verifica si las columnas necesarias están presentes
required_columns = ["timestamp", "close"]
missing_columns = [col for col in required_columns if col not in df.columns]
if missing_columns:
    print(f"❌ Faltan las siguientes columnas en 'historial_trading_acum.csv': {missing_columns}")
    exit()

print(f"✅ Archivo 'historial_trading_acum.csv' cargado correctamente con {len(df)} filas.")

# Audita el rango temporal de los datos
client = backtesting.connect_to_binance()
df = backtesting.cargar_y_combinar_datos("historial_trading_acum.csv", client)
if df is not None and "timestamp" in df.columns:
    df["timestamp_numeric"] = pd.to_numeric(df["timestamp"], errors="coerce")
    start = df["timestamp_numeric"].min()
    end = df["timestamp_numeric"].max()
    import datetime
    if pd.notnull(start) and pd.notnull(end):
        start_dt = datetime.datetime.fromtimestamp(start / 1000)
        end_dt = datetime.datetime.fromtimestamp(end / 1000)
        print(f"Rango temporal de datos base: {start_dt} --> {end_dt} | Filas: {len(df)}")
    else:
        print(f"Rango temporal de datos base: {start} --> {end} | Filas: {len(df)}")

# Crea todas las combinaciones posibles
combinaciones = list(itertools.product(rsi_limits, adx_limits, min_votes, sl_mults, tp_mults, ATR_MIN_range))
comb_total = len(combinaciones)
print(f"Total de combinaciones a probar: {comb_total}")

# Guarda los resultados y fallos
resultados = []
fallos = []

def probar_combinacion(params):
    rsi, adx, votes, sl, tp, atr_min = params
    try:
        # Importa y recarga módulos dentro del proceso hijo
        import importlib
        import config_estrategias
        import backtesting
        import estrategias_bot1
        import pandas as pd

        # Carga el DataFrame dentro del proceso hijo
        df = pd.read_csv("historial_trading_acum.csv")
        client = backtesting.connect_to_binance()
        df = backtesting.cargar_y_combinar_datos("historial_trading_acum.csv", client)

        config_estrategias.RSI_LIMIT_COMPRA = rsi
        config_estrategias.RSI_LIMIT_VENTA = 100 - rsi
        config_estrategias.ADX_LIMIT = adx
        config_estrategias.MIN_VOTES_COMPRA = votes
        config_estrategias.MIN_VOTES_VENTA = votes
        config_estrategias.SL_MULT = sl
        config_estrategias.TP_MULT = tp

        importlib.reload(config_estrategias)
        importlib.reload(estrategias_bot1)
        importlib.reload(backtesting)

        resultados_trades, resumen = backtesting.backtesting(
            df,
            rsi_limit_compra=rsi,
            rsi_limit_venta=100 - rsi,
            adx_limit=adx,
            min_votes_compra=votes,
            min_votes_venta=votes,
            sl_mult=sl,
            tp_mult=tp,
            atr_min=atr_min
        )
        return {
            "params": {
                "RSI_LIMIT_COMPRA": rsi,
                "RSI_LIMIT_VENTA": 100 - rsi,
                "ADX_LIMIT": adx,
                "MIN_VOTES": votes,
                "SL_MULT": sl,
                "TP_MULT": tp,
                "ATR_MIN": atr_min
            },
            "resumen": resumen,
            "error": None
        }
    except Exception as e:
        return {
            "params": {
                "RSI_LIMIT_COMPRA": rsi,
                "RSI_LIMIT_VENTA": 100 - rsi,
                "ADX_LIMIT": adx,
                "MIN_VOTES": votes,
                "SL_MULT": sl,
                "TP_MULT": tp,
                "ATR_MIN": atr_min
            },
            "resumen": None,
            "error": str(e) + "\n" + traceback.format_exc()
        }

# Paraleliza las pruebas
with ProcessPoolExecutor() as executor:
    futures = [executor.submit(probar_combinacion, params) for params in combinaciones]
    for i, future in enumerate(as_completed(futures), 1):
        res = future.result()
        if res["error"]:
            fallos.append({**res["params"], "error": res["error"]})
            print(f"❌ Error en combinación {i}: {res['params']} -> {res['error']}")
        else:
            resultados.append({**res["params"], **res["resumen"]})
            print(f"✅ Combinación {i} completada: {res['params']}")

# Guarda los resultados para análisis posterior
with open("resultados_parametros.json", "w", encoding="utf-8") as f:
    json.dump(resultados, f, indent=4, ensure_ascii=False)
if fallos:
    with open("fallos_parametros.json", "w", encoding="utf-8") as f:
        json.dump(fallos, f, indent=4, ensure_ascii=False)

# Buscar la mejor combinación según la métrica elegida (ejemplo: ganancia_total)
def mejor_combinacion(resultados, metrica="ganancia_total"):
    mejores = [r for r in resultados if metrica in r and isinstance(r[metrica], (int, float))]
    if not mejores:
        return None
    mejor = max(mejores, key=lambda x: x[metrica])
    return mejor

print("\n=== Grid search completado ===")
print(f"Total combinaciones exitosas: {len(resultados)}")
print(f"Total combinaciones con error: {len(fallos)}")
mejor = mejor_combinacion(resultados, metrica="ganancia_total")
if mejor:
    print("\nMejor combinación según ganancia_total:")
    print(json.dumps(mejor, indent=4, ensure_ascii=False))
    parametros_finales = {k: mejor[k] for k in [
        "RSI_LIMIT_COMPRA", "RSI_LIMIT_VENTA", "ADX_LIMIT", "MIN_VOTES", "SL_MULT", "TP_MULT"
    ] if k in mejor}
    if os.path.exists("parametros_seleccionados.json"):
        import shutil
        shutil.copy("parametros_seleccionados.json", "parametros_seleccionados_backup.json")
    with open('parametros_seleccionados.json', 'w', encoding='utf-8') as f:
        json.dump(parametros_finales, f, indent=4, ensure_ascii=False)
    print("✅ Parámetros óptimos actualizados en parametros_seleccionados.json (respaldo en parametros_seleccionados_backup.json)")
else:
    print("No se pudo determinar la mejor combinación (¿quizás no hay resultados exitosos?).")
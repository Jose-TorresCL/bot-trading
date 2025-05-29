import itertools
import importlib
import config_estrategias
import backtesting
import estrategias_bot1
import json
import os
import pandas as pd
import traceback

# Define los rangos de parámetros a probar
rsi_limits = [30, 40, 45]
adx_limits = [20, 23, 25]
min_votes = [3, 4, 5]
sl_mults = [1.0, 1.5, 2.0]
tp_mults = [2.0, 3.0, 3.5]

resultados = []
fallos = []
comb_total = len(rsi_limits) * len(adx_limits) * len(min_votes) * len(sl_mults) * len(tp_mults)
comb_num = 1

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

# Carga el DataFrame SOLO una vez para auditar el rango temporal y filas
client = backtesting.connect_to_binance()
df = backtesting.cargar_y_combinar_datos("historial_trading_acum.csv", client)
if df is not None and "timestamp" in df.columns:
    # Intenta convertir a numérico, ignora errores
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

# Recarga los módulos una vez antes del bucle
importlib.reload(config_estrategias)
importlib.reload(estrategias_bot1)
importlib.reload(backtesting)

for rsi in rsi_limits:
    for adx in adx_limits:
        for votes in min_votes:
            for sl in sl_mults:
                for tp in tp_mults:
                    print(f"\n=== Probando combinación {comb_num}/{comb_total} ===")
                    
                    # Modifica los parámetros en config_estrategias
                    config_estrategias.RSI_LIMIT_COMPRA = rsi
                    config_estrategias.RSI_LIMIT_VENTA = 100 - rsi
                    config_estrategias.ADX_LIMIT = adx
                    config_estrategias.MIN_VOTES_COMPRA = votes
                    config_estrategias.MIN_VOTES_VENTA = votes
                    config_estrategias.SL_MULT = sl
                    config_estrategias.TP_MULT = tp

                    # Recarga los módulos para asegurar que los cambios se apliquen
                    importlib.reload(config_estrategias)
                    importlib.reload(estrategias_bot1)
                    importlib.reload(backtesting)

                    # Imprime los parámetros actuales para verificar
                    print(f"Parámetros actuales: RSI={rsi}, ADX={adx}, VOTES={votes}, SL={sl}, TP={tp}")

                    try:
                        # Ejecuta el backtesting con el archivo acumulado
                        resultados_trades, resumen = backtesting.backtesting(
    df,
    rsi_limit_compra=rsi,
    rsi_limit_venta=100 - rsi,
    adx_limit=adx,
    min_votes_compra=votes,
    min_votes_venta=votes,
    sl_mult=sl,
    tp_mult=tp
)
                        # Verifica si el resumen cambia entre iteraciones
                        print(f"Resumen obtenido: {resumen}")
                        # Asegura que los resultados sean únicos
                        resultados.append({
                            "RSI_LIMIT_COMPRA": rsi,
                            "RSI_LIMIT_VENTA": 100 - rsi,
                            "ADX_LIMIT": adx,
                            "MIN_VOTES": votes,
                            "SL_MULT": sl,
                            "TP_MULT": tp,
                            **resumen
                        })
                        print(f"Probado: RSI={rsi}, ADX={adx}, VOTES={votes}, SL={sl}, TP={tp} -> {resumen}")
                    except Exception as e:
                        fallo = {
                            "RSI_LIMIT_COMPRA": rsi,
                            "RSI_LIMIT_VENTA": 100 - rsi,
                            "ADX_LIMIT": adx,
                            "MIN_VOTES": votes,
                            "SL_MULT": sl,
                            "TP_MULT": tp,
                            "error": str(e),
                            "traceback": traceback.format_exc()
                        }
                        fallos.append(fallo)
                        print(f"❌ Error en combinación {comb_num}: {fallo}")
                    finally:
                        # Incrementar el contador incluso si ocurre un error
                        comb_num += 1

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
else:
    print("No se pudo determinar la mejor combinación (¿quizás no hay resultados exitosos?).")
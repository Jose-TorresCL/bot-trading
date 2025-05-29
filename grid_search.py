import importlib
import pandas as pd
import itertools
import json

# Parámetros a probar
RSI_LIMIT_COMPRA_values = [30, 35, 40, 45, 50]
MIN_VOTES_COMPRA_values = [1, 2, 3, 4]

# Carga el DataFrame una sola vez
from conexion_api import connect_to_binance
from backtesting import cargar_y_combinar_datos, backtesting

client = connect_to_binance()
df = cargar_y_combinar_datos("historial_trading.csv", client)

resultados_grid = []

for rsi_limit, min_votes in itertools.product(RSI_LIMIT_COMPRA_values, MIN_VOTES_COMPRA_values):
    # Modifica los parámetros en config_estrategias.py
    with open("config_estrategias.py", "r") as f:
        lines = f.readlines()
    with open("config_estrategias.py", "w") as f:
        for line in lines:
            if line.strip().startswith("RSI_LIMIT_COMPRA"):
                f.write(f"RSI_LIMIT_COMPRA = {rsi_limit}\n")
            elif line.strip().startswith("MIN_VOTES_COMPRA"):
                f.write(f"MIN_VOTES_COMPRA = {min_votes}\n")
            else:
                f.write(line)
    # Recarga el módulo de configuración
    import config_estrategias
    importlib.reload(config_estrategias)
    # Recarga el módulo de backtesting para que tome los nuevos parámetros
    importlib.reload(__import__('backtesting'))
    from backtesting import backtesting

    print(f"Probando RSI_LIMIT_COMPRA={rsi_limit}, MIN_VOTES_COMPRA={min_votes}")
    resultados = backtesting(df)
    # Extrae el resumen de resultados
    ganancias = [r["ganancia"] for r in resultados if r["tipo"] == "venta" and r.get("ganancia") is not None]
    operaciones_ganadoras = [g for g in ganancias if g > 0]
    operaciones_perdedoras = [g for g in ganancias if g <= 0]
    winrate = (len(operaciones_ganadoras) / len(ganancias) * 100) if ganancias else 0
    profit_factor = (sum(operaciones_ganadoras) / abs(sum(operaciones_perdedoras))) if operaciones_perdedoras else float('inf')
    total_ganancia = sum(ganancias)
    resultados_grid.append({
        "RSI_LIMIT_COMPRA": rsi_limit,
        "MIN_VOTES_COMPRA": min_votes,
        "ganancia_total": total_ganancia,
        "winrate": winrate,
        "profit_factor": profit_factor
    })

# Guarda los resultados en un CSV
pd.DataFrame(resultados_grid).to_csv("resultados_grid_search.csv", index=False)
print("Grid search completado. Resultados guardados en resultados_grid_search.csv")

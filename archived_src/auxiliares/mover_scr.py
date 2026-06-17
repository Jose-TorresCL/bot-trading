import os
import shutil

# Crea la carpeta 'data' si no existe
os.makedirs("data", exist_ok=True)

# Crea las subcarpetas dentro de 'data'
for subcarpeta in ["papertrading", "backtesting", "historiales"]:
    os.makedirs(os.path.join("data", subcarpeta), exist_ok=True)

# Define las carpetas destino
carpetas = {
    "papertrading": [
        "papertrading_BTCUSDT.csv",
        "estado_papertrading.json",
        "registro_decisiones.json",
        "registro_operaciones.json"
    ],
    "backtesting": [
        "resultados_parametros.json",
        "operaciones_robustas_por_simbolo_periodo.csv",
        "mejores_operaciones_por_simbolo_periodo.json",
        "parametros_seleccionados.json",
        "parametros_seleccionados_backup.json",
        "decision.json"
    ],
    "historiales": [
        "historial_trading_maestro.csv",
        "historial_trading_maestro_limpio.csv",
        "historial_trading_limpio.csv",
        "historial_BNBUSDT.csv",
        "historial_BTCUSDT.csv",
        "historial_ETHUSDT.csv",
        "historial_WLDUSDT.csv"
    ]
}

# Mueve los archivos desde la raíz de 'data' a su carpeta correspondiente
for carpeta, archivos in carpetas.items():
    for archivo in archivos:
        origen = os.path.join("data", archivo)
        destino = os.path.join("data", carpeta, archivo)
        # Solo mueve si el archivo está en la raíz de 'data' y no ya en la subcarpeta
        if os.path.exists(origen) and not os.path.exists(destino):
            shutil.move(origen, destino)
            print(f"Movido: {origen} -> {destino}")
        else:
            print(f"No encontrado en raíz de data o ya movido: {archivo}")

print("✅ Archivos en la raíz de 'data' movidos y organizados por función.")
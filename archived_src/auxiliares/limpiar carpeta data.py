import os
import shutil
from datetime import datetime
import re

data_dir = "data"
backup_dir = os.path.join(data_dir, "backup")
os.makedirs(backup_dir, exist_ok=True)

# Mapeo de archivos clave a subcarpetas
mapeo_subcarpetas = {
    # Paper trading y registros principales
    "papertrading_BTCUSDT.csv": "papertrading",
    "estado_papertrading.json": "papertrading",
    "registro_decisiones.json": "papertrading",
    "registro_operaciones.json": "papertrading",

    # Historiales y datos limpios
    "historial_trading.csv": "historiales",
    "historial_trading_limpio.csv": "historiales",
    "historial_trading_maestro.csv": "historiales",
    "historial_trading_maestro_limpio.csv": "historiales",
    "acumulado_operaciones.csv": "historiales",

    # Resultados y resúmenes de backtesting multi-símbolo
    "resultados_backtesting.csv": "backtesting",
    "resumen_backtesting.csv": "backtesting",
    "resultados_BNBUSDT_12m.csv": "backtesting",
    "resultados_BNBUSDT_3m.csv": "backtesting",
    "resultados_BNBUSDT_6m.csv": "backtesting",
    "resultados_BTCUSDT_12m.csv": "backtesting",
    "resultados_BTCUSDT_3m.csv": "backtesting",
    "resultados_BTCUSDT_6m.csv": "backtesting",
    "resultados_ETHUSDT_12m.csv": "backtesting",
    "resultados_ETHUSDT_3m.csv": "backtesting",
    "resultados_ETHUSDT_6m.csv": "backtesting",
    "resultados_WLDUSDT_12m.csv": "backtesting",
    "resultados_WLDUSDT_3m.csv": "backtesting",
    "resultados_WLDUSDT_6m.csv": "backtesting",
    "resumen_BNBUSDT_12m.csv": "backtesting",
    "resumen_BNBUSDT_3m.csv": "backtesting",
    "resumen_BNBUSDT_6m.csv": "backtesting",
    "resumen_BTCUSDT_12m.csv": "backtesting",
    "resumen_BTCUSDT_3m.csv": "backtesting",
    "resumen_BTCUSDT_6m.csv": "backtesting",
    "resumen_ETHUSDT_12m.csv": "backtesting",
    "resumen_ETHUSDT_3m.csv": "backtesting",
    "resumen_ETHUSDT_6m.csv": "backtesting",
    "resumen_WLDUSDT_12m.csv": "backtesting",
    "resumen_WLDUSDT_3m.csv": "backtesting",
    "resumen_WLDUSDT_6m.csv": "backtesting",

    # Parámetros y configuraciones
    "parametros_seleccionados.json": "backtesting",
    "resultados_parametros.json": "backtesting",
    "mejores_operaciones_por_simbolo_periodo.json": "backtesting",
    "operaciones_robustas_por_simbolo_periodo.csv": "backtesting",
    "parametros_seleccionados_backup.json": "backup",
    "decision.json": "backup",

    # Históricos por símbolo
    "historial_BNBUSDT.csv": "historicos",
    "historial_BTCUSDT.csv": "historicos",
    "historial_ETHUSDT.csv": "historicos",
    "historial_WLDUSDT.csv": "historicos",
    "historial_trading_maestro_limpio.csv": "historicos",

    # Otros archivos generados por notebooks
    "mejor_operacion_papertrading.json": "papertrading",
    "operaciones_robustas_papertrading.csv": "papertrading",
}

# Detecta símbolos en el nombre del archivo
simbolos = ["BTCUSDT", "BNBUSDT", "WLDUSDT", "ETHUSDT", "SOLUSDT"]

print("Moviendo archivos clave a sus subcarpetas correspondientes...\n")
for archivo, subcarpeta in mapeo_subcarpetas.items():
    origen = os.path.join(data_dir, archivo)
    destino_dir = os.path.join(data_dir, subcarpeta)
    destino = os.path.join(destino_dir, archivo)
    os.makedirs(destino_dir, exist_ok=True)
    if os.path.exists(origen):
        shutil.move(origen, destino)
        print(f"✅ {archivo} movido a {subcarpeta}/")

# Procesa archivos no clave
for archivo in os.listdir(data_dir):
    ruta = os.path.join(data_dir, archivo)
    if os.path.isfile(ruta) and archivo not in mapeo_subcarpetas and archivo != "backup":
        info = os.stat(ruta)
        fecha_mod = datetime.fromtimestamp(info.st_mtime)
        tamano = info.st_size

        # Detecta el símbolo en el nombre del archivo
        simbolo_encontrado = None
        for s in simbolos:
            if re.search(s, archivo):
                simbolo_encontrado = s
                break

        print(f"\nArchivo: {archivo}")
        print(f"  Fecha modificación: {fecha_mod.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Tamaño: {tamano/1024:.2f} KB")
        if simbolo_encontrado:
            print(f"  Símbolo detectado: {simbolo_encontrado}")
        else:
            print("  Símbolo detectado: (no encontrado en nombre)")

        accion = input("¿Qué deseas hacer con este archivo? (m = mover a backup, e = eliminar, n = no hacer nada): ").strip().lower()
        if accion == "m":
            shutil.move(ruta, os.path.join(backup_dir, archivo))
            print(f"Movido {archivo} a backup/")
        elif accion == "e":
            os.remove(ruta)
            print(f"Eliminado {archivo}")
        else:
            print(f"{archivo} se mantiene en data/")

print("\n✅ Organización y limpieza terminada. Revisa las subcarpetas y backup para tus archivos movidos.")
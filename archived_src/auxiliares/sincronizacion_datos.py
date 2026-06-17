# filepath: c:\Users\lenovo\bot_trading\semana_5\src\scripts_auxiliares\limpiar_y_unir_historicos.py
import os, glob, pandas as pd
from src.validar_y_limpiar_datos import verificar_y_limpiar_datos  # usar import absoluto del paquete

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "data", "historicos")
CLEAN_DIR = os.path.join(SRC, "cleaned")
os.makedirs(CLEAN_DIR, exist_ok=True)

files = glob.glob(os.path.join(SRC, "historial_*.csv"))
cleaned = []
for f in files:
    try:
        out = os.path.join(CLEAN_DIR, os.path.basename(f).replace(".csv","_clean.csv"))
        # usar la función de limpieza para cada archivo y guardar en out
        ok = verificar_y_limpiar_datos(csv_file=f, csv_salida=out)
        if ok and os.path.exists(out):
            df = pd.read_csv(out, parse_dates=["timestamp"], low_memory=False)
            cleaned.append(df)
    except Exception as e:
        print("Error limpiando", f, e)

if cleaned:
    master = pd.concat(cleaned, ignore_index=True)
    master = master.drop_duplicates(subset=["timestamp","symbol"] if "symbol" in master.columns else ["timestamp"])
    master = master.sort_values(["symbol","timestamp"]) if "symbol" in master.columns else master.sort_values("timestamp")
    out_master = os.path.join(ROOT, "data", "historiales", "historial_trading_limpio.csv")
    os.makedirs(os.path.dirname(out_master), exist_ok=True)
    master.to_csv(out_master, index=False)
    print("✅ Master guardado en", out_master, "filas:", len(master))
else:
    print("⚠️ No se generaron archivos limpios.")
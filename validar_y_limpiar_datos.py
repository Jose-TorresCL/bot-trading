import json
import pandas as pd
import os

def verificar_parametros(param_file="parametros_seleccionados.json", grid_file="resultados_parametros.json"):
    print("🔎 Verificando parámetros óptimos...")
    if not os.path.exists(param_file):
        print(f"❌ No se encontró {param_file}")
        return False
    with open(param_file, encoding="utf-8") as f:
        params = json.load(f)
    print("Parámetros cargados:")
    print(json.dumps(params, indent=2, ensure_ascii=False))

    if os.path.exists(grid_file):
        with open(grid_file, encoding="utf-8") as f:
            grid = json.load(f)
        if isinstance(grid, list) and grid:
            mejores = sorted(grid, key=lambda x: x.get("ganancia_total", -float("inf")), reverse=True)
            mejor_grid = mejores[0]
            print("\nMejor combinación del grid search:")
            print(json.dumps(mejor_grid, indent=2, ensure_ascii=False))
            claves = ["RSI_LIMIT_COMPRA", "RSI_LIMIT_VENTA", "ADX_LIMIT", "MIN_VOTES", "SL_MULT", "TP_MULT", "ATR_MIN"]
            for k in claves:
                v1 = params.get(k)
                v2 = mejor_grid.get(k)
                if v1 != v2:
                    print(f"⚠️ Diferencia en {k}: param_file={v1} | grid_file={v2}")
        else:
            print("⚠️ El archivo de grid search está vacío o malformado.")
    else:
        print(f"⚠️ No se encontró {grid_file}")

def verificar_y_limpiar_datos(csv_file="historial_trading.csv", csv_salida="historial_trading_limpio.csv"):
    print("\n🔎 Verificando y limpiando datos históricos...")
    if not os.path.exists(csv_file):
        print(f"❌ No se encontró {csv_file}")
        return False
    df = pd.read_csv(csv_file)
    print(f"Registros cargados: {len(df)}")
    print("Columnas:", list(df.columns))
    nan_cols = df.isna().sum()
    nan_cols = nan_cols[nan_cols > 0]
    if not nan_cols.empty:
        print("⚠️ Columnas con valores NaN:")
        print(nan_cols)
        print("🧹 Limpiando filas con NaN en columnas clave...")
        columnas_clave = ["close", "price", "volume", "timestamp"]
        df = df.dropna(subset=columnas_clave)
    else:
        print("✅ No hay valores NaN en las columnas principales.")

    # Filtra timestamps claramente inválidos (ejemplo: menores a 1e9)
    if "timestamp" in df.columns:
        try:
            ts = pd.to_numeric(df["timestamp"], errors="coerce")
            rango_min, rango_max = ts.min(), ts.max()
            print(f"Rango de timestamp antes de limpiar: {rango_min} - {rango_max}")
            df = df[ts > 1e9]
            print(f"Rango de timestamp después de limpiar: {df['timestamp'].astype(float).min()} - {df['timestamp'].astype(float).max()}")
        except Exception as e:
            print(f"⚠️ Error al analizar timestamp: {e}")

    print(f"Filas después de limpiar: {len(df)}")
    df.to_csv(csv_salida, index=False)
    print(f"✅ Archivo limpio guardado como {csv_salida}")
    return True

if __name__ == "__main__":
    verificar_parametros()
    verificar_y_limpiar_datos()
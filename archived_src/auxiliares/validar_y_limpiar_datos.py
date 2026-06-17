"""
validar_y_limpiar_datos.py
--------------------------
Utilidades para verificar parámetros óptimos y limpiar archivos históricos de trading.
Incluye comparación de parámetros, chequeo de diferencias y limpieza de datos NaN o timestamps inválidos.
"""

import json
import pandas as pd
import os

from src.validacion_datos import validar_datos  # delegar en el validador central

def verificar_parametros(param_file="parametros_seleccionados.json", grid_file="resultados_parametros.json"):
    """
    Verifica que los parámetros óptimos actuales coincidan con los mejores del grid search.
    Muestra diferencias y advierte si hay desajustes.
    """
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

def verificar_y_limpiar_datos(csv_file="historial_trading.csv", csv_salida=None):
    """
    Wrapper I/O: lee csv_file, aplica validar_datos(df) y guarda resultado en csv_salida (si se indica).
    Mantiene compatibilidad con la versión previa (parsing de timestamp) pero delega la limpieza principal.
    """
    print("\n🔎 Verificando y limpiando datos históricos (delegando en validar_datos)...")
    if not os.path.exists(csv_file):
        print(f"❌ No se encontró {csv_file}")
        return False

    # Leer con pandas (acepta timestamp en distintos formatos)
    df = pd.read_csv(csv_file, low_memory=False)

    # Normalizar nombre timestamp si hace falta (mantener compatibilidad)
    if "timestamp" not in df.columns:
        for cand in ("time","date","datetime","open_time"):
            if cand in df.columns:
                df = df.rename(columns={cand: "timestamp"})
                break

    # Delegar validación/transformación principal
    try:
        df_clean = validar_datos(df)
    except Exception as e:
        print("❌ Error en validar_datos:", e)
        return False

    # Determinar ruta de salida si no se pasó
    if csv_salida is None:
        base = os.path.splitext(os.path.basename(csv_file))[0]
        csv_salida = os.path.join(os.path.dirname(csv_file), f"{base}_clean.csv")

    df_clean.to_csv(csv_salida, index=False)
    print(f"✅ Archivo limpio guardado como {csv_salida} (filas: {len(df_clean)})")
    return True

if __name__ == "__main__":
    # CLI mínimo usable
    import argparse
    parser = argparse.ArgumentParser(description="Validar y limpiar CSV histórico (delegando en validar_datos)")
    parser.add_argument("-f", "--csv_file", default="historial_trading.csv")
    parser.add_argument("-o", "--csv_salida", default=None)
    args = parser.parse_args()
    verificar_y_limpiar_datos(csv_file=args.csv_file, csv_salida=args.csv_salida)
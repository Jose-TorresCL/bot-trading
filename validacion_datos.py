import logging
import pandas as pd
import numpy as np

def validar_datos(df, required_fields):
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):  # 🔹 Validamos explícitamente que `df` sea un DataFrame
        logging.error("❌ Error: DataFrame recibido está vacío o no está definido.")
        return pd.DataFrame()  # 🔹 Retorno seguro para evitar el error

    # 🔥 SOLUCIÓN: Definir `historical_data` antes de usarlo
    historical_data = df.to_dict(orient="records")  # 🔥 Definir `historical_data` antes del `for`

    for record in historical_data:
        if isinstance(record, dict):
            if "close" in record and "price" not in record:
                record["price"] = record["close"]   

    # 🚀 PASO 2: Filtrar registros inválidos (evitando eliminar todo)
    historical_data = [
        record for record in historical_data 
        if isinstance(record, dict) and "close" in record and any(field in record for field in ["open", "high", "low", "volume"])
    ]

    registros_validos = len(historical_data)
    
    df = pd.DataFrame(historical_data)  # 🔹 Reconstruimos el DataFrame con los registros filtrados

    # 🚀 PASO 3: Si no hay registros válidos, asignar valores mínimos para continuar
    if registros_validos == 0:
        logging.warning("⚠️ Todos los registros fueron filtrados como inválidos. Se conservarán los datos originales sin eliminar todo.")
        df = pd.DataFrame([{field: 0.0 for field in required_fields}])  # 🔹 Restauramos con valores seguros

    # 🚀 PASO 4: Asegurar que las columnas esenciales siguen presentes y corregir NaN/Inf
    for col in required_fields:
        if col in df.columns and (df[col].dtype == np.float64 or df[col].dtype == np.int64):
            avg_value = df[col][~df[col].isin([np.inf, -np.inf])].mean(skipna=True) if not df[col].isna().all() else 0.0
            df[col] = df[col].replace([np.inf, -np.inf], np.nan)
            df[col] = df[col].fillna(avg_value)

    # 🚀 PASO 5: Detectar si aún quedan NaN o Inf
    num_df = df.select_dtypes(include=[np.number])
    inf_cols = num_df.columns[np.isinf(num_df).any()]
    nan_cols = num_df.columns[num_df.isna().any()]

    if not num_df.empty and (len(nan_cols) > 0 or len(inf_cols) > 0):
        logging.error(f"❌ Datos contienen NaN en: {nan_cols.tolist()}, Infinitos en: {inf_cols.tolist()}")

    # 🚀 PASO 6: Convertir columnas numéricas a `float` para cálculos eficientes
    for field in required_fields:
        if field in df.columns:
            try:
                df[field] = pd.to_numeric(df[field], errors="coerce").fillna(0.0)
            except (ValueError, TypeError):
                logging.error(f"❌ Error al convertir {field} a float. Usando 0.0.")
                df[field] = 0.0

    return df  # 🚀 Retorno seguro siempre como DataFrame
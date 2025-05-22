import pandas as pd
import logging

def obtener_datos_historicos(source="historial_trading_acum.csv"):
    try:
        df = pd.read_csv(source)
        logging.info(f"🔍 Columnas detectadas: {df.columns.tolist()}")
        logging.info(f"🔍 Primeras 5 filas:\n{df.head()}")
        historical_data = df.to_dict(orient="records")
        logging.info(f"✅ Datos históricos obtenidos: {len(historical_data)} registros.")
        for record in historical_data:
            if "price" not in record or record["price"] is None:
                record["price"] = record.get("close")
        return historical_data
    except FileNotFoundError:
        logging.warning("⚠️ No se encontró el archivo de datos históricos.")
        return []

def guardar_datos_csv(data, filename="datos_historicos.csv"):
    if not data:
        logging.warning("⚠️ No hay datos para guardar en CSV.")
        return
    pd.DataFrame(data).to_csv(filename, mode="a", header=False, index=False)
    logging.info(f"✅ Datos guardados en {filename}")

def cargar_datos_csv(filename="datos_historicos.csv"):
    try:
        df = pd.read_csv(filename)
        if df.empty:
            logging.warning("⚠️ Archivo CSV vacío.")
            return []
        return df.to_dict(orient="records")
    except (FileNotFoundError, pd.errors.ParserError) as e:
        logging.warning(f"⚠️ Error al cargar archivo CSV: {e}")
        return []

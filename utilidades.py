import os
import json
import logging
from datetime import datetime
import pandas as pd
import numpy as np

# Configuración de `logging`
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("registro_operaciones.txt", mode="a"),
        logging.StreamHandler()  # Mostrar logs en la consola
    ]
)

def log_operation(message, operation_type="INFO"):
    """
    Registra mensajes en un archivo de log (`registro_operaciones.txt`) con `logging`.
    """
    try:
        if operation_type == "ERROR":
            logging.error(message)
        elif operation_type == "WARNING":
            logging.warning(message)
        else:
            logging.info(message)
    except Exception as e:
        logging.error(f"❌ Error al registrar operación: {e}")

def log_operation_json(message, operation_type="INFO", additional_data=None):
    """
    Guarda registros en `registro_operaciones.json`, asegurando rotación automática si el archivo supera los 5 MB.
    También valida que los datos sean diccionarios antes de guardarlos.
    """
    log_file = "registro_operaciones.json"

    try:
        # 🔹 Validación de `additional_data`
        if additional_data and not isinstance(additional_data, dict):
            logging.warning("⚠️ `additional_data` no es un diccionario. Convirtiéndolo...")
            additional_data = {"data": str(additional_data)}

        log_entry = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "type": operation_type,
            "message": message,
            "additional_data": convertir_timestamps_a_str(additional_data)
        }

        # 🔹 Rotación del archivo JSON por tamaño
        if os.path.exists(log_file) and os.path.getsize(log_file) > 5 * 1024 * 1024:
            os.rename(log_file, f"registro_operaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            logging.info("📌 Archivo JSON de log rotado por tamaño.")

        # 🔹 Escritura segura en JSON con formato estructurado
        with open(log_file, "a", encoding="utf-8") as file:
            json.dump(log_entry, file, indent=4, ensure_ascii=False)
            file.write("\n")

        logging.info(f"📌 Operación registrada en JSON: {log_entry}")
    except Exception as e:
        logging.error(f"❌ Error al registrar operación en JSON: {e}")


def validar_estructura(datos, required_fields=None):
    """Verifica si los registros tienen los campos requeridos."""
    if not isinstance(datos, list):
        logging.error("❌ `datos` no es una lista válida.")
        return False

    if required_fields:
        for field in required_fields:
            if not all(field in record for record in datos):
                logging.error(f"❌ Falta el campo requerido: {field}")
                return False

    logging.info("✅ Estructura de datos verificada correctamente.")
    return True

def convertir_timestamps_a_str(obj):
    import datetime

    if isinstance(obj, dict):
        return {k: convertir_timestamps_a_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convertir_timestamps_a_str(i) for i in obj]
    elif isinstance(obj, (pd.Timestamp, datetime.datetime, datetime.date)):
        return str(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj
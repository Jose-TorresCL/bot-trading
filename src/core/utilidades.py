"""
utilidades.py
-------------
Funciones utilitarias para logging, validación y conversión de datos en el bot de trading.
Incluye registro estructurado en TXT y JSON, validación de estructura y conversión segura de timestamps.

Notas:
- Actualmente, **solo `log_operation_json` se usa activamente** en el flujo principal del bot.
- Las funciones `log_operation`, `validar_estructura` y `convertir_timestamps_a_str` NO se usan directamente,
  pero se mantienen por si se requieren en futuras extensiones, pruebas o scripts auxiliares.
- Si buscas máxima limpieza, puedes mover las funciones no usadas a un archivo de utilidades
"""

import os
import json
import logging
from datetime import datetime
import re
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, List

# Crear la carpeta de logs si no existe
os.makedirs("data/logs", exist_ok=True)

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("data/logs/registro_operaciones.txt", mode="a"),
        logging.StreamHandler()
    ]
)

def log_operation(message, operation_type="INFO"):
    """
    Registra mensajes en un archivo de log (registro_operaciones.txt) con logging.
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
    Guarda registros en registro_operaciones.json, asegurando rotación automática si el archivo supera los 5 MB.
    Valida que los datos adicionales sean diccionarios antes de guardarlos.
    """
    log_file = "data/logs/registro_operaciones.json"
    try:
        if additional_data and not isinstance(additional_data, dict):
            logging.warning("⚠️ `additional_data` no es un diccionario. Convirtiéndolo...")
            additional_data = {"data": str(additional_data)}

        log_entry = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "type": operation_type,
            "message": message,
            "additional_data": convertir_timestamps_a_str(additional_data)
        }

        # Rotación del archivo JSON por tamaño
        if os.path.exists(log_file) and os.path.getsize(log_file) > 5 * 1024 * 1024:
            os.rename(log_file, f"data/logs/registro_operaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            logging.info("📌 Archivo JSON de log rotado por tamaño.")

        with open(log_file, "a", encoding="utf-8") as file:
            json.dump(log_entry, file, indent=4, ensure_ascii=False)
            file.write("\n")

        logging.info(f"📌 Operación registrada en JSON: {log_entry}")
    except Exception as e:
        logging.error(f"❌ Error al registrar operación en JSON: {e}")

def validar_estructura(datos, required_fields=None):
    """
    Verifica si los registros tienen los campos requeridos.
    """
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
    """
    Convierte objetos datetime, numpy y pandas a string o tipo nativo para exportación.
    """
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

def cargar_parametros(path="data/backtesting/parametros_seleccionados.json"):
    """
    Carga los parámetros desde un archivo JSON y devuelve un diccionario.
    Si el archivo no existe o hay error, devuelve un diccionario vacío.
    """
    import os
    import json
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as e:
            logging.warning(f"No se pudo leer {path}: {e}")
    return {}

@dataclass
class ParamConfig:
    # Core estrategia
    RSI_LIMIT_COMPRA: float = 30.0
    RSI_LIMIT_VENTA: float = 70.0
    ADX_LIMIT: float = 25.0
    SL_MULT: float = 1.0
    TP_MULT: float = 2.0
    MIN_VOTES_COMPRA: int = 1
    MIN_VOTES_VENTA: int = 1
    # Dinámicos / filtros
    rsi_dynamic_buy: float = 30.0
    rsi_dynamic_sell: float = 70.0
    atr_min: float = 0.0
    bb_width_min: Optional[float] = None
    # Riesgo / trailing
    trailing_stop: bool = True
    adx_trailing_threshold: float = 25.0
    # Capital
    starting_capital: float = 100.0
    # Control operativo
    COOLDOWN_THRESHOLD: int = 3
    COOLDOWN_PERIOD_BARS: int = 50
    max_duracion: int = 50

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ParamConfig":
        # Acepta alias en mayúsculas o minúsculas
        norm = {k.lower(): v for k, v in d.items()}
        field_map = {f.name: f for f in cls.__dataclass_fields__.values()}  # type: ignore
        init_vals = {}
        for name in field_map:
            # buscar exacto / alias uppercase
            if name in d:
                init_vals[name] = d[name]
            elif name.upper() in d:
                init_vals[name] = d[name.upper()]
            elif name.lower() in norm:
                init_vals[name] = norm[name.lower()]
        return cls(**init_vals)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def cargar_parametros_config(path: str = "data/backtesting/parametros_seleccionados.json") -> ParamConfig:
    """
    Carga parámetros desde JSON, aplica tolerancia a alias y devuelve ParamConfig.
    Si falla, retorna defaults.
    """
    raw = cargar_parametros(path)  # reutiliza función existente
    try:
        return ParamConfig.from_dict(raw)
    except Exception as e:
        logging.warning(f"Fallo creando ParamConfig desde {path}: {e}. Usando defaults.")
        return ParamConfig()

REQUIRED_OHLCV = ["open", "high", "low", "close", "volume", "timestamp"]

def limpiar_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia columnas ruido:
    - Elimina columnas que empiezan con 'Unnamed'
    - Elimina columnas cuyo nombre es numérico / flotante
    - Elimina columnas totalmente vacías
    - Renombra variantes comunes (OpenTime/open_time -> timestamp)
    """
    if df is None or df.empty:
        return df

    # Drop columnas 'Unnamed'
    cols_drop = [c for c in df.columns if c.startswith("Unnamed")]
    # Nombres numéricos (pueden venir de filas mal enganchadas como header)
    for c in df.columns:
        try:
            float(c)
            cols_drop.append(c)
        except Exception:
            pass

    # Columnas vacías
    for c in df.columns:
        if df[c].isna().all():
            cols_drop.append(c)

    df = df.drop(columns=list(set(cols_drop)), errors="ignore")

    # Normaliza nombres básicos a minúsculas
    df.rename(columns={c: c.lower() for c in df.columns}, inplace=True)

    # Map timestamp
    for candidate in ["open_time", "opentime", "fecha", "date", "datetime", "time"]:
        if candidate in df.columns and "timestamp" not in df.columns:
            df.rename(columns={candidate: "timestamp"}, inplace=True)
            break

    # Asegura tipos numéricos básicos (si existen)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse timestamp si está con detección de unidad (s/ms) cuando es numérico
    if "timestamp" in df.columns:
        ts = df["timestamp"]
        try:
            # Si ya es datetime, solo forzar UTC
            if pd.api.types.is_datetime64_any_dtype(ts):
                df["timestamp"] = pd.to_datetime(ts, errors="coerce", utc=True)
            else:
                # Intentar detectar unidad si es numérico
                ts_num = pd.to_numeric(ts, errors="coerce")
                # Heurística: >1e12 => milisegundos, >1e9 => segundos, sino intentar parseo directo
                max_val = float(ts_num.dropna().max()) if not ts_num.dropna().empty else None
                if max_val is not None and np.isfinite(max_val):
                    if max_val > 1e12:
                        df["timestamp"] = pd.to_datetime(ts_num, unit="ms", errors="coerce", utc=True)
                    elif max_val > 1e9:
                        df["timestamp"] = pd.to_datetime(ts_num, unit="s", errors="coerce", utc=True)
                    else:
                        # Probablemente ya es fecha string o ns raros; intentar parseo genérico
                        df["timestamp"] = pd.to_datetime(ts, errors="coerce", utc=True)
                else:
                    df["timestamp"] = pd.to_datetime(ts, errors="coerce", utc=True)
        except Exception:
            df["timestamp"] = pd.to_datetime(ts, errors="coerce", utc=True)

    # Elimina filas sin close o timestamp
    if "close" in df.columns and "timestamp" in df.columns:
        df = df.dropna(subset=["close", "timestamp"]).sort_values("timestamp")

    return df.reset_index(drop=True)

def validar_columnas_requeridas(df: pd.DataFrame, required: List[str]) -> None:
    faltan = [c for c in required if c not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas requeridas: {faltan}")
    # Solo chequea NaN en columnas requeridas
    nan_cols = [c for c in required if df[c].isna().any()]
    if nan_cols:
        raise ValueError(f"Columnas requeridas con NaN: {nan_cols}")
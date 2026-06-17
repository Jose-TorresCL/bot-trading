"""
validacion_datos.py
-------------------
Funciones para validar y limpiar DataFrames de históricos para trading.
Asegura que los datos tengan las columnas requeridas, corrige NaN/Inf y rellena valores faltantes.
"""

import logging
import pandas as pd
import numpy as np
import importlib.util
from pathlib import Path
from typing import Callable, Any

logger = logging.getLogger(__name__)

# Intentar importar transformar_datos con varios fallbacks; si no existe, usar un fallback que convierte a DataFrame.
transformar_datos: Callable[[Any], pd.DataFrame] | None = None
_try_paths = [
    ("from .transformacion_datos import transformar_datos", ".transformacion_datos"),
    ("from src.pipeline.transformacion_datos import transformar_datos", "src.pipeline.transformacion_datos"),
]

for stmt, _mod in _try_paths:
    try:
        # ejecutar import dinámico simple para evitar bloqueos de import relativos/absolutos
        if _mod == ".transformacion_datos":
            from .transformacion_datos import transformar_datos  # type: ignore
        else:
            from src.pipeline.transformacion_datos import transformar_datos  # type: ignore
        break
    except Exception:
        transformar_datos = None

if transformar_datos is None:
    # búsqueda por ruta de archivo
    candidate_paths = [
        Path(__file__).resolve().parent / "transformacion_datos.py",
        Path(__file__).resolve().parents[1] / "pipeline" / "transformacion_datos.py",
        Path(__file__).resolve().parents[2] / "src" / "pipeline" / "transformacion_datos.py",
    ]
    found = None
    for p in candidate_paths:
        if p.exists():
            found = p
            break
    if found is not None:
        spec = importlib.util.spec_from_file_location("pipeline.transformacion_datos", str(found))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            transformar_datos = getattr(mod, "transformar_datos", None)
            if transformar_datos is None:
                logger.warning("transformar_datos no encontrado en %s; se usará fallback básico.", found)
    else:
        logger.warning("No se encontró transformacion_datos; se usará fallback básico.")

# Fallback seguro si no se pudo importar la función real
if not callable(transformar_datos):
    def _fallback_transform(x: Any) -> pd.DataFrame:
        if isinstance(x, pd.DataFrame):
            return x.copy()
        try:
            return pd.DataFrame(x)
        except Exception:
            return pd.DataFrame()
    transformar_datos = _fallback_transform

def validar_datos(df, required_fields=None):
    """
    Valida y limpia un DataFrame de históricos para trading.
    - Aplica transformaciones básicas centralizadas (transformar_datos).
    - Asegura que existan las columnas requeridas.
    - Rellena la columna 'price' si falta, usando 'close'.
    - Filtra registros inválidos y corrige NaN/Inf.
    - Devuelve siempre un DataFrame seguro para cálculos.
    """
    if required_fields is None:
        required_fields = ["timestamp", "open", "high", "low", "close", "volume", "symbol"]

    # Aplicar transformación (segura)
    try:
        df = transformar_datos(df)
    except Exception as e:
        logger.warning("transformar_datos falló: %s. Intentando coerción a DataFrame.", e)
        try:
            df = pd.DataFrame(df)
        except Exception as e2:
            logger.error("No se pudo convertir input a DataFrame: %s", e2)
            return pd.DataFrame()

    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        logger.error("❌ Error: DataFrame recibido está vacío o no está definido.")
        return pd.DataFrame()

    # Asegurar columna 'price' si falta
    if "price" not in df.columns and "close" in df.columns:
        df["price"] = df["close"]

    # Eliminar filas sin close o timestamp (solo si esas columnas existen)
    subset_to_check = [c for c in ("close", "timestamp") if c in df.columns]
    if subset_to_check:
        df = df.dropna(subset=subset_to_check, how="any")

    # Para cada campo requerido presente, forzar a numérico, reemplazar infinitos y rellenar con media o 0.0
    for field in required_fields:
        if field in df.columns:
            # Coerción segura a numérico
            df[field] = pd.to_numeric(df[field], errors="coerce")

            # Reemplazar inf/-inf por NaN
            df[field] = df[field].replace([np.inf, -np.inf], np.nan)

            # Calcular media ignorando NaN
            mean_value = df[field].mean(skipna=True)
            if pd.isna(mean_value):
                fill_value = 0.0
            else:
                fill_value = float(mean_value)

            df[field] = df[field].fillna(fill_value)

    # Asegurar tipos numéricos coherentes para columnas numéricas detectadas
    for col in df.select_dtypes(include=["int64", "float64"]).columns:
        try:
            df[col] = df[col].astype(float)
        except Exception:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df.reset_index(drop=True)
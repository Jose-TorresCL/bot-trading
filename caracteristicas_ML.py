import numpy as np
import logging
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GridSearchCV
import pandas as pd

# Configuración de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def crear_dataset(validated_data, indicadores):
    """ Ensambla los datos en un DataFrame con columnas organizadas y verifica que no haya valores NaN. """
    
    logging.info("🔄 Creando dataset de entrenamiento para ML...")

    df = pd.DataFrame(validated_data)
    
    for key, value in indicadores.items():
        df[key] = value if isinstance(value, list) else [value] * len(df)

    if df.isnull().sum().sum() > 0:
        logging.warning("⚠️ Hay valores NaN en el dataset, se reemplazarán por la media.")
        df.fillna(df.mean(), inplace=True)

    logging.info(f"✅ Dataset creado con {df.shape[0]} filas y {df.shape[1]} columnas.")
    return df

def generar_labels(df):
    """ Genera la variable objetivo (label) basada en variación del precio en la siguiente vela. """
    
    logging.info("🔄 Generando variable objetivo para el modelo...")
    
    df["label"] = np.where(df["close"].shift(-1) > df["close"], 1, 0)
    
    logging.info("✅ Variable objetivo generada.")
    return df



def generar_features(datos_historicos):
    """
    Genera una matriz de características combinando múltiples indicadores técnicos.
    Retorna un DataFrame normalizado con columnas [high, low, close, price].
    """

    # 🚀 Validación inicial de datos
    if datos_historicos is None or datos_historicos.empty or len(datos_historicos) < 50:
        logging.error("❌ Error: `datos_historicos` está vacío o tiene menos de 50 registros.")
        return None
    if not isinstance(datos_historicos, (list, pd.DataFrame)):
        logging.error("❌ Error: `datos_historicos` debe ser lista o DataFrame.")
        return None

    # 🔹 Conversión a DataFrame y creación de la columna 'price'
    df = datos_historicos.copy() if isinstance(datos_historicos, pd.DataFrame) else pd.DataFrame(datos_historicos)
    if "price" not in df.columns:
        df["price"] = df["close"]

    required_cols = ["high", "low", "close", "price"]
    if not all(col in df.columns for col in required_cols):
        logging.error("❌ Error: Faltan columnas requeridas en los datos históricos.")
        return None

    try:
        # 🔍 Detectar columnas con SOLO valores NaN
        nan_cols = df[required_cols].columns[df[required_cols].isnull().all()]
        if not nan_cols.empty:
            logging.error(f"❌ Columnas con SOLO NaN detectadas antes de limpiar: {nan_cols.tolist()}")
            return None  # 🚀 Retorno seguro antes de generar `features`

        # 🔹 Reemplazar NaN con el promedio SOLO en columnas con al menos un valor válido
        df_cleaned = df[required_cols].copy()
        df_cleaned = df_cleaned.apply(lambda col: col.fillna(col.mean()) if col.notnull().any() else col.fillna(0))

        # 🚀 Validación de NaN e infinitos después de la limpieza
        if df_cleaned.isnull().values.any():
            logging.error("❌ Error: Persisten valores NaN después de limpieza.")
            nan_columns = df_cleaned.columns[df_cleaned.isnull().any()]
            logging.warning(f"⚠️ Columnas afectadas: {nan_columns.tolist()}")
            return None

        if not np.isfinite(df_cleaned.values).all():
            logging.error("❌ Error: El DataFrame aún contiene valores infinitos.")
            return None

        # 🔹 Conversión a array NumPy
        features = df_cleaned.values
        if features.shape[0] != len(df_cleaned):
            logging.error(f"⚠️ Tamaño inconsistente entre `features` y `df_cleaned`: {features.shape[0]} vs {len(df_cleaned)}")
            return None

        if features.ndim < 2:
            features = features.reshape(-1, len(required_cols))

        if features.size == 0:
            logging.error("❌ Error: `features` ya está vacío antes de limpiar.")
            return None

        # 🚀 Normalización con StandardScaler
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features)

        # 🔹 Conversión a DataFrame
        df_features = pd.DataFrame(features_scaled, columns=required_cols)

        logging.info(f"✅ Características generadas y normalizadas. Tamaño: {df_features.shape}")
        return df_features

    except Exception as e:
        logging.error(f"❌ Error al generar características: {e}")
        return None




def clean_features(features):
    """Limpia los datos de características eliminando valores no válidos antes de enviarlos a ML."""
    try:
        if features.size == 0:
            logging.error("❌ Error: `features` ya está vacío antes de limpiar.")
            return None

        features_clean = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        if features_clean.size == 0 or not features_clean.any():
            logging.error("❌ Error: La matriz de características quedó vacía después de limpiar.")
            return None
        logging.info(f"✅ Datos de características limpiados. Dimensión: {features_clean.shape}")
        return features_clean
    except Exception as e:
        logging.error(f"❌ Error en la limpieza de datos: {e}")
        return None

def train_random_forest(df):
    """ Entrena el modelo ML con los datos estructurados. """
    
    logging.info("🔄 Entrenando modelo Random Forest...")

    X = df.drop(["timestamp", "label"], axis=1)
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    logging.info("✅ Modelo Random Forest entrenado con éxito.")
    return model

def train_random_forest(features, prices):
    """ Entrena modelo ML con validación cruzada y optimización. """
    features_clean = clean_features(features)

    if features_clean is None or features_clean.shape[0] < 3 or not isinstance(prices, np.ndarray) or prices.size == 0:
        logging.error("❌ Datos insuficientes para entrenar el modelo ML.")
        return None

    try:
        X_train, X_test, y_train, y_test = train_test_split(features_clean, prices, test_size=0.2, random_state=42)
        cv = min(5, max(2, len(X_train) // 2))

        param_grid = {"n_estimators": [50, 100, 200], "max_depth": [5, 10, None]}
        grid_search = GridSearchCV(RandomForestRegressor(random_state=42), param_grid, cv=cv)
        grid_search.fit(X_train, y_train)

        if grid_search.best_estimator_ is None:
            logging.error("❌ GridSearchCV no encontró un modelo válido.")
            return None

        model = grid_search.best_estimator_

        predictions = model.predict(X_test)
        error = mean_absolute_error(y_test, predictions)
        logging.info(f"✅ Modelo Random Forest entrenado - Error MAE: {error}")

        if len(y_test) > 1:
            score = model.score(X_test, y_test)
            logging.info(f"✅ R² score del modelo: {score}")
        else:
            logging.info("⚠️ No se calcula `R² score` porque hay menos de 2 muestras.")

        return model
    except Exception as e:
        logging.error(f"❌ Error al entrenar el modelo ML: {e}")
        return None

def predict_price(model, current_features):
    """ Realiza una predicción del próximo precio usando el modelo entrenado. """
    if model is None:
        logging.error("❌ No hay modelo entrenado para hacer predicciones.")
        return None

    try:
        current_features_clean = clean_features(np.array(current_features))

        if not isinstance(current_features_clean, np.ndarray):
            logging.error("❌ Error: `current_features_clean` no es un array válido.")
            return None

        if np.isnan(current_features_clean).sum() > 0 or np.isinf(current_features_clean).sum() > 0:
            logging.error("❌ Error: `current_features_clean` contiene valores inválidos.")
            return None

        if current_features_clean.size == 0 or not current_features_clean.any():
            logging.error("❌ Error: `current_features_clean` no contiene datos utilizables.")
            return None

        predicted_price = float(model.predict(current_features_clean.reshape(1, -1))[0])
        logging.info(f"⚡ Predicción de precio futura: {predicted_price}")
        return predicted_price

    except Exception as e:
        logging.error(f"❌ Error en la predicción de precios: {e}")
        return None

# 🔹 Ejemplo de uso:
df = pd.read_csv("historial_trading.csv")  # Asegura que tenga columna 'close'
features = generar_features(df)
prices = df["close"].values

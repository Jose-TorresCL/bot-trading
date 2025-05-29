# ================================================================
# CONFIGURACIÓN DE PARÁMETROS PARA ESTRATEGIAS Y BACKTESTING
# ================================================================
# Este archivo centraliza todos los parámetros usados por tu bot.
# Modifica los valores aquí o desde tu grid search para experimentar.
# ================================================================

# ==============================
# PARÁMETROS DE INDICADORES
# ==============================

# --- RSI ---
RSI_LIMIT_COMPRA = 40   # Señal de compra: RSI < este valor (ej: 45)
RSI_LIMIT_VENTA = 60    # Señal de venta:  RSI > este valor (ej: 80)

# --- ADX ---
ADX_LIMIT = 23         # Umbral mínimo para considerar tendencia (ej: >=25)
ADX_STRONG_TREND = 40   # (Opcional) Tendencia muy fuerte

# --- MACD ---
MACD_THRESHOLD = 3      # Diferencia mínima MACD vs señal para validar señal

# --- VOTOS MÍNIMOS PARA OPERAR ---
MIN_VOTES_COMPRA = 4   # Más alto = señales más selectivas
MIN_VOTES_VENTA = 2

# ==============================
# PARÁMETROS DE GESTIÓN DE RIESGO
# ==============================

SL_MULT = 3.0             # Stop-loss: x veces ATR (ej: 4 para menos agresivo)
TP_MULT = 2.0           # Take-profit: x veces ATR (ej: 2.5)
TRAILING_STOP = True    # ¿Activar trailing stop dinámico?

# ==============================
# AJUSTES PARA PRECISIÓN Y FILTROS
# ==============================

ATR_MIN = 50           # Mínimo ATR aceptado para evitar stops en rangos planos

# ==============================
# OTROS PARÁMETROS GLOBALES
# ==============================

COMISION = 0.00075      # Comisión estimada por operación (0.075%)
TAMANO_POSICION = 1.0   # Tamaño de posición por operación

# ==============================
# ESPACIO PARA NUEVOS PARÁMETROS EXPERIMENTALES
# ==============================

# Ejemplo:
# NUEVO_FILTRO_ON = False
# UMBRAL_X = 1.23
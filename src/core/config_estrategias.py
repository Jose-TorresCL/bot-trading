# from carpeta.config_estrategias import *

"""
config_estrategias.py
---------------------
Archivo centralizado de parámetros para estrategias y backtesting del bot de trading.
Modifica los valores aquí o desde tu grid search para experimentar.

Notas:
- Algunas variables como ADX_STRONG_TREND, MACD_THRESHOLD, COMISION y TAMANO_POSICION
  NO se usan actualmente en el flujo principal, pero se mantienen para posibles pruebas o extensiones.
"""

# ==============================
# PARÁMETROS DE INDICADORES
# ==============================

# --- RSI ---
RSI_LIMIT_COMPRA = 40   # Señal de compra: RSI < este valor (ej: 45)
RSI_LIMIT_VENTA = 60    # Señal de venta:  RSI > este valor (ej: 80)

# --- ADX ---
ADX_LIMIT = 23          # Umbral mínimo para considerar tendencia (ej: >=25)
ADX_STRONG_TREND = 40   # (NO USADA) Tendencia muy fuerte, variable experimental

# --- MACD ---
MACD_THRESHOLD = 3      # (NO USADA) Diferencia mínima MACD vs señal para validar señal

# --- VOTOS MÍNIMOS PARA OPERAR ---
MIN_VOTES_COMPRA = 4    # Más alto = señales más selectivas
MIN_VOTES_VENTA = 2

# ==============================
# PARÁMETROS DE GESTIÓN DE RIESGO
# ==============================

SL_MULT = 1.5           # Stop Loss (multiplicador ATR)
TP_MULT = 3.0           # Take Profit (multiplicador ATR)
TRAILING_STOP = 1.0     # Trailing Stop (multiplicador ATR)
ATR_MIN = 1.0           # ATR mínimo para filtrar mercados laterales

# --- Variables experimentales (NO USADAS) ---
COMISION = 0.00075      # (NO USADA) Comisión estimada por operación
TAMANO_POSICION = 0.1   # (NO USADA) Tamaño de posición por operación

# ==============================
# FILTROS Y AJUSTES AVANZADOS
# ==============================

FILTRO_VOLATILIDAD = True
MIN_VOLUME = 1000
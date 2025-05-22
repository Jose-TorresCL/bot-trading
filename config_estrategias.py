# ==============================
# Parámetros de indicadores
# ==============================

# RSI
RSI_LIMIT_COMPRA = 45    # Compra si RSI < 45 (zona de sobreventa)
RSI_LIMIT_VENTA = 80     # Venta si RSI > 80 (zona de sobrecompra)

# ADX
ADX_LIMIT = 25           # Mínimo para considerar tendencia (>=25)
ADX_STRONG_TREND = 40    # Opcional: tendencia muy fuerte

# Votos mínimos para señal (más alto = señales más selectivas)
MIN_VOTES_COMPRA = 4
MIN_VOTES_VENTA = 3

# ==============================
# Gestión de riesgo
# ==============================

SL_MULT = 4              # Stop-loss: 4 x ATR (menos agresivo que 1.5~3)
TP_MULT = 2.5            # Take-profit: 2.5 x ATR (ajusta según tu backtest)
TRAILING_STOP = True     # Protege ganancias cuando el precio sube/baja a favor

# ==============================
# Ajustes adicionales para precisión
# ==============================

ATR_MIN = 100            # Umbral mínimo para ATR (evita stops en mercados planos)
MACD_THRESHOLD = 3       # Filtro: diferencia mínima MACD vs señal para considerar válida la señal

# ==============================
# Otros parámetros globales
# ==============================
# (Agrega aquí si quieres nuevas reglas, filtros, o parámetros experimentales)
import logging
import json
from datetime import datetime
from config_estrategias import (
    RSI_LIMIT_COMPRA, RSI_LIMIT_VENTA, ADX_LIMIT,
    MIN_VOTES_COMPRA, MIN_VOTES_VENTA,
    SL_MULT, TP_MULT, TRAILING_STOP
)

logger = logging.getLogger(__name__)

# --- Utilidad para convertir Timestamps a string ---
def convertir_timestamps_a_str(obj):
    if isinstance(obj, dict):
        return {k: convertir_timestamps_a_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convertir_timestamps_a_str(i) for i in obj]
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        return obj


def evaluar_condiciones(indicadores, condiciones, min_votes):
    """
    Evalúa una lista de condiciones booleanas y retorna True si se alcanza el mínimo de votos requeridos.
    """
    if not isinstance(indicadores, dict):
        logger.error("❌ Indicadores deben ser un diccionario válido.")
        return False
    votes = sum(1 for cond in condiciones if cond)
    return votes >= min_votes

def estrategia_compra(indicadores):
    try:
        condiciones = [
            ("RSI", indicadores.get("RSI") is not None and indicadores["RSI"] < RSI_LIMIT_COMPRA),
            ("ADX", indicadores.get("ADX") is not None and indicadores["ADX"] > ADX_LIMIT),
            ("EMA", indicadores.get("EMA") is not None and indicadores["close"] > indicadores["EMA"]),
            ("MACD", indicadores.get("MACD") is not None and indicadores.get("MACD_signal") is not None and indicadores["MACD"] > indicadores["MACD_signal"]),
            ("Bollinger", indicadores.get("BB_Lower") is not None and indicadores["close"] < indicadores["BB_Lower"]),
            ("Ichimoku", 
                indicadores.get("Ichimoku_SpanA") is not None and 
                indicadores.get("Ichimoku_SpanB") is not None and 
                indicadores["Ichimoku_SpanA"] > indicadores["Ichimoku_SpanB"] and
                indicadores["close"] > indicadores["Ichimoku_SpanA"]
            )
        ]
        usados = [nombre for nombre, ok in condiciones if ok]
        resultado = evaluar_condiciones(indicadores, [ok for _, ok in condiciones], MIN_VOTES_COMPRA)
        return resultado, usados
    except Exception as e:
        logger.error(f"❌ Error en estrategia de compra: {e}")
        return False, []

def estrategia_venta(indicadores):
    try:
        condiciones = [
            ("RSI", indicadores.get("RSI") is not None and indicadores["RSI"] > RSI_LIMIT_VENTA),
            ("ADX", indicadores.get("ADX") is not None and indicadores["ADX"] > ADX_LIMIT),
            ("EMA", indicadores.get("EMA") is not None and indicadores["close"] < indicadores["EMA"]),
            ("MACD", indicadores.get("MACD") is not None and indicadores.get("MACD_signal") is not None and indicadores["MACD"] < indicadores["MACD_signal"]),
            ("Bollinger", indicadores.get("BB_Upper") is not None and indicadores["close"] > indicadores["BB_Upper"]),
            ("Ichimoku", 
                indicadores.get("Ichimoku_SpanA") is not None and 
                indicadores.get("Ichimoku_SpanB") is not None and 
                indicadores["Ichimoku_SpanA"] < indicadores["Ichimoku_SpanB"] and
                indicadores["close"] < indicadores["Ichimoku_SpanA"]
            )
        ]
        usados = [nombre for nombre, ok in condiciones if ok]
        resultado = evaluar_condiciones(indicadores, [ok for _, ok in condiciones], MIN_VOTES_VENTA)
        return resultado, usados
    except Exception as e:
        logger.error(f"❌ Error en estrategia de venta: {e}")
        return False, []

def gestion_riesgo(
    precio_compra,
    precio_actual,
    indicadores,
    mejor_precio=None,
    modo="compra",
    sl_mult=SL_MULT,
    tp_mult=TP_MULT,
    trailing_stop=TRAILING_STOP,
    margen_seguridad=0.001  # extra margen opcional
):
    try:
        atr = indicadores.get("ATR", 0)
        if atr <= 0:
            atr = max(0.01 * precio_compra, 1e-6)  # evita 0 y da mínimo seguro

        stop_loss = atr * sl_mult
        take_profit = atr * tp_mult

        if modo == "compra":
            stop_price = precio_compra - stop_loss
            take_price = precio_compra + take_profit

            # trailing stop dinámico (sube solo si mejora el precio)
            if trailing_stop and mejor_precio:
                stop_price = max(mejor_precio - stop_loss, stop_price)

            # Aplica margen de seguridad para evitar salir por fluctuación leve
            if precio_actual <= stop_price * (1 + margen_seguridad):
                logger.info(f"⚠️ SL activado en {precio_actual:.2f} | SL={stop_price:.2f}, ATR={atr:.2f}")
                return {"accion": "vender", "motivo": "stop_loss", "precio_activado": precio_actual}
            elif precio_actual >= take_price * (1 - margen_seguridad):
                logger.info(f"✅ TP activado en {precio_actual:.2f} | TP={take_price:.2f}, ATR={atr:.2f}")
                return {"accion": "vender", "motivo": "take_profit", "precio_activado": precio_actual}

        elif modo == "venta":
            stop_price = precio_compra + stop_loss
            take_price = precio_compra - take_profit

            if trailing_stop and mejor_precio:
                stop_price = min(mejor_precio + stop_loss, stop_price)

            if precio_actual >= stop_price * (1 - margen_seguridad):
                logger.info(f"⚠️ SL activado en {precio_actual:.2f} | SL={stop_price:.2f}, ATR={atr:.2f}")
                return {"accion": "comprar", "motivo": "stop_loss", "precio_activado": precio_actual}
            elif precio_actual <= take_price * (1 + margen_seguridad):
                logger.info(f"✅ TP activado en {precio_actual:.2f} | TP={take_price:.2f}, ATR={atr:.2f}")
                return {"accion": "comprar", "motivo": "take_profit", "precio_activado": precio_actual}

        return {"accion": None, "motivo": "mantener", "precio_activado": precio_actual}
    
    except Exception as e:
        logger.error(f"❌ Error en gestión de riesgo: {e}")
        return {"accion": None, "motivo": "error", "error": str(e)}

def registrar_decisiones(tipo_operacion, precio, condiciones, resultado, usados=None, log_file="registro_decisiones.json"):
    """
    Registra decisiones de compra/venta en JSON con formato optimizado.
    """
    try:
        if not isinstance(condiciones, dict):
            logger.error("❌ Condiciones debe ser un diccionario válido.")
            return

        log_entry = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "operacion": tipo_operacion.upper(),
            "precio": float(round(precio, 2)),
            "condiciones": convertir_timestamps_a_str(condiciones),
            "resultado": resultado,
            "indicadores_usados": usados or []
        }

        with open(log_file, "a", encoding="utf-8") as file:
            json.dump(log_entry, file, indent=4, ensure_ascii=False)
            file.write("\n")

        logger.info(f"📊 Decisión registrada: {log_entry}")  # Solo irá al archivo, no a la consola
    except Exception as e:
        logger.error(f"❌ Error al registrar decisión: {e}")

print(f"[DEBUG] RSI_LIMIT_COMPRA desde config_estrategias: {RSI_LIMIT_COMPRA}")
print(f"[DEBUG] SL_MULT desde config_estrategias: {SL_MULT}")
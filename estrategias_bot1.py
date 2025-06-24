import logging
import json
from datetime import datetime
import config_estrategias

logger = logging.getLogger(__name__)

def convertir_timestamps_a_str(obj):
    if isinstance(obj, dict):
        return {k: convertir_timestamps_a_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convertir_timestamps_a_str(i) for i in obj]
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        return obj

def evaluar_votacion(condiciones, nombres, min_votos, tipo="compra"):
    usados = [nombre for cond, nombre in zip(condiciones, nombres) if cond]
    votos = sum(condiciones)
    logger.info(f"Evaluación {tipo}: votos={votos}/{len(condiciones)} | usados={usados}")
    return votos >= min_votos, usados

def estrategia_compra(
    indicadores,
    rsi_limit=None,
    adx_limit=None,
    min_votes=None,
    atr_min=None
):
    import config_estrategias
    rsi_limit = rsi_limit if rsi_limit is not None else config_estrategias.RSI_LIMIT_COMPRA
    adx_limit = adx_limit if adx_limit is not None else config_estrategias.ADX_LIMIT
    min_votes = min_votes if min_votes is not None else config_estrategias.MIN_VOTES_COMPRA
    atr_min = atr_min if atr_min is not None else config_estrategias.ATR_MIN

    condiciones = [
        indicadores.get("RSI") is not None and indicadores["RSI"] < rsi_limit,
        indicadores.get("ADX") is not None and indicadores["ADX"] >= adx_limit,
        indicadores.get("MACD_hist", 0) > 0,
        indicadores.get("BB_Lower") is not None and indicadores.get("close", 0) < indicadores["BB_Lower"],
        indicadores.get("Ichimoku_Tenkan") is not None and indicadores.get("close", 0) > indicadores["Ichimoku_Tenkan"],
        indicadores.get("ATR") is not None and indicadores["ATR"] > atr_min
    ]
    nombres = ["RSI", "ADX", "MACD_hist", "BB_Lower", "Ichimoku_Tenkan", "ATR"]
    return evaluar_votacion(condiciones, nombres, min_votes, tipo="compra")

def estrategia_venta(
    indicadores,
    rsi_limit=None,
    adx_limit=None,
    min_votes=None,
    atr_min=None
):
    import config_estrategias
    # Usa los valores pasados o los de config
    rsi_limit = rsi_limit if rsi_limit is not None else config_estrategias.RSI_LIMIT_VENTA
    adx_limit = adx_limit if adx_limit is not None else config_estrategias.ADX_LIMIT
    min_votes = min_votes if min_votes is not None else config_estrategias.MIN_VOTES_VENTA
    atr_min = atr_min if atr_min is not None else getattr(config_estrategias, "ATR_MIN", 0)

    condiciones = [
        indicadores.get("RSI") is not None and indicadores["RSI"] > rsi_limit,
        indicadores.get("ADX") is not None and indicadores["ADX"] >= adx_limit,
        indicadores.get("MACD_hist", 0) < 0,
        indicadores.get("BB_Upper") is not None and indicadores.get("close", 0) > indicadores["BB_Upper"],
        indicadores.get("Ichimoku_Tenkan") is not None and indicadores.get("close", 0) < indicadores["Ichimoku_Tenkan"],
        indicadores.get("ATR") is not None and indicadores["ATR"] > atr_min
    ]
    nombres = ["RSI", "ADX", "MACD_hist", "BB_Upper", "Ichimoku_Tenkan", "ATR"]
    return evaluar_votacion(condiciones, nombres, min_votes, tipo="venta")

def gestion_riesgo(
    precio_compra,
    precio_actual,
    indicadores,
    mejor_precio=None,
    modo="compra",
    sl_mult=None,
    tp_mult=None,
    trailing_stop=None,
    margen_seguridad=0.001,
    atr_min=None  # <-- agrega esto
):
    try:
        sl_mult = sl_mult if sl_mult is not None else config_estrategias.SL_MULT
        tp_mult = tp_mult if tp_mult is not None else config_estrategias.TP_MULT
        trailing_stop = trailing_stop if trailing_stop is not None else config_estrategias.TRAILING_STOP
        atr_min = atr_min if atr_min is not None else getattr(config_estrategias, "ATR_MIN", 2)

        atr = indicadores.get("ATR", 0)
        if atr < atr_min:
            logger.warning(f"ATR ({atr:.2f}) menor que ATR_MIN ({atr_min}), usando ATR_MIN para gestión de riesgo.")
            atr = atr_min
        if atr <= 0:
            atr = max(0.01 * precio_compra, 1e-6)

        stop_loss = atr * sl_mult
        take_profit = atr * tp_mult

        if modo == "compra":
            stop_price = precio_compra - stop_loss
            take_price = precio_compra + take_profit

            if trailing_stop and mejor_precio:
                stop_price = max(mejor_precio - stop_loss, stop_price)

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
    try:
        log_entry = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "operacion": tipo_operacion.upper(),
            "precio": float(round(precio, 2)),
            "condiciones": convertir_timestamps_a_str(condiciones),
            "resultado": resultado,
            "indicadores_usados": usados or []
        }
        with open(log_file, "a", encoding="utf-8") as file:
            json.dump(log_entry, file, ensure_ascii=False)
            file.write("\n")
        logger.info(f"📊 Decisión registrada: {log_entry}")
    except Exception as e:
        logger.error(f"❌ Error al registrar decisión: {e}")
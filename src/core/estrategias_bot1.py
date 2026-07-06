"""
estrategias_bot1.py
-------------------
Funciones para definir y evaluar estrategias de compra/venta, gestión de riesgo y registro de decisiones.
Centraliza la lógica de votación y condiciones para operar.
"""

import logging
import json
import csv
import os
from datetime import datetime
# antiguo (provocaba ImportError al importar desde 'src')
#from src import config_estrategias
# nuevo: intenta import relativo primero, luego absoluto dentro del paquete y finalmente fallback
try:
    from . import config_estrategias
except Exception:
    try:
        from src.core import config_estrategias
    except Exception:
        # último recurso: intentar importar módulo por nombre (útil para ejecuciones sueltas)
        import config_estrategias as config_estrategias

import pandas as pd
from typing import Tuple, List, Dict, Any, Optional, Union

# Writer JSONL opcional (centralización de logs estructurados)
try:
    from src.auxiliares.simple_jsonl_writer import CompactJsonlGzipWriter  # type: ignore
except Exception:
    CompactJsonlGzipWriter = None  # fallback: no writer optimizado

logger = logging.getLogger(__name__)

def _safe_float(x: Any) -> float:
    """Convierte a float de forma segura; retorna 0.0 si no es convertible."""
    try:
        return float(x)
    except Exception:
        try:
            # listas/tuplas -> intentar primer elemento
            if isinstance(x, (list, tuple)) and len(x) > 0:
                return float(x[0])
        except Exception:
            pass
        return 0.0

def convertir_timestamps_a_str(obj):
    """
    Convierte todos los timestamps a string para exportación.
    """
    if isinstance(obj, dict):
        return {k: convertir_timestamps_a_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convertir_timestamps_a_str(i) for i in obj]
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        return obj

def evaluar_votacion(condiciones, nombres, min_votos, tipo="compra"):
    """
    Evalúa las condiciones y retorna si se cumple el mínimo de votos.
    """
    usados = [nombre for cond, nombre in zip(condiciones, nombres) if cond]
    votos = sum(condiciones)
    logger.info(f"Evaluación {tipo}: votos={votos}/{len(condiciones)} | usados={usados}")
    return votos >= min_votos, usados

def registrar_decisiones(
    evento: str,
    precio: float,
    timestamp: Any = None,
    indicadores: Optional[Dict[str, Any]] = None,
    modo: Optional[str] = None,
    origen: Optional[str] = None,
    estrategia: Optional[str] = None,
    version: Optional[str] = None,
    debug_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Registra decisiones/señales con metadata.

    Parámetros:
    - evento: 'compra' | 'venta' | ...
    - precio: precio asociado a la decisión
    - timestamp: fecha/hora; se normaliza a UTC (acepta str/int/pd.Timestamp)
    - indicadores: snapshot de indicadores (opcional)
    - modo: etiqueta de modo ('simulada', 'aprobado', ...)
    - origen: contexto opcional
    - estrategia: nombre de la estrategia (opcional)
    - version: versión de la estrategia (opcional)
    - debug_info: dict con detalles adicionales para trazabilidad (opcional)

    Retorna:
    - payload (dict) con la decisión registrada.

    Notas:
    - Si está disponible "CompactJsonlGzipWriter", se intenta escribir en JSONL comprimido.
    - Ruta de salida por defecto: data/logs/decisiones.jsonl.gz
    """
    try:
        # si se pasa un timestamp histórico, usarlo (acepta pd.Timestamp, datetime o int/ms)
        if timestamp is not None:
            try:
                ts = pd.to_datetime(timestamp, utc=True, errors="coerce")
                # forzar timezone UTC
                if ts.tzinfo is None and pd.notna(ts):
                    ts = ts.tz_localize("UTC")
                ts_iso = ts.isoformat() if pd.notna(ts) else pd.Timestamp.utcnow().tz_localize("UTC").isoformat()
            except Exception:
                ts_iso = pd.Timestamp.utcnow().tz_localize("UTC").isoformat()
        else:
            ts_iso = pd.Timestamp.utcnow().tz_localize("UTC").isoformat()

        payload = {
            "evento": evento,
            "precio": float(precio) if precio is not None else None,
            "timestamp": ts_iso,
            "indicadores": indicadores.copy() if isinstance(indicadores, dict) else indicadores,
            "modo": modo,
            "origen": origen,
            "estrategia": estrategia,
            "version": version,
            "debug_info": debug_info,
        }
    except Exception:
        payload = {
            "evento": evento,
            "precio": precio,
            "timestamp": str(pd.Timestamp.utcnow().tz_localize("UTC")),
            "indicadores": indicadores,
            "modo": modo,
            "origen": origen,
            "estrategia": estrategia,
            "version": version,
            "debug_info": debug_info,
        }

    # Loguear y/o almacenar según implementación previa (no romper flujo si falla)
    try:
        logger = logging.getLogger(__name__)
        logger.info("Registrar decisión: %s", payload)
    except Exception:
        pass

    # Escritura centralizada en JSONL si el writer está disponible; fallback a gzip manual
    try:
        os.makedirs("data/logs", exist_ok=True)
        out_path = os.path.join("data", "logs", "decisiones.jsonl.gz")
        if CompactJsonlGzipWriter is not None:
            # crear una instancia efímera para escribir 1 registro (buffer=1)
            w = CompactJsonlGzipWriter(out_path, batch_size=1)
            w.write(payload)
            w.close()
        else:
            import gzip
            line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            with gzip.open(out_path, "ab") as f:
                f.write(line)
    except Exception as e:
        logger.warning("No se pudo persistir la decisión en JSONL: %s", e)

    # Si existía lógica adicional para persistir, mantenerla aquí (no raise)
    return payload

def estrategia_compra(
    indicadores: Dict[str, Any],
    rsi_dynamic: float = 30,
    adx_limit: float = 25,
    min_votes: int = 1,
    atr_min: Optional[float] = None,
    bb_width_min: Optional[float] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    debug: bool = False,
) -> Union[Tuple[bool, List[str]], Tuple[bool, List[str], Dict[str, Any]]]:
    """Estrategia de compra basada en indicadores.

    Parámetros:
    - indicadores: dict con claves esperadas: RSI, ADX, ATR, BB_Width, votes
    - rsi_dynamic: umbral RSI para compra (RSI < rsi_dynamic)
    - adx_limit: umbral ADX mínimo
    - min_votes: votos mínimos requeridos
    - atr_min: filtro de volatilidad mínima por ATR
    - bb_width_min: filtro de consolidación (ancho de bandas)
    - thresholds: dict opcional que sobrescribe los umbrales anteriores (p.ej. {"rsi_dynamic": 35, "adx_limit": 23})
    - debug: si True, devuelve también un dict con valores evaluados

    Retorna:
    - (resultado_bool, usados) cuando debug=False
    - (resultado_bool, usados, debug_info) cuando debug=True

    Ejemplo:
        ok, usados = estrategia_compra(indicadores, thresholds={"rsi_dynamic": 35})
        ok, usados, dbg = estrategia_compra(indicadores, debug=True)
    """
    used = []
    dbg: Dict[str, Any] = {}
    try:
        # aplicar thresholds personalizados si vienen
        if thresholds:
            rsi_dynamic = float(thresholds.get("rsi_dynamic", rsi_dynamic))
            adx_limit = float(thresholds.get("adx_limit", adx_limit))
            min_votes = int(thresholds.get("min_votes", min_votes))
            atr_min = float(thresholds.get("atr_min", atr_min)) if thresholds.get("atr_min") is not None else atr_min
            bb_width_min = float(thresholds.get("bb_width_min", bb_width_min)) if thresholds.get("bb_width_min") is not None else bb_width_min

        rsi = indicadores.get("RSI")
        adx_raw = indicadores.get("ADX", 0)
        # normalizar ADX (acepta scalar o lista/tupla)
        if isinstance(adx_raw, (list, tuple)):
            adx = _safe_float(adx_raw[0] if len(adx_raw) > 0 else 0.0)
        else:
            adx = _safe_float(adx_raw)
        atr = indicadores.get("ATR", 0)
        bbw = indicadores.get("BB_Width", None)
        votes = int(indicadores.get("votes", 1) or 0)
        # Filtros de tendencia
        tenkan = indicadores.get("Tenkan")
        kijun = indicadores.get("Kijun")

        dbg.update({
            "RSI": rsi,
            "ADX": adx,
            "ATR": atr,
            "BB_Width": bbw,
            "votes": votes,
            "thr": {
                "rsi_dynamic": rsi_dynamic,
                "adx_limit": adx_limit,
                "min_votes": min_votes,
                "atr_min": atr_min,
                "bb_width_min": bb_width_min,
            },
        })

        if rsi is not None:
            used.append("RSI")
            if not (rsi < rsi_dynamic):
                return (False, used, dbg) if debug else (False, used)

        
        # Filtro Ichimoku: confirmar tendencia UP
        if tenkan is not None and kijun is not None:
            try:
                used.append("Ichimoku")
                if not (float(tenkan) > float(kijun)):
                    return (False, used, dbg) if debug else (False, used)
            except Exception:
                pass

        # adx ya normalizado
        used.append("ADX")
        if adx < adx_limit:
            return (False, used, dbg) if debug else (False, used)

        if atr_min is not None:
            used.append("ATR")
            if atr is None or atr < atr_min:
                return (False, used, dbg) if debug else (False, used)

        if bb_width_min is not None:
            used.append("BB_Width")
            if bbw is None or bbw < bb_width_min:
                return (False, used, dbg) if debug else (False, used)

        # votes (simple)
        if votes < min_votes:
            return (False, used, dbg) if debug else (False, used)

        return (True, used, dbg) if debug else (True, used)
    except Exception as e:
        logger.exception("Error en estrategia_compra: %s", e)
        return (False, [], dbg) if debug else (False, [])

def estrategia_venta(
    indicadores: Dict[str, Any],
    rsi_dynamic: float = 70,
    adx_limit: float = 25,
    min_votes: int = 1,
    bb_width_min: Optional[float] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    debug: bool = False,
) -> Union[Tuple[bool, List[str]], Tuple[bool, List[str], Dict[str, Any]]]:
    """Estrategia de venta (simétrica) con modo debug y thresholds personalizados.

    Ver parámetros y comportamiento en estrategia_compra.
    """
    used = []
    dbg: Dict[str, Any] = {}
    try:
        if thresholds:
            rsi_dynamic = float(thresholds.get("rsi_dynamic", rsi_dynamic))
            adx_limit = float(thresholds.get("adx_limit", adx_limit))
            min_votes = int(thresholds.get("min_votes", min_votes))
            bb_width_min = float(thresholds.get("bb_width_min", bb_width_min)) if thresholds.get("bb_width_min") is not None else bb_width_min

        rsi = indicadores.get("RSI")
        adx_raw = indicadores.get("ADX", 0)
        # normalizar ADX (acepta scalar o lista/tupla)
        if isinstance(adx_raw, (list, tuple)):
            adx = _safe_float(adx_raw[0] if len(adx_raw) > 0 else 0.0)
        else:
            adx = _safe_float(adx_raw)
        atr = indicadores.get("ATR", 0)
        bbw = indicadores.get("BB_Width", None)
        votes = int(indicadores.get("votes", 1) or 0)
        
        # Filtros de tendencia
        tenkan = indicadores.get("Tenkan")
        kijun = indicadores.get("Kijun")


        dbg.update({
            "RSI": rsi,
            "ADX": adx,
            "ATR": atr,
            "BB_Width": bbw,
            "votes": votes,
            "thr": {
                "rsi_dynamic": rsi_dynamic,
                "adx_limit": adx_limit,
                "min_votes": min_votes,
                "bb_width_min": bb_width_min,
            },
        })

        if rsi is not None:
            used.append("RSI")
            if not (rsi > rsi_dynamic):
                return (False, used, dbg) if debug else (False, used)

        used.append("ADX")
        if adx < adx_limit:
            return (False, used, dbg) if debug else (False, used)

        if bb_width_min is not None:
            used.append("BB_Width")
            if bbw is None or bbw < bb_width_min:
                return (False, used, dbg) if debug else (False, used)

        if votes < min_votes:
            return (False, used, dbg) if debug else (False, used)

        return (True, used, dbg) if debug else (True, used)
    except Exception as e:
        logger.exception("Error en estrategia_venta: %s", e)
        return (False, [], dbg) if debug else (False, [])

def gestion_riesgo(
    precio_entrada: float,
    precio_actual: float,
    indicadores: Dict[str, Any],
    mejor_precio: Optional[float] = None,
    modo: str = "compra",
    sl_mult: float = 1.0,
    tp_mult: float = 2.0,
    trailing_stop: bool = False,
    atr_min: Optional[float] = None,
    evaluar_sin_accion: bool = False,
) -> Dict[str, Any]:
    """Calcula niveles de SL/TP y sugiere acción según el modo.

    - SL = sl_mult * ATR, TP = tp_mult * ATR
    - Breakeven cuando alcanza +1R
    - Trailing stop si trailing_stop=True y mejor_precio definido

    Parámetros extra:
    - evaluar_sin_accion: si True, solo calcula niveles y R_ratio, no sugiere acción.

    Retorna:
    - dict con claves: accion (opcional), motivo, stop_price, take_price, R_ratio, nivel_riesgo

    Ejemplo:
        out = gestion_riesgo(100.0, 101.2, indicadores, modo="compra", sl_mult=1.0, tp_mult=2.0, evaluar_sin_accion=True)
    """
    try:
        atr = float(indicadores.get("ATR") or 0.0)
        if atr_min and atr < atr_min:
            atr = float(atr_min)
        if atr <= 0:
            atr = max(0.001 * float(precio_entrada), 1e-6)

        stop_move = atr * float(sl_mult)
        take_move = atr * float(tp_mult)

        # calcular stop/take de referencia según modo
        if modo == "compra":
            stop_price = float(precio_entrada) - stop_move
            sl_original = stop_price
            take_price = float(precio_entrada) + take_move
            # breakeven cuando alcance +1R
            if float(precio_actual) >= float(precio_entrada) + stop_move:
                stop_price = float(precio_entrada)
            # trailing
            if trailing_stop and mejor_precio is not None:
                stop_price = max(stop_price, float(mejor_precio) - stop_move)
            # R actual
            r_ratio = (float(precio_actual) - float(precio_entrada)) / stop_move if stop_move != 0 else 0.0
            accion_sugerida = None
            motivo = "mantener"
            if not evaluar_sin_accion:
                if float(precio_actual) <= stop_price:
                    accion_sugerida, motivo = "vender", "stop_loss"
                elif float(precio_actual) >= take_price:
                    accion_sugerida, motivo = "vender", "take_profit"
        else:
            stop_price = float(precio_entrada) + stop_move
            take_price = float(precio_entrada) - take_move
            sl_original = stop_price
            if float(precio_actual) <= float(precio_entrada) - stop_move:
                stop_price = float(precio_entrada)
            if trailing_stop and mejor_precio is not None:
                stop_price = min(stop_price, float(mejor_precio) + stop_move)
            r_ratio = (float(precio_entrada) - float(precio_actual)) / stop_move if stop_move != 0 else 0.0
            accion_sugerida = None
            motivo = "mantener"
            if not evaluar_sin_accion:
                if float(precio_actual) >= stop_price:
                    accion_sugerida, motivo = "comprar", "stop_loss"
                elif float(precio_actual) <= take_price:
                    accion_sugerida, motivo = "comprar", "take_profit"

        nivel_riesgo = (
            "breakeven" if abs(r_ratio) < 1.0 else ("favorable" if r_ratio >= 1.0 else "riesgo")
        )

        # Detectar si se activó SL o TP
        hit_sl = float(precio_actual) <= sl_original if modo == "compra" else float(precio_actual) >= sl_original
        hit_tp = float(precio_actual) >= take_price if modo == "compra" else float(precio_actual) <= take_price

        out = {
            "accion": accion_sugerida,
            "motivo": motivo,
            "precio_activado": float(precio_actual),
            "stop_price": float(stop_price),
            "take_price": float(take_price),
            "R_ratio": float(r_ratio),
            "nivel_riesgo": nivel_riesgo,
            "hit_sl": hit_sl,
            "hit_tp": hit_tp,
        }
        return out
    except Exception as e:
        logger.exception("Error en gestion_riesgo: %s", e)
        return {"accion": None, "motivo": "error", "error": str(e)}

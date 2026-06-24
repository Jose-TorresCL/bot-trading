"""
ciclo_real.py
-------------
Funciones para ejecutar ciclos de trading en tiempo real y simulación (paper trading).
Incluye obtención de datos, cálculo de indicadores, toma de decisiones y registro de operaciones.
"""

import logging
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import time
import json
import os
import pandas as pd
from typing import Any, Dict, Optional, List, Union, Sequence, Mapping, cast

from src.pipeline.conexion_api import get_historical_data, connect_to_binance
from src.core.estrategias_bot1 import estrategia_compra, estrategia_venta, registrar_decisiones, gestion_riesgo
from src.core.gestor_indicadores import calcular_todos_los_indicadores

logger = logging.getLogger("ciclo_real")

def _to_dataframe(maybe_df: Union[pd.DataFrame, List[Dict[str, Any]]]) -> Optional[pd.DataFrame]:
    """
    Acepta un DataFrame o una lista de dicts (respuesta API) y devuelve DataFrame.
    """
    if maybe_df is None:
        return None
    if isinstance(maybe_df, pd.DataFrame):
        return maybe_df
    try:
        return pd.DataFrame(maybe_df)
    except Exception:
        return None

def _strategy_bool(result: Any) -> bool:
    """
    Normaliza el retorno de las funciones de estrategia:
    - si devuelven (bool, details) toma el primer elemento
    - si devuelven bool lo devuelve
    - cualquier otra cosa -> False
    """
    if isinstance(result, tuple) and len(result) >= 1:
        return bool(result[0])
    return bool(result)

def evaluar_indicadores(indicadores_lista: Sequence[Mapping[str, Any]]):
    """
    Evalúa una lista de indicadores y devuelve recomendaciones simples.
    """
    recomendaciones = []
    for indicador in indicadores_lista:
        indicador_dict = cast(Dict[str, Any], dict(indicador))
        compra = _strategy_bool(estrategia_compra(indicador_dict))
        venta = _strategy_bool(estrategia_venta(indicador_dict))
        if compra and not venta:
            recomendaciones.append("compra")
        elif venta and not compra:
            recomendaciones.append("venta")
        else:
            recomendaciones.append("mantener")
    return recomendaciones

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def obtener_datos_historicos(symbol="ETHUSDT", limit=500) -> Optional[pd.DataFrame]:
    """
    Obtiene datos históricos solo desde Binance y devuelve un DataFrame.
    """
    logging.info("🌍 Conectando a Binance para obtener datos reales...")
    client = connect_to_binance()
    if not client:
        logging.error("❌ No se pudo conectar a Binance. Se detiene el bot.")
        return None
    historical_data = get_historical_data(symbol=symbol, limit=limit, client=client)
    df = _to_dataframe(historical_data)
    if df is None or df.empty or len(df) < 50:
        logging.error("❌ No se pudieron obtener suficientes datos históricos.")
        return None
    logging.info(f"✅ Datos históricos obtenidos con {len(df)} registros.")
    return df

def ejecutar_ciclo():
    """
    Ejecuta un ciclo del bot en modo paper trading (solo simula operaciones).
    """
    logging.info("🔄 Iniciando ciclo de trading...")
    historical_data = obtener_datos_historicos()
    if historical_data is None or historical_data.empty or len(historical_data) < 50:
        logging.error("❌ No se pudieron obtener suficientes datos históricos para el ciclo.")
        return

    indicadores_lista = calcular_todos_los_indicadores(historical_data)
    if not indicadores_lista:
        logging.warning("⚠️ No se generaron indicadores válidos.")
        return

    recomendaciones = evaluar_indicadores(indicadores_lista)
    logging.info(f"📊 Recomendaciones basadas en indicadores: {recomendaciones}")

    ultima_data = historical_data.iloc[-1]
    precio_actual = float(ultima_data["close"])

    ultimo_indicador = indicadores_lista[-1] if indicadores_lista else {}
    indicadores_clave = ["RSI", "MACD", "ATR"]
    if not (isinstance(ultimo_indicador, dict) and ultimo_indicador and all(ultimo_indicador.get(k) is not None for k in indicadores_clave)):
        logging.warning("⚠️ Indicadores clave no disponibles o no válidos para estrategia.")
        decision = None
    else:
        decision = tomar_decision(ultimo_indicador)

    if decision:
        # usar llamada posicional para evitar mismatch de kwargs
        try:
            registrar_decisiones(decision, precio_actual, ultimo_indicador, "simulada")
        except Exception:
            pass
    logging.info("✅ Ciclo de trading completado.")
    return historical_data

def tomar_decision(indicadores):
    """
    Evalúa la estrategia de compra o venta y devuelve la decisión.
    """
    indicadores = cast(Dict[str, Any], indicadores)
    compra = _strategy_bool(estrategia_compra(indicadores))
    venta = _strategy_bool(estrategia_venta(indicadores))
    if compra and not venta:
        logging.info("✅ Oportunidad de compra detectada (SIMULADA).")
        return "compra"
    if venta and not compra:
        logging.info("✅ Oportunidad de venta detectada (SIMULADA).")
        return "venta"
    return None

def ejecutar_ciclo_paper_trading(symbol: str = "BTCUSDT",
                                 intervalo: int = 60,
                                 modo: str = "paper",
                                 capital_inicial: float = 100.0,
                                 tamaño_posicion: float = 1.0):
    """
    Ciclo de paper trading.
    """
    saldo_virtual = capital_inicial
    posicion_abierta = False
    precio_entrada: Optional[float] = None
    lado: Optional[str] = None  # 'compra' o 'venta'

    logger.info("🔄 Iniciando ciclo de paper trading... saldo=%.2f", saldo_virtual)

    while True:
        try:
            logger.info("▶️ Ciclo (%s) símbolo=%s saldo=%.2f pos=%s", modo, symbol, saldo_virtual,
                        f"{lado}@{precio_entrada}" if posicion_abierta else "ninguna")

            client = connect_to_binance()
            if client is None:
                logger.warning("Sin cliente Binance; reintentando en %ss", intervalo)
                time.sleep(intervalo)
                continue

            data = get_historical_data(symbol=symbol, interval="1m", limit=100, client=client)
            df = _to_dataframe(data)
            if df is None or df.empty:
                logger.warning("DF vacío; sleep %ss", intervalo)
                time.sleep(intervalo)
                continue

            # Normalización mínima
            if df["timestamp"].dtype == object:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
            df = df.dropna(subset=["open","high","low","close"]).sort_values("timestamp")

            indicadores_lista = calcular_todos_los_indicadores(df)
            if not indicadores_lista:
                logger.warning("Sin indicadores.")
                time.sleep(intervalo)
                continue
            ind = cast(Dict[str, Any], indicadores_lista[-1])

            # Estrategias (normalizar retorno)
            buy = _strategy_bool(estrategia_compra(cast(Dict[str, Any], ind)))
            sell = _strategy_bool(estrategia_venta(cast(Dict[str, Any], ind)))

            precio_actual = None
            try:
                precio_actual = float(df.iloc[-1]["close"])
            except Exception:
                logger.warning("Precio actual inválido; salto ciclo.")
                time.sleep(intervalo)
                continue

            # Entrada
            if not posicion_abierta:
                if buy:
                    posicion_abierta = True
                    lado = "compra"
                    precio_entrada = precio_actual
                    try:
                        registrar_decisiones("compra", precio_actual, ind, "aprobado")
                    except Exception:
                        pass
                    logger.info("➡️ Abre LONG @ %.4f", precio_actual)
                elif sell:
                    posicion_abierta = True
                    lado = "venta"
                    precio_entrada = precio_actual
                    try:
                        registrar_decisiones("venta", precio_actual, ind, "aprobado")
                    except Exception:
                        pass
                    logger.info("➡️ Abre SHORT @ %.4f", precio_actual)

            # Salida con SL/TP ejecutado
            else:
                # Evaluar STOP-LOSS y TAKE-PROFIT
                risk_eval = gestion_riesgo(
                    precio_entrada=precio_entrada,
                    precio_actual=precio_actual,
                    indicadores=ind,
                    modo=lado,
                    sl_mult=1.5,
                    tp_mult=2.5,
                    trailing_stop=False
                )
                logger.info("SL=%.4f TP=%.4f ATR=%.4f hit_sl=%s hit_tp=%s", risk_eval.get("stop_price",0), risk_eval.get("take_price",0), float((ind or {}).get("ATR") or 0), risk_eval.get("hit_sl"), risk_eval.get("hit_tp"))
                
                cerrar = False
                cierre_razon = "estrategia"
                
                # PRIMERO: Verificar SL
                if risk_eval.get("hit_sl"):
                    cerrar = True
                    cierre_razon = "stop_loss"
                    logger.warning("⛔ STOP-LOSS ACTIVADO @ %.4f", precio_actual)
                # SEGUNDO: Verificar TP
                elif risk_eval.get("hit_tp"):
                    cerrar = True
                    cierre_razon = "take_profit"
                    logger.info("✅ TAKE-PROFIT ACTIVADO @ %.4f", precio_actual)
                # TERCERO: Señal opuesta
                elif (lado == "compra" and sell) or (lado == "venta" and buy):
                    cerrar = True
                    cierre_razon = "señal_opuesta"
                    logger.info("🔄 Señal opuesta detectada")
                
                if cerrar:
                    if precio_entrada is None:
                        logger.warning("Precio de entrada desconocido; no se puede calcular PnL.")
                    else:
                        if lado == "compra":
                            pnl = (precio_actual - precio_entrada) * tamaño_posicion
                        else:
                            pnl = (precio_entrada - precio_actual) * tamaño_posicion
                        
                        saldo_virtual += float(pnl)
                        logger.info("⬅️ Cierra %s @ %.4f pnl=%.4f saldo=%.2f [%s]",
                                    (lado or "").upper(), precio_actual, pnl, saldo_virtual, cierre_razon)
                        try:
                            registrar_decisiones("cierre", precio_actual, ind, "cerrado")
                        except Exception:
                            pass
                    
                    posicion_abierta = False
                    precio_entrada = None
                    lado = None

        except KeyboardInterrupt:
            logger.info("⛔ Interrumpido. Saldo final=%.2f", saldo_virtual)
            break
        except Exception as e:
            logger.error("Error en ciclo de paper trading: %s", e)

        time.sleep(intervalo)

def obtener_precio_actual(symbol):
    """
    Obtiene el precio actual de un símbolo en Binance.
    """
    client = connect_to_binance()
    if not client:
        logging.error("❌ No se pudo conectar a Binance para obtener el precio actual.")
        return 0
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])
    except Exception as e:
        logging.error(f"Error al obtener el precio actual de {symbol}: {e}")
        return 0

def obtener_señal_trading(symbol):
    """
    Obtiene la señal de trading (comprar, vender o mantener) para un símbolo usando lógica avanzada.
    """
    # Obtén los datos históricos recientes
    historical_data = obtener_datos_historicos(symbol, limit=100)
    if historical_data is None or historical_data.empty:
        return None

    # Calcula los indicadores técnicos
    indicadores_lista = calcular_todos_los_indicadores(historical_data)
    if not indicadores_lista:
        return None

    ultimo_indicador = cast(Dict[str, Any], indicadores_lista[-1])
    # Usa tu lógica avanzada de estrategia
    if _strategy_bool(estrategia_compra(ultimo_indicador)):
        return "comprar"
    elif _strategy_bool(estrategia_venta(ultimo_indicador)):
        return "vender"
    else:
        return None

def guardar_estado(saldo_virtual, cantidad_btc, filename="data/papertrading/estado_papertrading.json"):
    estado = {
        "saldo_virtual": saldo_virtual,
        "cantidad_btc": cantidad_btc
    }
    with open(filename, "w") as f:
        json.dump(estado, f)

def cargar_estado(filename="data/papertrading/estado_papertrading.json"):
    if os.path.exists(filename):
        with open(filename) as f:
            return json.load(f)
    return {"saldo_virtual": 10000.0, "cantidad_btc": 0.0}

if __name__ == "__main__":
    ejecutar_ciclo_paper_trading()
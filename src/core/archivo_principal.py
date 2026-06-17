
from __future__ import annotations
"""
archivo_principal.py
--------------------
Script principal para ejecutar el bot de trading:
- Modo paper trading (simulación continua).
- Modo análisis (una pasada de señales).
Centraliza flujo alto nivel reutilizando utilidades existentes.2
"""

import sys
from pathlib import Path
# Agregar raíz del proyecto al PATH
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
import json
import pandas as pd
from typing import Optional
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__)) + "/.."
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.pipeline.conexion_api import get_historical_data, connect_to_binance
from src.pipeline.carga_datos import cargar_y_combinar_datos
from src.pipeline.validacion_datos import validar_datos
from src.core.gestor_indicadores import calcular_todos_los_indicadores
from src.core.estrategias_bot1 import estrategia_compra, estrategia_venta, registrar_decisiones
from src.core.utilidades import log_operation_json, cargar_parametros_config, ParamConfig, limpiar_ohlcv
from src.core.backtesting import backtesting as motor_backtesting, guardar_resultados_por_par  # type: ignore
from src.core.backtesting import BTConfig

# ML opcional
try:
    from src.caracteristicas_ML import generar_features, train_random_forest, predict_price  # type: ignore
    ML_ENABLED = True
except Exception:
    ML_ENABLED = False

LOG_FILE = "logs/bot.log"

def configurar_logging() -> logging.Logger:
    logger = logging.getLogger("bot_main")
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.propagate = False
    return logger

logger = configurar_logging()
config: ParamConfig = cargar_parametros_config()

def fusionar_datos_historicos(
    symbol: str,
    interval: str,
    limit: int,
    client
) -> pd.DataFrame:
    """Obtiene dataset base (maestro limpio o maestro 15m) y opcionalmente concatena live.
    Prioriza:
      1. Env var PAPER_MASTER_FILE
      2. Si intervalo 15m: historial_trading_maestro_15m.csv
      3. Fallback: historial_trading_maestro_limpio.csv
    Filtra por símbolo si la columna 'symbol' existe.
    """
    env_master = os.environ.get("PAPER_MASTER_FILE")
    maestro_15m = "data/historiales/historial_trading_maestro_15m.csv"
    maestro_default = "data/historiales/historial_trading_maestro_limpio.csv"
    if env_master and os.path.exists(env_master):
        base_path = env_master
    elif interval.lower().startswith("15") and os.path.exists(maestro_15m):
        base_path = maestro_15m
    else:
        base_path = maestro_default

    try:
        df_base = cargar_y_combinar_datos(
            base_path,
            client=None,
            symbol=symbol,
            meses=0
        )
    except Exception as e:
        logger.error("Error cargando maestro %s: %s", base_path, e)
        return pd.DataFrame()

    if df_base.empty:
        logger.warning("Maestro vacío para %s", symbol)
        return df_base
    # Filtrar por símbolo si procede
    if "symbol" in df_base.columns:
        # Algunas construcciones guardan símbolo en mayúsculas; normalizar
        df_base = df_base[df_base["symbol"].str.upper() == symbol.upper()].copy()
    df_base = limpiar_ohlcv(df_base)

    df_live = pd.DataFrame()
    if client is not None:
        try:
            live = get_historical_data(client, symbol=symbol, interval=interval, limit=limit)
            df_live = pd.DataFrame(live)
            if not df_live.empty:
                df_live = limpiar_ohlcv(df_live)
        except Exception as e:
            logger.warning("No se pudo obtener live %s: %s", symbol, e)

    if not df_live.empty:
        df = pd.concat([df_base, df_live], ignore_index=True)
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    else:
        df = df_base.sort_values("timestamp")

    if df.empty:
        logger.warning("Sin datos combinados tras fusión para %s", symbol)
    else:
        logger.info("Datos combinados %s filas (%s -> %s) fuente=%s", len(df), df['timestamp'].min(), df['timestamp'].max(), os.path.basename(base_path))
    return df.reset_index(drop=True)

def validar_y_calcular_indicadores(df: pd.DataFrame) -> tuple[Optional[pd.DataFrame], Optional[dict]]:
    required = ["open", "high", "low", "close", "volume", "timestamp"]
    try:
        df_valid = validar_datos(df, required_fields=required)
    except Exception as e:
        logger.error("Validación falló: %s", e)
        return None, None
    if df_valid is None or df_valid.empty:
        logger.error("DataFrame vacío tras validar.")
        return None, None

    indicadores_lista = calcular_todos_los_indicadores(df_valid)
    if not indicadores_lista:
        logger.warning("No se generaron indicadores.")
        return None, None
    ultima = indicadores_lista[-1]
    if not isinstance(ultima, dict):
        logger.warning("Formato de indicadores inesperado.")
        return None, None
    return df_valid, ultima

def evaluar_estrategias(df_valid: pd.DataFrame, snapshot_ind: dict):
    """
    Evalúa condiciones básicas de compra / venta usando snapshot final.
    Ajusta según firma real de estrategia_compra / estrategia_venta (placeholder).
    """
    try:
        precio = df_valid.iloc[-1]["close"]
        ts = df_valid.iloc[-1].get("timestamp")

        _buy_ret = estrategia_compra(
            indicadores=snapshot_ind,
            rsi_dynamic=config.rsi_dynamic_buy,
            adx_limit=config.ADX_LIMIT,
            min_votes=config.MIN_VOTES_COMPRA,
            atr_min=config.atr_min,
            bb_width_min=config.bb_width_min
        )
        buy, usados_buy = (_buy_ret[0], _buy_ret[1]) if isinstance(_buy_ret, tuple) else (bool(_buy_ret), [])
        _sell_ret = estrategia_venta(
            indicadores=snapshot_ind,
            rsi_dynamic=config.rsi_dynamic_sell,
            adx_limit=config.ADX_LIMIT,
            min_votes=config.MIN_VOTES_VENTA,
            bb_width_min=config.bb_width_min
        )
        sell, usados_sell = (_sell_ret[0], _sell_ret[1]) if isinstance(_sell_ret, tuple) else (bool(_sell_ret), [])

        if buy:
            logger.info("Señal COMPRA @ %.5f", precio)
            # pasar timestamp histórico para que el registro sea reproducible
            registrar_decisiones("compra", precio, timestamp=ts, indicadores=snapshot_ind, modo="aprobado")
            log_operation_json("compra_signal", "INFO", {"precio": precio, "indicadores": snapshot_ind})
        elif sell:
            logger.info("Señal VENTA @ %.5f", precio)
            registrar_decisiones("venta", precio, timestamp=ts, indicadores=snapshot_ind, modo="aprobado")
            log_operation_json("venta_signal", "INFO", {"precio": precio, "indicadores": snapshot_ind})
        else:
            logger.info("Sin señal operativa.")
    except Exception as e:
        logger.error("Error evaluando estrategias: %s", e)

def guardar_nuevos_registros(df_total: pd.DataFrame, symbol: str):
    """
    Persiste únicamente filas más recientes (última barra) como ejemplo simple.
    """
    if df_total.empty:
        return
    try:
        last = df_total.iloc[[-1]]
        path = f"data/historiales/historial_{symbol}_append.csv"
        append = not last.empty and bool(last["timestamp"].iloc[0])
        last.to_csv(path, mode="a" if append else "w", header=not append, index=False)
        logger.info("Snapshot final (%s) guardado en %s", symbol, path)
    except Exception as e:
        logger.warning("No se pudo guardar snapshot incremental: %s", e)

def run_modo_analisis(symbol: str = "WLDUSDT", interval: str = "1m", limit: int = 500):
    client = connect_to_binance()
    if client is None:
        logger.warning("Modo offline (sin API). Continuando solo histórico local.")
    df = fusionar_datos_historicos(symbol, interval, limit, client)
    if df.empty:
        return
    df_valid, snapshot = validar_y_calcular_indicadores(df)
    if df_valid is None or snapshot is None:
        return
    evaluar_estrategias(df_valid, snapshot)
    guardar_nuevos_registros(df, symbol)

def run_paper_trading(symbols: list | None = None, interval: str = "15m", limit: int = 1500):
    """Paper trading reutilizando el motor de backtesting para producir trades reales.
    - Usa últimos 5 días del maestro (según intervalo)
    - Genera carpeta data/papertrading/YYYY-MM-DD/ con subcarpetas por símbolo (igual formato backtesting)
    - Agrega trades.csv global (gross/net pnl idénticos por ahora)
    """
    import datetime
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    base_dir = os.path.join("data", "papertrading", today)
    os.makedirs(base_dir, exist_ok=True)
    if symbols is None:
        symbols = ["BNBUSDT"]

    resumen_global = []
    for symbol in symbols:
        logger.info("[PAPER] Procesando %s", symbol)
        df_full = fusionar_datos_historicos(symbol=symbol, interval=interval, limit=limit, client=None)
        if df_full.empty:
            continue
        # Ventana de 5 días
        try:
            end = pd.to_datetime(df_full['timestamp']).max()
            cutoff_5d = pd.to_datetime(end) - pd.Timedelta(days=90)
            df_cut = df_full.loc[pd.to_datetime(df_full['timestamp']) >= cutoff_5d].reset_index(drop=True)
        except Exception:
            df_cut = df_full.copy()
        if df_cut.empty:
            logger.warning("Sin datos recortados (5d) para %s", symbol)
            continue
        # Ejecutar motor de backtesting (ya incluye nueva lógica SL/TP ATR)
        try:
            res = motor_backtesting(df_cut)
        except Exception as e:
            logger.error("Fallo backtesting simbolo %s: %s", symbol, e)
            continue
        if not res or not isinstance(res, tuple) or len(res) < 2:
            logger.warning("Backtesting sin resultados para %s", symbol)
            continue
        resultados, resumen, *extra = res  # Captura 3+ valores

        # Guardar artefactos estilo backtesting
        try:
            guardar_resultados_por_par(symbol, "5d", resultados, resumen, starting_capital=getattr(config, "starting_capital", 100.0), run_dir=base_dir)
        except Exception as e:
            logger.warning("No se pudieron guardar resultados estandarizados para %s: %s", symbol, e)
        # Construir trades para resumen global rápido
        try:
            # Construir trades desde resultados (simplificado)
            trades_df = pd.DataFrame(resultados) if isinstance(resultados, list) else pd.DataFrame()
            total_trades = len(trades_df)
            pf = 0.0
            if total_trades:
                wins = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
                losses = trades_df[trades_df['pnl'] <= 0]['pnl'].sum()
                pf = (wins / abs(losses)) if losses != 0 else float('inf')
        except Exception:
            total_trades = 0
            pf = 0.0
        resumen_global.append({
            "symbol": symbol,
            "filas": int(len(df_cut)),
            "timestamp_inicio": str(df_cut['timestamp'].iloc[0]),
            "timestamp_fin": str(df_cut['timestamp'].iloc[-1]),
            "total_trades": total_trades,
            "profit_factor": float(pf)
        })

    # Guardar resumen global y parámetros
    try:
        with open(os.path.join(base_dir, "resumen_global.json"), "w", encoding="utf-8") as f:
            json.dump(resumen_global, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("No se pudo guardar resumen_global: %s", e)
    try:
        with open(os.path.join(base_dir, "parametros_usados.json"), "w", encoding="utf-8") as f:
            json.dump(config.__dict__, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("No se pudo guardar parametros_usados: %s", e)
    readme_file = os.path.join(base_dir, "README.txt")
    if not os.path.exists(readme_file):
        with open(readme_file, "w", encoding="utf-8") as f:
            f.write("Paper trading diario con motor backtesting unificado (ATR SL/TP).\n")
    # Agregar trades global
    try:
        import pandas as _pd
        frames = []
        for sym in symbols:
            tfile = os.path.join(base_dir, sym, "trades.csv")
            if os.path.exists(tfile):
                tdf = _pd.read_csv(tfile)
                if 'symbol' not in tdf.columns:
                    tdf['symbol'] = sym
                frames.append(tdf)
        if frames:
            all_trades = _pd.concat(frames, ignore_index=True)
            all_trades.to_csv(os.path.join(base_dir, "trades.csv"), index=False)
            logger.info("Trades global paper (%d filas)", len(all_trades))
        else:
            logger.warning("Sin trades globales (ningún símbolo generó cierres)")
    except Exception as e:
        logger.warning("No se pudo generar trades global: %s", e)

def build_bt_config_from_setup(setup: dict) -> BTConfig:
    return BTConfig(
        allowed_regimes=setup.get("ALLOWED_REGIMES", ["neutral","low_vol","range"]),
        allowed_hours=setup.get("ALLOWED_HOURS"),  # ej. excluir [0,1,2] si aplica
        cooldown_bars=int(setup.get("COOLDOWN_BARS", 30)),
        max_trades_per_day=int(setup.get("MAX_TPD", 6)),
        min_distance_bars=int(setup.get("MIN_DIST", 8)),
        min_bbw_pct=float(setup.get("MIN_BBW", 0.15)),
        min_atr_pct=float(setup.get("MIN_ATR", 0.30)),
    )

def seleccionar_setups_eligibles(df_grid: pd.DataFrame) -> pd.DataFrame:
    # Repite los criterios de gating del grid para evitar promover setups no aptos
    elig = df_grid[
        (df_grid["expectancy_net"] > 0)
        & (df_grid["r_multiple_median_net"] > 0)
        & (df_grid["recovery_ratio"] > -0.5)
        & (df_grid["winrate_rolling20"] > 0.45)
        & (~df_grid["skew_extreme"])
        & (~df_grid["few_trades"])
        & (df_grid["fees_share_pct"] <= 40)
        & (df_grid["trades_per_day"] <= 6)
        & (df_grid["mae_eff_ok"].isin([True, None]))
    ].copy()
    return elig

def main(interactive: bool = True, modo: Optional[str] = None):
    """
    interactive=False permite llamar desde otros scripts sin input().
    modo: 'paper' | 'analisis' | None
    """
    logger.info("Inicio archivo principal (ML=%s)", ML_ENABLED)
    if not interactive and modo is None:
        modo = "analisis"
    if interactive:
        print("=======================================")
        print("      BOT DE TRADING AUTOMÁTICO")
        print("=======================================")
        print("1. Paper Trading (simulación en tiempo real)")
        print("2. Análisis normal (señales únicas)")
        opcion = input("Elige (1/2): ").strip()
        modo = "paper" if opcion == "1" else ("analisis" if opcion == "2" else None)

    if modo == "paper":
        logger.info("Modo PAPER TRADING")
        run_paper_trading()
    elif modo == "analisis":
        logger.info("Modo ANÁLISIS")
        run_modo_analisis()
    else:
        logger.error("Modo no válido (%s)", modo)

if __name__ == "__main__":
    main()
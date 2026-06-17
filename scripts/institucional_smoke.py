import os
import sys
from datetime import datetime
import pandas as pd

# Ensure project root in path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.config_loader import get_institucional_config, freeze_params
from src.core.backtesting import backtesting, guardar_resultados_por_par, cargar_y_combinar_datos, limpiar_ohlcv, btconfig_from_simple


def main():
    base = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    cfg = get_institucional_config()

    # Pick first included symbol
    symbols = [s for s in cfg.portfolio_include if cfg.symbols.get(s) and cfg.symbols[s].enabled]
    if not symbols:
        raise SystemExit("No enabled symbols in portfolio.include")
    symbol = symbols[0]

    # Build BTConfig from merged filters/execution
    sc = cfg.symbols[symbol]
    bt_cfg = btconfig_from_simple(filters=sc.filters, execution=sc.execution)

    # Create run dir and freeze params
    run_dir = os.path.join(base, "data", "backtesting", "runs", datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    frozen = freeze_params(run_dir, cfg, extra={"symbols": [symbol], "note": "institucional smoke 30d"})
    print("Params frozen at:", frozen)

    # Load master and slice last 30d for the smoke
    master = os.path.join(base, "data", "historiales", "historial_trading_maestro_15m.csv")
    df_full = cargar_y_combinar_datos(master, client=None, symbol=symbol, meses=0)
    if df_full is None or df_full.empty:
        raise SystemExit(f"No data for {symbol}")
    df_full["timestamp"] = pd.to_datetime(df_full["timestamp"], utc=True, errors="coerce")
    end = df_full["timestamp"].max()
    cutoff = end - pd.Timedelta(days=30)
    df = df_full.loc[df_full["timestamp"] >= cutoff].reset_index(drop=True)
    df = limpiar_ohlcv(df)

    # Run backtesting
    resultados, resumen, trades_enriched = backtesting(df, bt_cfg, params={})

    # Save outputs under run dir
    out = guardar_resultados_por_par(symbol, "30d", resultados, resumen, run_dir=run_dir, trades_enriched=trades_enriched.to_dict("records") if hasattr(trades_enriched, "to_dict") else None)
    print("Smoke done:", symbol, "events=", len(resultados), "out_dir=", os.path.dirname(out.get("resultados_file", "")))


if __name__ == "__main__":
    main()

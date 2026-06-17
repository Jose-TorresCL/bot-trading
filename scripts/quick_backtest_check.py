import os
from datetime import datetime
import pandas as pd

from src.core.backtesting import backtesting, guardar_resultados_por_par, cargar_y_combinar_datos, limpiar_ohlcv
from src.core import config_estrategias as config


def main():
    symbols = ["BTCUSDT", "ETHUSDT"]
    master_rel = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src", "data", "historiales", "historial_trading_limpio.csv"))

    for symbol in symbols:
        try:
            df_full = cargar_y_combinar_datos(master_rel, client=None, symbol=symbol, meses=0)
        except Exception as e:
            print("Error loading data for", symbol, e)
            continue
        if df_full is None or df_full.empty:
            print("No data for", symbol)
            continue
        end = pd.to_datetime(df_full["timestamp"], utc=True).max()
        cutoff = end - pd.Timedelta(days=30)
        df = df_full.loc[pd.to_datetime(df_full["timestamp"], utc=True) >= cutoff].reset_index(drop=True)
        df = limpiar_ohlcv(df)
        resultados, resumen = backtesting(df, config_obj=config, writer=None)
        out = guardar_resultados_por_par(symbol, "30d", resultados, resumen, starting_capital=getattr(config, "starting_capital", 100.0))
        print(symbol, "->", resumen.get("total_compras"), resumen.get("total_ventas"), out.get("resultados_file"))

    today = datetime.now().strftime("%Y-%m-%d")
    day_dir = os.path.join("data", "backtesting", today)
    print("Day dir:", day_dir)
    print("Summary exists:", os.path.exists(os.path.join(day_dir, "summary.csv")))


if __name__ == "__main__":
    main()

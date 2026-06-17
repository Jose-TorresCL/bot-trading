import pandas as pd, os
p = "src/data/historiales/historial_trading_limpio.csv"
if os.path.exists(p):
    df = pd.read_csv(p, parse_dates=["timestamp"], low_memory=False)
    print("Símbolos:", df['symbol'].unique())
    print(df.groupby('symbol').timestamp.agg(['min','max','count']))
else:
    print("No existe master en", p)
import pandas as pd
df = pd.read_csv("historial_trading_limpio.csv")
print(df["symbol"].value_counts())
print(df["timestamp"].min(), df["timestamp"].max())
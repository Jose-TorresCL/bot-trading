import pandas as pd

columnas_objetivo = ["timestamp", "open", "high", "low", "close", "volume", "price"]
df = pd.read_csv("historial_trading_acum.csv")
for col in columnas_objetivo:
    if col not in df.columns:
        df[col] = None
df = df[columnas_objetivo]
# Si quieres igualar close y price:
df["close"] = df["price"]
df.to_csv("historial_trading_acum.csv", index=False)
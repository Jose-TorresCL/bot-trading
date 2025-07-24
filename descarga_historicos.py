import pandas as pd
from conexion_api import get_historical_data, connect_to_binance

symbols = ["WLDUSDT", "BTCUSDT", "ETHUSDT", "BNBUSDT"]
interval = "1m"
limit = 3000  # Ajusta según lo que permita la API

client = connect_to_binance()
for symbol in symbols:
    data = get_historical_data(client, symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(data)
    df["symbol"] = symbol
    df.to_csv(f"historial_{symbol}.csv", index=False)
    print(f"✅ Datos guardados en historial_{symbol}.csv")

# Fusiona los archivos en uno solo y convierte timestamp a ms
dfs = []
for f in [f"historial_{s}.csv" for s in symbols]:
    df = pd.read_csv(f)
    if df["timestamp"].dtype == "object":
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["timestamp"] = df["timestamp"].astype("int64") // 10**6
    dfs.append(df)
df_final = pd.concat(dfs, ignore_index=True)
df_final.to_csv("historial_trading_limpio.csv", index=False)
print("✅ Archivo fusionado y timestamp convertido a milisegundos.")
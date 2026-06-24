from dotenv import load_dotenv
import os, time
import pandas as pd
load_dotenv('data/config.env')
from binance.client import Client
from src.pipeline.conexion_api import get_historical_data
from src.core.gestor_indicadores import calcular_todos_los_indicadores
from src.policies.gating import should_trade
from src.policies.regime import classify_regime

client = Client(os.getenv('API_KEY'), os.getenv('API_SECRET'))
server_time = client.get_server_time()['serverTime']
client.timestamp_offset = server_time - int(time.time() * 1000)

df = get_historical_data('BTCUSDT', '1h', limit=500, client=client)
result = calcular_todos_los_indicadores(df)
df_ind = pd.DataFrame(result)

last = df_ind.iloc[-1].to_dict()
regime = classify_regime(last)
decision = should_trade(last)

print('votes:', last['votes'])
print('RSI:', round(last['RSI'], 2))
print('ADX:', round(last['ADX'], 2))
print('regime:', regime)
print('should_trade:', decision)

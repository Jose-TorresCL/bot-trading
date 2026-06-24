from dotenv import load_dotenv
import os, time
import pandas as pd
load_dotenv('data/config.env')
from binance.client import Client
from src.pipeline.conexion_api import get_historical_data
from src.core.gestor_indicadores import calcular_todos_los_indicadores

client = Client(os.getenv('API_KEY'), os.getenv('API_SECRET'))
server_time = client.get_server_time()['serverTime']
client.timestamp_offset = server_time - int(time.time() * 1000)

df = get_historical_data('BTCUSDT', '1h', limit=200, client=client)
result = calcular_todos_los_indicadores(df)
df_ind = pd.DataFrame(result)
print(df_ind.columns.tolist())
print(df_ind.tail(3))

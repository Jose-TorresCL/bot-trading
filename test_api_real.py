from dotenv import load_dotenv
import os, time
import pandas as pd
load_dotenv('data/config.env')
from binance.client import Client
from src.pipeline.conexion_api import get_historical_data

client = Client(os.getenv('API_KEY'), os.getenv('API_SECRET'))
server_time = client.get_server_time()['serverTime']
client.timestamp_offset = server_time - int(time.time() * 1000)

df = get_historical_data('BTCUSDT', '1h', limit=100, client=client)
print(type(df), df.shape)
print(df[['close','open','high','low']].tail(3))

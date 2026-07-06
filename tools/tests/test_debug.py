import sys, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

from src.pipeline.conexion_api import get_historical_data, connect_to_binance
from src.core.ciclo_real import _to_dataframe
from src.core.gestor_indicadores import calcular_todos_los_indicadores
from src.core.estrategias_bot1 import estrategia_compra, estrategia_venta
from typing import cast, Dict, Any

client = connect_to_binance()
data = get_historical_data(symbol='BTCUSDT', interval='1m', limit=100, client=client)
df = _to_dataframe(data)
df = df.dropna(subset=['open','high','low','close']).sort_values('timestamp').reset_index(drop=True)

inds = calcular_todos_los_indicadores(df)
ind = cast(Dict[str, Any], inds[-1])

ok, used, dbg = estrategia_compra(ind, debug=True)
print(f'BUY: {ok}  |  used={used}')
print(f'  RSI={dbg["RSI"]:.1f}  (thr < {dbg["thr"]["rsi_dynamic"]})')
print(f'  ADX={dbg["ADX"]:.1f}  (thr > {dbg["thr"]["adx_limit"]})')

ok2, used2, dbg2 = estrategia_venta(ind, debug=True)
print(f'SELL: {ok2}  |  used={used2}')

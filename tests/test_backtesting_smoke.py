import pandas as pd

from src.core import backtesting as bt


def _make_prices(rows: int = 64) -> pd.DataFrame:
    base = pd.Timestamp("2024-01-01T00:00:00Z")
    datos = []
    for i in range(rows):
        precio = 100 + i * 0.5
        ts = base + pd.Timedelta(minutes=15 * i)
        datos.append(
            {
                "timestamp": ts,
                "open": precio,
                "high": precio + 1,
                "low": precio - 1,
                "close": precio + 0.2,
                "volume": 10 + i,
                "symbol": "BTCUSDT",
            }
        )
    return pd.DataFrame(datos)


def test_backtesting_smoke(monkeypatch):
    df = _make_prices()

    # Forzar uso de indicadores de respaldo (sin dependencias externas)
    monkeypatch.setattr(bt, "calcular_todos_los_indicadores", None, raising=False)

    def precios_timestamp(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _stub_simulate(prices, indicadores, cfg):
        resultado = {
            "tipo": "compra",
            "precio": float(prices.iloc[0]["close"]),
            "indice": 0,
            "timestamp": precios_timestamp(prices.iloc[0]["timestamp"]),
            "symbol": "BTCUSDT",
            "ganancia": 5.0,
        }
        trades_df = pd.DataFrame(
            [
                {
                    "entry_time": precios_timestamp(prices.iloc[0]["timestamp"]),
                    "exit_time": precios_timestamp(prices.iloc[1]["timestamp"]),
                    "net_pnl": 5.0,
                    "pnl": 5.0,
                    "symbol": "BTCUSDT",
                }
            ]
        )
        return [resultado], trades_df

    monkeypatch.setattr(bt, "_simulate_trades", _stub_simulate)

    resultados, resumen, trades = bt.backtesting(df, cfg=bt.BTConfig())

    assert resultados and isinstance(resultados, list)
    assert resumen["trades"] == 1
    assert resumen["profit_factor"] > 0
    assert trades and trades[0]["symbol"] == "BTCUSDT"

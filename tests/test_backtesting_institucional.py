import math
from datetime import datetime

import pandas as pd

from src.core.backtesting import BTConfig, _simulate_trades


def _build_base_frame(prices):
    df = pd.DataFrame(prices)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["volume"] = df.get("volume", 1.0)
    df["symbol"] = df.get("symbol", "BTCUSDT")
    indicators = df.copy()
    default_cols = {
        "RSI": 30,
        "ADX": 30,
        "ATR_pct": 0.5,
        "BBW_pct": 0.5,
        "ATR": 10.0,
        "hist": 1.0,
        "market_regime": "trend",
    }
    for col, val in default_cols.items():
        if col not in indicators:
            indicators[col] = val
    return df[["timestamp", "open", "high", "low", "close", "volume", "symbol"]], indicators


def test_backtesting_tp_sl_regimen():
    base_ts = pd.date_range(datetime(2025, 1, 1), periods=3, freq="15min", tz="UTC")
    price_rows = [
        {"timestamp": base_ts[0], "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0},
        {"timestamp": base_ts[1], "open": 101.0, "high": 131.0, "low": 100.5, "close": 125.0},
        {"timestamp": base_ts[2], "open": 125.0, "high": 129.0, "low": 123.0, "close": 128.0},
    ]
    prices_df, indicators_df = _build_base_frame(price_rows)
    cfg = BTConfig(
        allowed_hours=list(range(24)),
        min_atr_pct=0.1,
        min_bbw_pct=0.1,
        cooldown_bars=0,
        max_trades_per_day=10,
        fee_bps=0.0,
        slippage_bps=0.0,
        tick_size=0.1,
        max_duracion=5,
        trailing_stop=False,
        tp_sl_by_regime={"trend": {"sl_mult": 2.0, "tp_mult": 3.0}},
        sl_mult=1.0,
        tp_mult=1.0,
    )

    resultados, trades_df = _simulate_trades(prices_df, indicators_df, cfg)

    assert len(trades_df) == 1
    trade = trades_df.iloc[0]
    assert trade["take_price"] == 130.0
    assert trade["stop_price"] == 80.0
    assert trade["exit_reason"] == "take_profit_atr"
    assert math.isinf(trade["mfe_mae_ratio"]) or trade["mfe_mae_ratio"] >= 1.0
    assert any(r.get("signal") == "take_profit_atr" for r in resultados)


def test_backtesting_guardrails():
    base_ts = pd.date_range(datetime(2025, 1, 1), periods=4, freq="15min", tz="UTC")
    price_rows = [
        {"timestamp": base_ts[0], "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.0},
        {"timestamp": base_ts[1], "open": 100.5, "high": 102.0, "low": 97.0, "close": 101.0},
        {"timestamp": base_ts[2], "open": 101.0, "high": 102.5, "low": 96.0, "close": 99.5},
        {"timestamp": base_ts[3], "open": 99.5, "high": 100.0, "low": 95.5, "close": 99.0},
    ]
    prices_df, indicators_df = _build_base_frame(price_rows)
    cfg = BTConfig(
        allowed_hours=list(range(24)),
        min_atr_pct=0.1,
        min_bbw_pct=0.1,
        cooldown_bars=0,
        max_trades_per_day=10,
        fee_bps=0.0,
        slippage_bps=0.0,
        tick_size=0.1,
        max_duracion=3,
        trailing_stop=False,
        tp_sl_by_regime={"trend": {"sl_mult": 1.0, "tp_mult": 1.5}},
        sl_mult=1.0,
        tp_mult=1.0,
        min_mfe_mae_ratio=1.5,
    )

    resultados, trades_df = _simulate_trades(prices_df, indicators_df, cfg)

    assert trades_df.empty
    guardrail_events = [r for r in resultados if r.get("tipo") == "guardrail_skip"]
    assert guardrail_events, "Se esperaba un evento de guardrail"
    assert guardrail_events[0]["signal"] == "mfe_mae_ratio"
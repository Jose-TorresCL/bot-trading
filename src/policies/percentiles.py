from __future__ import annotations
import pandas as pd


def _last_percentile(s: pd.Series) -> float:
    # percent rank of the last observation within the rolling window
    r = s.rank(pct=True, method="average")
    return float(r.iloc[-1]) if len(r) else float("nan")


def add_atr_bbw_pct(df: pd.DataFrame, atr_col: str = "ATR", bbw_col: str = "BB_WIDTH", window: int = 200) -> pd.DataFrame:
    out = df.copy()
    if atr_col in out:
        out["ATR_pct"] = out[atr_col].rolling(window, min_periods=max(5, window // 5)).apply(_last_percentile, raw=False)
    if bbw_col in out:
        out["BBW_pct"] = out[bbw_col].rolling(window, min_periods=max(5, window // 5)).apply(_last_percentile, raw=False)
    return out

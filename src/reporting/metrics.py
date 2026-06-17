from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Any, Dict, Tuple


# ---------------------
# Helpers
# ---------------------

def _ensure_df(trades_obj: Any) -> pd.DataFrame:
    if trades_obj is None:
        return pd.DataFrame()
    if isinstance(trades_obj, pd.DataFrame):
        df = trades_obj.copy()
    elif isinstance(trades_obj, list):
        df = pd.DataFrame(trades_obj)
    else:
        try:
            df = pd.DataFrame(trades_obj)
        except Exception:
            return pd.DataFrame()

    # Normalize time column if present
    tcol = "exit_time" if "exit_time" in df.columns else ("timestamp" if "timestamp" in df.columns else None)
    if tcol:
        df[tcol] = pd.to_datetime(df[tcol], errors="coerce")

    # net_pnl fallback
    if "net_pnl" not in df.columns:
        for alias in ("ganancia", "pnl", "profit"):
            if alias in df.columns:
                df["net_pnl"] = pd.to_numeric(df[alias], errors="coerce")
                break
        else:
            df["net_pnl"] = np.nan

    # r_multiple_net fallback
    if "r_multiple_net" not in df.columns and "r_multiple" in df.columns:
        df["r_multiple_net"] = pd.to_numeric(df["r_multiple"], errors="coerce")

    return df


def _as_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
        return s if isinstance(s, pd.Series) else pd.Series(s, index=df.index)
    return pd.Series(index=df.index, dtype=float)


def _pnl_col(df: pd.DataFrame) -> str:
    for c in ("net_pnl", "pnl_net", "pnl"):
        if c in df.columns:
            return c
    return "net_pnl"


# ---------------------
# Core metrics
# ---------------------

def profit_factor(df: pd.DataFrame) -> float:
    col = _pnl_col(df)
    gains = df.loc[df[col] > 0, col].sum()
    losses = -df.loc[df[col] < 0, col].sum()
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def expectancy(df: pd.DataFrame) -> float:
    col = _pnl_col(df)
    return float(df[col].mean())


def max_drawdown_amount(series: pd.Series) -> float:
    cum = series.cumsum()
    roll_max = cum.cummax()
    dd = cum - roll_max
    return float(dd.min())  # negativo


def max_drawdown_pct(series: pd.Series, start_equity: float = 100.0) -> float:
    dd = max_drawdown_amount(series)
    return float(dd / start_equity)


def winrate_rolling(series: pd.Series, window: int = 20) -> float:
    if series.empty:
        return np.nan
    wins = (series > 0).astype(float)
    roll = wins.rolling(window, min_periods=max(5, window // 2)).mean() * 100
    return float(roll.median())


def mae_eff_ok(df: pd.DataFrame, threshold: float = 0.8) -> bool:
    if "mae" not in df.columns or "mfe" not in df.columns:
        return False
    mae = pd.to_numeric(df["mae"], errors="coerce").abs()
    mfe = pd.to_numeric(df["mfe"], errors="coerce").abs().replace(0, np.nan)
    ratio = (mae / mfe).dropna()
    if ratio.empty:
        return False
    return float(ratio.median()) < threshold


def fragility_flag(trades: pd.DataFrame) -> bool:
    if trades.empty or "symbol" not in trades.columns:
        return False
    base = _as_series(trades, "net_pnl").fillna(0.0)
    base_pf = profit_factor(base)
    base_dd = max_drawdown(base)
    for sym, _g in trades.groupby("symbol"):
        rest = trades.loc[trades["symbol"] != sym]
        s = _as_series(rest, "net_pnl").fillna(0.0)
        if profit_factor(s) > base_pf or max_drawdown(s) < base_dd:
            return True
    return False


def pf_window_degradation(series: pd.Series, window: int = 20) -> Tuple[float, float]:
    if series.empty:
        return (np.nan, np.nan)
    pfs = []
    for i in range(0, len(series), window):
        blk = series.iloc[i:i+window]
        if not blk.empty:
            pfs.append(profit_factor(blk))
    if not pfs:
        return (np.nan, np.nan)
    ratios = []
    for i, pf in enumerate(pfs):
        prev = pfs[:i]
        if not prev:
            ratios.append(np.nan)
        else:
            med_prev = float(np.median(prev))
            ratios.append(pf / med_prev if med_prev != 0 else np.nan)
    ratios = pd.Series(ratios)
    return (float(ratios.min(skipna=True)), float(ratios.dropna().iloc[-1]) if ratios.dropna().size else np.nan)


def skew_r_multiple(df: pd.DataFrame) -> float:
    if "r_multiple_net" not in df.columns:
        return np.nan
    vals = pd.to_numeric(df["r_multiple_net"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if vals.empty:
        return np.nan
    sk = vals.skew()
    return float(sk) if isinstance(sk, (int, float, np.floating)) else np.nan


# ---------------------
# Public API
# ---------------------

def compute_advanced_metrics(trades_df: pd.DataFrame) -> Dict[str, Any]:
    df = trades_df.copy()
    # Temporal order
    time_col = "exit_time" if "exit_time" in df.columns else ("timestamp" if "timestamp" in df.columns else None)
    if time_col:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.sort_values(time_col).reset_index(drop=True)

    pnl = _as_series(df, "net_pnl").fillna(0.0)
    exp = float(pnl.mean()) if len(pnl) else np.nan
    pf = profit_factor(pnl)
    mdd = max_drawdown(pnl)
    rec = recovery_ratio(pnl)
    wins_roll = winrate_rolling(pnl, window=20)

    mae_ok = mae_eff_ok(df)
    frag = fragility_flag(df)
    min_ratio, last_ratio = pf_window_degradation(pnl, window=20)
    skew_val = skew_r_multiple(df)
    r_median = float(pd.to_numeric(df.get("r_multiple_net", pd.Series(dtype=float)), errors="coerce").median()) if "r_multiple_net" in df.columns else np.nan

    gross = _as_series(df, "gross_pnl").abs().fillna(0.0)
    fees  = _as_series(df, "commission_paid").fillna(0.0)
    slip  = _as_series(df, "slippage_cost").fillna(0.0)
    denom = float(gross.sum())
    fees_share_pct = float(((fees.sum() + slip.sum()) / denom) * 100.0) if denom > 0 else np.nan

    trades_per_day = 0.0
    if time_col:
        per_day = df.groupby(df[time_col].dt.date).size()
        trades_per_day = float(per_day.mean()) if len(per_day) else 0.0

    return {
        "trades": int(len(df)),
        "pf_net": float(pf),
        "expectancy": exp,
        "max_dd": float(mdd),
        "recovery_ratio": float(rec),
        "winrate_rolling": float(wins_roll),
        "mae_eff_ok": bool(mae_ok),
        "fragility_flag": bool(frag),
        "pf_ratio_min": float(min_ratio),
        "pf_ratio_last": float(last_ratio),
        "skew_r_multiple": float(skew_val) if not np.isnan(skew_val) else np.nan,
        "r_multiple_median_net": r_median,
        "fees_share_pct": fees_share_pct,
        "trades_per_day": trades_per_day,
    }


def compute_core_metrics(df: pd.DataFrame, start_equity: float = 100.0) -> Dict[str, Any]:
    col = _pnl_col(df)
    pf = profit_factor(df)
    expct = expectancy(df)
    dd_amt = max_drawdown_amount(df[col])
    dd_pct = max_drawdown_pct(df[col], start_equity=start_equity)
    tpd = trades_per_day(df)
    fees_pct = fees_share_pct(df)
    winrate = float((df[col] > 0).mean()) if len(df) else 0.0
    return {
        "pf_net": pf,
        "expectancy": expct,
        "max_dd": dd_amt,           # negativo (monto)
        "max_dd_pct": dd_pct,       # negativo (proporción de equity)
        "trades_per_day": tpd,
        "fees_share_pct": fees_pct,
        "winrate": winrate,
        "n_trades": int(len(df)),
    }

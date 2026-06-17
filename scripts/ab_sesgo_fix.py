import os
import sys
import argparse
from typing import Dict, Any, List, Tuple, Set
import pandas as pd
import numpy as np

# Ensure project root in path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.backtesting import BTConfig, backtesting
from src.core.gestor_indicadores import calcular_todos_los_indicadores
from src.reporting.metrics import compute_advanced_metrics
from src.core import config_estrategias as base_cfg
import logging

# Optional per-regime overrides (set in main via CLI)
REGIME_VOTES_OVERRIDE: Dict[str, int] = {}

# Institucional config + gating (optional) via module imports to keep typing simple
try:
    import src.config_loader as instit_mod  # type: ignore
except Exception:
    instit_mod = None  # type: ignore
try:
    import src.policies.gating as gating_mod  # type: ignore
    import src.policies.regime as regime_mod  # type: ignore
    import src.policies.percentiles as pct_mod  # type: ignore
    import src.policies.votes as votes_mod  # type: ignore
except Exception:
    gating_mod = None  # type: ignore
    regime_mod = None  # type: ignore
    pct_mod = None  # type: ignore
    votes_mod = None  # type: ignore


def ensure_pct_cols(df_ind: pd.DataFrame, window: int = 200) -> pd.DataFrame:
    if pct_mod is not None:
        return pct_mod.add_atr_bbw_percentiles(df_ind, window=window)
    # fallback if module missing
    df = df_ind.copy()
    def _pct_rank_last(x):
        s = pd.Series(x).dropna()
        if s.empty:
            return np.nan
        return float(s.rank(pct=True).iloc[-1])
    if "ATR" in df.columns and "ATR_pct" not in df.columns:
        df["ATR_pct"] = df["ATR"].rolling(window, min_periods=10).apply(_pct_rank_last, raw=False)
    if "BB_Width" in df.columns and "BBW_pct" not in df.columns:
        df["BBW_pct"] = df["BB_Width"].rolling(window, min_periods=10).apply(_pct_rank_last, raw=False)
    return df


def classify_regime(row: pd.Series) -> str:
    if regime_mod is not None:
        return regime_mod.classify_regime(row)
    # fallback
    try:
        adx = float(row.get("ADX", np.nan)) if row.get("ADX") is not None else np.nan
        atrp = float(row.get("ATR_pct", 0.5) or 0.5)
        bbwp = float(row.get("BBW_pct", 0.5) or 0.5)
        if adx >= 25 and bbwp >= 0.5:
            return "trend"
        if adx < 18 and bbwp < 0.4:
            return "range"
        if atrp > 0.7:
            return "high_vol"
        if atrp < 0.3:
            return "low_vol"
        return "neutral"
    except Exception:
        return "neutral"


def compute_votes(row: pd.Series, side: str, rsi_buy: float, rsi_sell: float, adx_limit: float) -> int:
    if votes_mod is not None:
        return votes_mod.compute_votes(row, side=side, rsi_buy=rsi_buy, rsi_sell=rsi_sell, adx_limit=adx_limit)
    # fallback
    v = 0
    rsi = row.get("RSI")
    adx = row.get("ADX")
    atrp = row.get("ATR_pct", 0.5)
    bbwp = row.get("BBW_pct", 0.5)
    macd_h = row.get("hist")
    try:
        if side == "long":
            if rsi is not None and rsi < rsi_buy:
                v += 1
        else:  # short
            if rsi is not None and rsi > rsi_sell:
                v += 1
        if adx is not None and adx >= adx_limit:
            v += 1
        if 0.3 <= (atrp if atrp is not None else 0.5) <= 0.85:
            v += 1
        if macd_h is not None:
            if side == "long" and macd_h > 0:
                v += 1
            if side == "short" and macd_h < 0:
                v += 1
        if bbwp is not None and bbwp < 0.45:
            v += 1
    except Exception:
        pass
    return v


def per_regime_thresholds(regime: str) -> Tuple[int, int]:
    # Returns (ADX_LIMIT, MIN_VOTES) for regime
    if regime == "trend":
        # stricter trend
        adx, votes = (21, 3)
        v_ovr = REGIME_VOTES_OVERRIDE.get("trend")
        return (adx, v_ovr if v_ovr is not None else votes)
    if regime == "neutral":
        # neutral often noisy: require more votes (default 4)
        adx, votes = (17, 4)
        v_ovr = REGIME_VOTES_OVERRIDE.get("neutral")
        return (adx, v_ovr if v_ovr is not None else votes)
    if regime == "range":
        # still permissive but avoid very weak setups (default 3)
        adx, votes = (17, 3)
        v_ovr = REGIME_VOTES_OVERRIDE.get("range")
        return (adx, v_ovr if v_ovr is not None else votes)
    if regime == "low_vol":
        # require both later but lower ADX
        adx, votes = (18, 2)
        v_ovr = REGIME_VOTES_OVERRIDE.get("low_vol")
        return (adx, v_ovr if v_ovr is not None else votes)
    if regime == "high_vol":
        # require both later but lower ADX than baseline
        adx, votes = (18, 2)
        v_ovr = REGIME_VOTES_OVERRIDE.get("high_vol")
        return (adx, v_ovr if v_ovr is not None else votes)
    # Keep baseline for others
    adx, votes = (base_cfg.ADX_LIMIT, base_cfg.MIN_VOTES_COMPRA)
    v_ovr = REGIME_VOTES_OVERRIDE.get(regime)
    return (adx, v_ovr if v_ovr is not None else votes)


def admission_mode_for_regime(regime: str) -> str:
    """Return 'both' or 'any' depending on regime.
    trend: both
    neutral: both (reduce noise)
    range: any (mean-reversion leniency)
    low_vol, high_vol: both
    """
    if regime == "range":
        return "any"
    return "both"


def load_master(master_path: str) -> pd.DataFrame:
    df = pd.read_csv(master_path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df


def slice_months(df: pd.DataFrame, months: int | None) -> pd.DataFrame:
    if not months or months <= 0:
        return df
    if "timestamp" not in df.columns:
        return df
    end = pd.to_datetime(df["timestamp"].max())
    cutoff = end - pd.DateOffset(months=months)
    return df.loc[df["timestamp"] >= cutoff].copy()


def build_indicators(df_sym: pd.DataFrame) -> pd.DataFrame:
    ind_list = calcular_todos_los_indicadores(df_sym, export_snapshot=False)
    di = pd.DataFrame(ind_list)
    di = ensure_pct_cols(di)
    # Align timestamps by position, not by index labels (avoid NaT due to misaligned indices)
    try:
        ts_series = pd.to_datetime(df_sym["timestamp"].reset_index(drop=True), utc=True, errors="coerce")
        if len(ts_series) == len(di):
            di["timestamp"] = ts_series
        else:
            # fallback: broadcast using numpy values up to min length
            n = min(len(ts_series), len(di))
            di = di.iloc[:n].reset_index(drop=True)
            di["timestamp"] = ts_series.iloc[:n].reset_index(drop=True)
    except Exception:
        di["timestamp"] = pd.NaT
    di["hour"] = di["timestamp"].dt.hour.fillna(0).astype(int)
    di["market_regime"] = di.apply(classify_regime, axis=1)
    return di


def is_baseline_blocked(
    row: pd.Series,
    side: str,
    rsi_buy: int,
    rsi_sell: int,
    adx_limit: int,
    min_votes_long: int,
    min_votes_short: int,
    min_atr_pct: float = 0.30,
    min_bbw_pct: float = 0.15,
    rsi_tolerance: float = 0.0,
) -> bool:
    rsi = row.get("RSI")
    adx = row.get("ADX")
    atrp = row.get("ATR_pct")
    bbwp = row.get("BBW_pct")
    if rsi is None or np.isnan(rsi):
        return False
    # Baseline eligibility per side (RSI gate) with optional tolerance
    if side == "long" and not (rsi < (rsi_buy + rsi_tolerance)):
        return False
    if side == "short" and not (rsi > (rsi_sell - rsi_tolerance)):
        return False
    if atrp is None or np.isnan(atrp) or atrp < min_atr_pct:
        return False
    if bbwp is None or np.isnan(bbwp) or bbwp < min_bbw_pct:
        return False
    votes = compute_votes(row, side=side, rsi_buy=rsi_buy, rsi_sell=rsi_sell, adx_limit=adx_limit)
    min_votes = min_votes_long if side == "long" else min_votes_short
    adx_ok = (adx is not None and not np.isnan(adx) and adx >= adx_limit)
    votes_ok = (votes >= min_votes)
    # Considered previously blocked if ADX or votes failed
    return (not adx_ok) or (not votes_ok)


def run_engine_relaxed(df_sym: pd.DataFrame) -> pd.DataFrame:
    # Relaxed global thresholds (we'll post-filter by régimen y bloqueados)
    # Usar una configuración operativa permisiva para no perder operaciones por cooldown/tope diario
    cfg = BTConfig(
        allowed_regimes=None,
        allowed_hours=None,
        cooldown_bars=0,
        max_trades_per_day=9999,
        min_bbw_pct=0.0,
        min_atr_pct=0.0,
    )
    params = {
        "RSI_BUY": getattr(base_cfg, "RSI_LIMIT_COMPRA", 40),
        "RSI_SELL": getattr(base_cfg, "RSI_LIMIT_VENTA", 60),
        "ADX_LIMIT": 17,
        "MIN_VOTES": 2,
        "SL_MULT": getattr(base_cfg, "SL_MULT", 1.5),
        "TP_MULT": getattr(base_cfg, "TP_MULT", 3.0),
        "ATR_MULT": 1.0,
    }
    trades, resumen, trades_enriched = backtesting(df_sym, cfg, params)
    # trades_enriched is preferred if available
    if isinstance(trades_enriched, pd.DataFrame) and not trades_enriched.empty:
        return trades_enriched
    return pd.DataFrame(trades or [])


def filter_trades_prev_blocked_relaxed(
    trades_df: pd.DataFrame,
    di: pd.DataFrame,
    rsi_buy: int,
    rsi_sell: int,
    baseline_adx: int,
    baseline_votes_long: int,
    baseline_votes_short: int,
    bar_tolerance: int = 0,
    rsi_tolerance: float = 0.0,
    admission_mode: str = "conditional",
    min_atr_pct: float = 0.20,
    min_bbw_pct: float = 0.12,
    strict_proximity_bars: int = 2,
    exclude_hours: List[int] | None = None,
    gating_thresholds: Any | None = None,
    symbol: str | None = None,
    log_candidates: bool = False,
) -> Tuple[pd.DataFrame, int, int, Dict[str, float]]:
    """Match relaxed engine trades to previously-blocked indicator bars within ±bar_tolerance.

    Strategy (signals-first):
    - Iterate over indicator rows that meet baseline RSI gate and were blocked by ADX/VOTES.
    - For each such bar, look for relaxed trades with entry_time within the corresponding
      time window [t-±bar_tolerance, t+±bar_tolerance].
    - Evaluate quality (ATR_pct/BBW_pct) and per-regime admission on the indicator row.
    - Keep the nearest trade (by bars distance) if within strict_proximity_bars.
    """
    if trades_df is None or trades_df.empty or di is None or di.empty:
        return pd.DataFrame(columns=(trades_df.columns if isinstance(trades_df, pd.DataFrame) else [])), 0, 0, {"unique_regimes": 0, "top_regime_share": np.nan}

    # Normalize times
    df_tr = trades_df.copy()
    time_col = "entry_time" if "entry_time" in df_tr.columns else ("timestamp" if "timestamp" in df_tr.columns else None)
    if time_col is None:
        return pd.DataFrame(columns=df_tr.columns), 0, 0, {"unique_regimes": 0, "top_regime_share": np.nan}
    df_tr[time_col] = pd.to_datetime(df_tr[time_col], utc=True, errors="coerce")
    # infer side
    if "side" in df_tr.columns:
        df_tr["_side"] = df_tr["side"].map(lambda s: "long" if str(s).lower() == "long" else ("short" if str(s).lower() == "short" else None))
    elif "tipo" in df_tr.columns:
        df_tr["_side"] = df_tr["tipo"].map(lambda s: "long" if str(s).lower() == "compra" else ("short" if str(s).lower() == "venta" else None))
    else:
        df_tr["_side"] = None

    di_idx = di.set_index("timestamp").sort_index()
    di_times = di_idx.index
    if len(di_times) == 0:
        return pd.DataFrame(columns=df_tr.columns), 0, 0, {"unique_regimes": 0, "top_regime_share": np.nan}

    # Fast access structures
    tr_times = pd.to_datetime(df_tr[time_col], utc=True, errors="coerce")
    valid_tr_mask = ~tr_times.isna()
    df_tr = df_tr.loc[valid_tr_mask].reset_index(drop=True)
    tr_times = pd.to_datetime(df_tr[time_col], utc=True)

    # Pre-sort trades by time for efficient slicing
    # Use integer nanoseconds for robust sorting irrespective of timezone dtype
    order = np.argsort(tr_times.astype('int64').to_numpy())
    df_tr = df_tr.iloc[order].reset_index(drop=True)
    tr_times = tr_times.iloc[order].reset_index(drop=True)

    # Helper to slice trades by time range
    def trades_in_window(t_start: pd.Timestamp, t_end: pd.Timestamp) -> Tuple[int, int, pd.DataFrame]:
        i_start = int(tr_times.searchsorted(t_start, side="left"))
        i_end = int(tr_times.searchsorted(t_end, side="right"))
        if i_start >= i_end:
            return i_start, i_end, df_tr.iloc[0:0]
        return i_start, i_end, df_tr.iloc[i_start:i_end]

    # Tracking
    kept_indices: Set[int] = set()
    kept_rows: List[pd.Series] = []
    regimes_kept: List[str] = []
    kept_meta_regime: List[str] = []
    kept_meta_match_ts: List[pd.Timestamp] = []
    kept_meta_dist: List[int] = []
    candidates = 0
    admitted = 0
    # Debug counters
    dbg_no_trades_in_window = 0
    dbg_admission_reject = 0
    dbg_alignment_fail = 0
    dbg_dist_too_far = 0

    # Map time -> pos for distance calc
    di_pos = {t: i for i, t in enumerate(di_times)}

    # Iterate over indicator bars (signals-first)
    for i, (ts, row) in enumerate(di_idx.iterrows()):
        # Apply institutional gating if provided; else fallback to exclude_hours
        if gating_thresholds is not None and gating_mod is not None:
            try:
                context = {
                    "now_ts": ts,
                    "indicadores": {
                        "ATR_pct": row.get("ATR_pct"),
                        "BBW_pct": row.get("BBW_pct"),
                        "market_regime": row.get("market_regime", "neutral"),
                    },
                }
                if not gating_mod.should_trade(context, gating_thresholds):
                    continue
            except Exception:
                # if gating fails, default to legacy path below
                pass
        else:
            # Legacy hour exclusion
            hour_val = row.get("hour") if isinstance(row, pd.Series) else None
            try:
                hour = int(hour_val) if hour_val is not None and not pd.isna(hour_val) else None
            except Exception:
                hour = None
            if exclude_hours and hour is not None and int(hour) in set(exclude_hours):
                continue
        # Evaluate if this bar was baseline-eligible on RSI and blocked by ADX/VOTES
        # Use CLI-provided quality thresholds for consistency
        for side in ("long", "short"):
            if not is_baseline_blocked(
                row,
                side=side,
                rsi_buy=rsi_buy,
                rsi_sell=rsi_sell,
                adx_limit=baseline_adx,
                min_votes_long=baseline_votes_long,
                min_votes_short=baseline_votes_short,
                min_atr_pct=min_atr_pct,
                min_bbw_pct=min_bbw_pct,
                rsi_tolerance=rsi_tolerance,
            ):
                continue
            candidates += 1
            # Build time window around this bar using index positions
            left = max(0, i - int(bar_tolerance))
            right = min(len(di_times) - 1, i + int(bar_tolerance))
            t_start = di_times[left]
            t_end = di_times[right]
            i_start, i_end, tr_win = trades_in_window(t_start, t_end)
            if tr_win.empty:
                if log_candidates:
                    print(f"[AB-REJECT] {symbol or ''} ts={ts} side={side} no relaxed trades within ±{bar_tolerance} bars")
                dbg_no_trades_in_window += 1
                continue
            # Evaluate per-regime thresholds using the indicator row
            regime = row.get("market_regime", "neutral")
            adx_val = row.get("ADX", np.nan)
            adx_thr, votes_thr = per_regime_thresholds(regime)
            votes_val = compute_votes(row, side=side, rsi_buy=rsi_buy, rsi_sell=rsi_sell, adx_limit=adx_thr)
            adx_ok = (adx_val is not None and not np.isnan(adx_val) and adx_val >= adx_thr)
            votes_ok = (votes_val >= votes_thr)
            adm_mode = admission_mode_for_regime(regime) if admission_mode == "conditional" else admission_mode
            allow = ((adm_mode == "any") and (adx_ok or votes_ok)) or ((adm_mode == "both") and (adx_ok and votes_ok))
            if not allow:
                if log_candidates:
                    print(f"[AB-REJECT] {symbol or ''} ts={ts} side={side} regime={regime} votes={votes_val} (thr {votes_thr}) adx={float(adx_val) if adx_val is not None and not pd.isna(adx_val) else np.nan:.2f} (thr {adx_thr})")
                dbg_admission_reject += 1
                continue
            # Pick nearest trade in bar distance from this signal bar
            # Compute center_idx of each trade time to indicator index
            best = None  # (dist, tr_idx, tr_row)
            for idx in range(i_start, i_end):
                tr_idx = int(idx)
                tr_row = df_tr.iloc[tr_idx]
                t_tr = tr_times.iloc[tr_idx]
                try:
                    center_idx = di_times.get_indexer([pd.to_datetime(t_tr, utc=True)], method='nearest')[0]
                except Exception:
                    center_idx = -1
                if center_idx == -1:
                    continue
                dist = abs(center_idx - i)
                if best is None or dist < best[0]:
                    best = (dist, tr_idx, tr_row)
            if best is None:
                if log_candidates:
                    print(f"[AB-REJECT] {symbol or ''} ts={ts} side={side} relaxed trades found but none aligned to indicator index")
                dbg_alignment_fail += 1
                continue
            dist, tr_idx, tr_row = best
            if dist <= int(strict_proximity_bars):
                if tr_idx in kept_indices:
                    # already kept via opposite side or nearby signal
                    continue
                kept_indices.add(int(tr_idx))
                kept_rows.append(df_tr.iloc[int(tr_idx)])
                regimes_kept.append(regime)
                kept_meta_regime.append(regime)
                kept_meta_match_ts.append(di_times[i])
                kept_meta_dist.append(int(dist))
                admitted += 1
                if log_candidates:
                    print(f"[AB-ADMIT] {symbol or ''} ts={ts} side={side} -> trade@{tr_row.get(time_col)} d={dist} regime={regime} votes={votes_val} (thr {votes_thr}) adx={float(adx_val) if adx_val is not None and not pd.isna(adx_val) else np.nan:.2f} (thr {adx_thr})")
            else:
                dbg_dist_too_far += 1

    if not kept_rows:
        if log_candidates:
            try:
                print(f"[AB-DEBUG] candidates={candidates} admitted={admitted} no_trades_in_window={dbg_no_trades_in_window} admission_rejects={dbg_admission_reject} alignment_fail={dbg_alignment_fail} dist_too_far={dbg_dist_too_far}")
                if not df_tr.empty:
                    print(f"[AB-DEBUG] relaxed_trades: n={len(df_tr)} time_col={time_col} range=[{tr_times.min()} .. {tr_times.max()}]" )
                if not di_idx.empty:
                    print(f"[AB-DEBUG] indicators: n={len(di_idx)} range=[{di_times.min()} .. {di_times.max()}]")
            except Exception:
                pass
        return pd.DataFrame(columns=df_tr.columns), candidates, admitted, {"unique_regimes": 0, "top_regime_share": np.nan}

    kept_df = pd.DataFrame(kept_rows).reset_index(drop=True)
    # Attach matched regime info for downstream analysis
    try:
        if kept_meta_regime and len(kept_meta_regime) == len(kept_df):
            kept_df["ab_matched_regime"] = kept_meta_regime
        if kept_meta_match_ts and len(kept_meta_match_ts) == len(kept_df):
            kept_df["ab_matched_ts"] = pd.to_datetime(kept_meta_match_ts, utc=True, errors="coerce")
        if kept_meta_dist and len(kept_meta_dist) == len(kept_df):
            kept_df["ab_matched_dist"] = kept_meta_dist
    except Exception:
        pass

    # Diversity metrics
    if regimes_kept:
        vc = pd.Series(regimes_kept).value_counts(normalize=True)
        diversity = {"unique_regimes": int(vc.size), "top_regime_share": float(vc.iloc[0])}
    else:
        diversity = {"unique_regimes": 0, "top_regime_share": np.nan}

    # Attach debug counters for optional export upstream
    diversity.update({
        "dbg_no_trades_in_window": int(dbg_no_trades_in_window),
        "dbg_admission_reject": int(dbg_admission_reject),
        "dbg_alignment_fail": int(dbg_alignment_fail),
        "dbg_dist_too_far": int(dbg_dist_too_far),
    })

    return kept_df, candidates, admitted, diversity


def summarize_symbol(symbol: str, df_sym: pd.DataFrame, months: int | None, bar_tolerance: int = 0, rsi_tolerance: float = 0.0, admission_mode: str = "conditional", min_atr_pct: float = 0.20, min_bbw_pct: float = 0.12, strict_proximity_bars: int = 2, exclude_hours: List[int] | None = None, log_candidates: bool = False, min_mfe_mae_ratio: float | None = None, gating_thresholds: Any | None = None) -> Tuple[Dict[str, Any], Dict[str, Any], pd.DataFrame, Dict[str, Any]]:
    df_sym = slice_months(df_sym, months)
    di = build_indicators(df_sym)
    rsi_buy = getattr(base_cfg, "RSI_LIMIT_COMPRA", 40)
    rsi_sell = getattr(base_cfg, "RSI_LIMIT_VENTA", 60)
    baseline_adx = getattr(base_cfg, "ADX_LIMIT", 23)
    baseline_votes_long = getattr(base_cfg, "MIN_VOTES_COMPRA", 4)
    baseline_votes_short = getattr(base_cfg, "MIN_VOTES_VENTA", 2)
    relaxed_trades = run_engine_relaxed(df_sym)
    if log_candidates:
        try:
            cols = list(relaxed_trades.columns) if isinstance(relaxed_trades, pd.DataFrame) else []
            print(f"[AB-DEBUG] relaxed_trades cols={cols}")
            if isinstance(relaxed_trades, pd.DataFrame) and not relaxed_trades.empty:
                tc = "entry_time" if "entry_time" in relaxed_trades.columns else ("timestamp" if "timestamp" in relaxed_trades.columns else None)
                if tc:
                    tt = pd.to_datetime(relaxed_trades[tc], utc=True, errors="coerce")
                    print(f"[AB-DEBUG] relaxed_trades time range=[{tt.min()} .. {tt.max()}], n={len(relaxed_trades)}")
        except Exception:
            pass
    filtered_trades, candidates, admitted, diversity = filter_trades_prev_blocked_relaxed(
        relaxed_trades,
        di,
        rsi_buy=rsi_buy,
        rsi_sell=rsi_sell,
        baseline_adx=baseline_adx,
        baseline_votes_long=baseline_votes_long,
        baseline_votes_short=baseline_votes_short,
        bar_tolerance=bar_tolerance,
        rsi_tolerance=rsi_tolerance,
        admission_mode=admission_mode,
        min_atr_pct=min_atr_pct,
        min_bbw_pct=min_bbw_pct,
        strict_proximity_bars=strict_proximity_bars,
        exclude_hours=exclude_hours,
        gating_thresholds=gating_thresholds,
        symbol=symbol,
        log_candidates=log_candidates,
    )
    # Optional guardrail: MFE/MAE ratio at trade level if available
    if min_mfe_mae_ratio is not None and not pd.isna(min_mfe_mae_ratio) and not filtered_trades.empty:
        for c_from, c_to in [("mfe", "_mfe"), ("mae", "_mae")]:
            if c_from in filtered_trades.columns:
                filtered_trades[c_to] = pd.to_numeric(filtered_trades[c_from], errors="coerce")
        if "_mfe" in filtered_trades.columns and "_mae" in filtered_trades.columns:
            def _ratio_ok(r):
                mfe = r.get("_mfe")
                mae = r.get("_mae")
                try:
                    if mae is None or pd.isna(mae) or mae == 0:
                        return False
                    return (float(mfe) / float(mae)) >= float(min_mfe_mae_ratio)
                except Exception:
                    return False
            filtered_trades = filtered_trades.loc[filtered_trades.apply(_ratio_ok, axis=1)].reset_index(drop=True)

    # Signals-level block reduction (independent of trades)
    blocked_total = 0
    admitted_total = 0
    for _, row in di.iterrows():
        # Evaluate both sides independently
        for side in ("long", "short"):
            if is_baseline_blocked(
                row,
                side=side,
                rsi_buy=rsi_buy,
                rsi_sell=rsi_sell,
                adx_limit=baseline_adx,
                min_votes_long=baseline_votes_long,
                min_votes_short=baseline_votes_short,
                min_atr_pct=min_atr_pct,
                min_bbw_pct=min_bbw_pct,
                rsi_tolerance=rsi_tolerance,
            ):
                blocked_total += 1
                regime = row.get("market_regime", "neutral")
                adx_val = row.get("ADX")
                # Use per-regime ADX threshold when computing votes for the relaxed scenario
                adx_thr, v_thr = per_regime_thresholds(regime)
                votes_val = compute_votes(row, side=side, rsi_buy=rsi_buy, rsi_sell=rsi_sell, adx_limit=adx_thr)
                if (adx_val is not None and not np.isnan(adx_val) and adx_val >= adx_thr) and (votes_val >= v_thr):
                    admitted_total += 1

    metrics = compute_advanced_metrics(filtered_trades)
    # Augment with fees_share_pct and trades_per_day if missing
    if "fees_share_pct" not in metrics:
        metrics["fees_share_pct"] = np.nan
    # Always recompute trades_per_day over the full window to avoid inflation
    try:
        if not di.empty and "timestamp" in di.columns:
            tmin = pd.to_datetime(di["timestamp"]).min()
            tmax = pd.to_datetime(di["timestamp"]).max()
            total_days = max((tmax - tmin).total_seconds() / 86400.0, 1.0)
            metrics["trades_per_day"] = float(filtered_trades.shape[0]) / total_days if not filtered_trades.empty else 0.0
        else:
            metrics["trades_per_day"] = float("nan")
    except Exception:
        metrics["trades_per_day"] = np.nan
    # Prefer signal-level reduction for acceptance check; keep trade-level in metrics only
    reduction = (admitted_total / max(blocked_total, 1)) * 100.0

    # Baseline has 0 trades on these candidates; deltas thus equal to B metrics
    deltas = {
        "delta_pf_net": metrics.get("pf_net", np.nan),
        "delta_expectancy": metrics.get("expectancy", np.nan),
        "delta_max_dd": metrics.get("max_dd", np.nan),
        "block_reduction_pct": reduction,
        "candidates": blocked_total,
        "admitted": admitted_total,
    }

    result_row = {
        "symbol": symbol,
        "trades": metrics.get("trades", 0),
        "pf_net": metrics.get("pf_net", np.nan),
        "expectancy": metrics.get("expectancy", np.nan),
        "max_dd": metrics.get("max_dd", np.nan),
        "winrate_rolling": metrics.get("winrate_rolling", np.nan),
        "fees_share_pct": metrics.get("fees_share_pct", np.nan),
        "trades_per_day": metrics.get("trades_per_day", np.nan),
        "unique_regimes": diversity.get("unique_regimes", 0),
        "top_regime_share": diversity.get("top_regime_share", np.nan),
    }
    debug_info = {
        "symbol": symbol,
        "candidates": int(candidates),
        "admitted": int(admitted),
        "dbg_no_trades_in_window": int(diversity.get("dbg_no_trades_in_window", 0)),
        "dbg_admission_reject": int(diversity.get("dbg_admission_reject", 0)),
        "dbg_alignment_fail": int(diversity.get("dbg_alignment_fail", 0)),
        "dbg_dist_too_far": int(diversity.get("dbg_dist_too_far", 0)),
        "unique_regimes": diversity.get("unique_regimes", 0),
        "top_regime_share": diversity.get("top_regime_share", np.nan),
    }
    # Ensure symbol column present in trades for aggregation
    if isinstance(filtered_trades, pd.DataFrame) and not filtered_trades.empty:
        if "symbol" not in filtered_trades.columns:
            filtered_trades["symbol"] = symbol
    return result_row, deltas, (filtered_trades if isinstance(filtered_trades, pd.DataFrame) else pd.DataFrame()), debug_info


def main():
    ap = argparse.ArgumentParser(description="A/B sesgo operativo: validar mínimos ADX/VOTES por régimen sobre setups bloqueados")
    ap.add_argument("--master", default=os.path.join("data", "historiales", "historial_trading_maestro_15m.csv"))
    ap.add_argument("--symbols", nargs="*", default=["BTCUSDT", "ETHUSDT", "BNBUSDT", "WLDUSDT"])
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--bar-tolerance", type=int, default=2, help="±bars around blocked timestamps to consider")
    ap.add_argument("--out_csv", default="grid_results_sesgo_fix.csv")
    ap.add_argument("--out_md", default="delta_sesgo_ab.md")
    ap.add_argument("--out_trades", default="", help="Ruta CSV opcional para exportar trades admitidos agregados")
    ap.add_argument("--rsi-tolerance", type=float, default=0.0, help="Tolerancia (en puntos RSI) para considerar near-miss del gate RSI base")
    ap.add_argument("--admission", choices=["both", "any", "conditional"], default="conditional", help="Criterio de admisión: both/any o conditional por régimen")
    ap.add_argument("--min-atr-pct", type=float, default=0.20, help="Filtro de calidad mínima ATR_pct en la fila candidata")
    ap.add_argument("--min-bbw-pct", type=float, default=0.12, help="Filtro de calidad mínima BBW_pct en la fila candidata")
    ap.add_argument("--strict-proximity", type=int, default=2, help="Máxima distancia (en barras) admisible del bloqueo original para admitir el trade")
    ap.add_argument("--exclude-hours", type=str, default="", help="Horas UTC a excluir, separadas por coma. Ej: '0,1,2,12,13,14'")
    ap.add_argument("--log-candidates", action="store_true", help="Loggear mejor candidato por trade admitido")
    ap.add_argument("--min-mfe-mae-ratio", type=float, default=float("nan"), help="Guardrail opcional: exigir MFE/MAE >= umbral si las columnas existen")
    # Optional per-regime MIN_VOTES overrides for sensitivity runs
    ap.add_argument("--neutral-min-votes", type=int, default=None, help="Override de MIN_VOTES para régimen neutral (por defecto 4)")
    ap.add_argument("--range-min-votes", type=int, default=None, help="Override de MIN_VOTES para régimen range (por defecto 3)")
    ap.add_argument("--debug-csv", default="", help="Ruta CSV opcional para exportar contadores de depuración por símbolo")
    # Institucional options (optional)
    ap.add_argument("--institucional", action="store_true", help="Usar config institucional (gating centralizado, filtros por símbolo)")
    ap.add_argument("--config-path", default=os.path.join("config", "institucional.yaml"), help="Ruta a config institucional YAML")
    ap.add_argument("--freeze-run", action="store_true", dest="freeze_run", help="Congelar parámetros y escribir artefactos bajo runs/<timestamp>/ (requiere --institucional)")
    ap.add_argument("--run-dir", default="", help="Override para directorio de run; si se da y --freeze-run, se usa tal cual")
    args = ap.parse_args()

    dfm = load_master(args.master)
    if dfm.empty or "symbol" not in dfm.columns:
        raise RuntimeError("No se pudo cargar el maestro 15m con columna 'symbol'.")

    # Prepare institutional config if requested
    inst_cfg = None
    run_dir = None
    if getattr(args, "institucional", False) and instit_mod is not None:
        try:
            inst_cfg = instit_mod.get_institucional_config(args.config_path)
        except Exception as e:
            print(f"[WARN] No se pudo cargar config institucional: {e}")
            inst_cfg = None
        if getattr(args, "freeze_run", False) and inst_cfg is not None:
            ts = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
            run_dir = args.run_dir.strip() or os.path.join("data", "backtesting", "runs", ts)
            os.makedirs(run_dir, exist_ok=True)
            try:
                freeze_path = instit_mod.freeze_params(run_dir, inst_cfg, extra={
                    "script": os.path.basename(__file__),
                    "cli_args": vars(args),
                })
                print(f"Params frozen at: {freeze_path}")
            except Exception as e:
                print(f"[WARN] No se pudo congelar parámetros: {e}")

    rows: List[Dict[str, Any]] = []
    deltas: List[Dict[str, Any]] = []
    debug_rows: List[Dict[str, Any]] = []
    trades_agg: List[pd.DataFrame] = []
    exclude_hours = [int(x.strip()) for x in args.exclude_hours.split(",") if x.strip().isdigit()] if args.exclude_hours else []
    for sym in args.symbols:
        part = dfm.loc[dfm["symbol"] == sym].copy()
        if part.empty:
            continue
        # Build gating thresholds from institutional config if available for this symbol
        gating_thresholds = None
        min_atr_pct = args.min_atr_pct
        min_bbw_pct = args.min_bbw_pct
        if inst_cfg is not None and sym in inst_cfg.symbols:
            scfg = inst_cfg.symbols[sym]
            # Skip disabled symbols silently
            if not getattr(scfg, "enabled", True):
                continue
            # Resolve allowed hours from symbol filters (already computed by loader)
            try:
                allowed_hours = scfg.filters.get("allowed_hours") if isinstance(scfg.filters, dict) else None
                # If CLI provided explicit exclude-hours, override allowed via complement
                if exclude_hours:
                    if gating_mod is not None:
                        allowed_hours = gating_mod.normalize_hours(exclude_hours)
            except Exception:
                allowed_hours = None
            # Floors
            try:
                if isinstance(scfg.filters, dict):
                    min_atr_pct = float(scfg.filters.get("min_atr_pct", min_atr_pct))
                    min_bbw_pct = float(scfg.filters.get("min_bbw_pct", min_bbw_pct))
            except Exception:
                pass
            # Allowed regimes
            allowed_regimes = None
            try:
                if isinstance(scfg.filters, dict):
                    ar = scfg.filters.get("allowed_regimes")
                    if isinstance(ar, list) and ar:
                        allowed_regimes = [str(x) for x in ar]
            except Exception:
                allowed_regimes = None
            # Construct thresholds object
            try:
                if gating_mod is not None and hasattr(gating_mod, "GatingThresholds"):
                    gating_thresholds = gating_mod.GatingThresholds(
                        allowed_hours=allowed_hours,
                        allowed_regimes=allowed_regimes,
                        atr_min_percentile=float(min_atr_pct),
                        bbw_min_percentile=float(min_bbw_pct),
                    )
            except Exception:
                gating_thresholds = None
        # Apply per-regime overrides if provided
        global REGIME_VOTES_OVERRIDE
        REGIME_VOTES_OVERRIDE = {}
        if args.neutral_min_votes is not None:
            REGIME_VOTES_OVERRIDE["neutral"] = int(args.neutral_min_votes)
        if args.range_min_votes is not None:
            REGIME_VOTES_OVERRIDE["range"] = int(args.range_min_votes)
        rrow, drow, trades_df, dbg = summarize_symbol(
            sym,
            part,
            args.months,
            bar_tolerance=args.bar_tolerance,
            rsi_tolerance=args.rsi_tolerance,
            admission_mode=args.admission,
            min_atr_pct=min_atr_pct,
            min_bbw_pct=min_bbw_pct,
            strict_proximity_bars=args.strict_proximity,
            exclude_hours=exclude_hours or None,
            log_candidates=args.log_candidates,
            min_mfe_mae_ratio=(args.min_mfe_mae_ratio if not np.isnan(args.min_mfe_mae_ratio) else None),
            gating_thresholds=gating_thresholds,
        )
        rows.append(rrow)
        drow["symbol"] = sym
        deltas.append(drow)
        debug_rows.append(dbg)
        if isinstance(trades_df, pd.DataFrame) and not trades_df.empty:
            tdf = trades_df.copy()
            # guarantee symbol and matched regime columns
            if "symbol" not in tdf.columns:
                tdf["symbol"] = sym
            trades_agg.append(tdf)

    # Resolve output paths (respect run_dir if freezing)
    out_csv = args.out_csv
    out_md = args.out_md
    out_trades = args.out_trades
    if run_dir:
        try:
            out_csv = os.path.join(run_dir, os.path.basename(out_csv))
            out_md = os.path.join(run_dir, os.path.basename(out_md))
            if out_trades:
                out_trades = os.path.join(run_dir, os.path.basename(out_trades))
        except Exception:
            pass

    if rows:
        pd.DataFrame(rows).to_csv(out_csv, index=False)
    # Export aggregated trades if requested
    wrote_trades = False
    if out_trades and trades_agg:
        try:
            pd.concat(trades_agg, ignore_index=True).to_csv(out_trades, index=False)
            wrote_trades = True
        except Exception as e:
            logging.warning(f"No se pudo exportar trades a {out_trades}: {e}")
    # Optional debug CSV export
    if args.debug_csv:
        try:
            pd.DataFrame(debug_rows).to_csv(args.debug_csv, index=False)
        except Exception as e:
            logging.warning(f"No se pudo exportar debug a {args.debug_csv}: {e}")
    else:
        # Fallback: si no se pidió explícitamente y no hubo trades, guardar contadores para diagnóstico
        try:
            total_trades = int(sum([int(r.get("trades", 0)) for r in rows])) if rows else 0
        except Exception:
            total_trades = 0
        if total_trades == 0 and debug_rows:
            try:
                dbg_path = os.path.splitext(out_csv)[0] + "_debug.csv"
                pd.DataFrame(debug_rows).to_csv(dbg_path, index=False)
            except Exception as e:
                logging.warning(f"No se pudo exportar debug a {dbg_path}: {e}")

    # Build markdown delta
    lines: List[str] = ["# A/B Sesgo Operativo — Ajustes mínimos por régimen", ""]
    lines.append("## Configuración")
    lines.append("")
    lines.append(f"- months: {args.months}")
    lines.append(f"- bar_tolerance: ±{args.bar_tolerance}")
    lines.append(f"- strict_proximity: ±{args.strict_proximity}")
    lines.append(f"- rsi_tolerance: ±{args.rsi_tolerance}")
    lines.append(f"- admission: {args.admission}")
    lines.append(f"- min_atr_pct: {args.min_atr_pct}")
    lines.append(f"- min_bbw_pct: {args.min_bbw_pct}")
    if exclude_hours:
        lines.append(f"- exclude_hours UTC: {exclude_hours}")
    if not np.isnan(args.min_mfe_mae_ratio):
        lines.append(f"- min_mfe_mae_ratio: {args.min_mfe_mae_ratio}")
    lines.append("")
    lines.append("## Resumen por símbolo")
    lines.append("| Símbolo | Δpf_net | Δexpectancy | Δmax_dd | Reducción bloqueos (ADX/VOTES) | Candidatos | Admitidos |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for d in deltas:
        lines.append(f"| {d['symbol']} | {d['delta_pf_net']:.3f} | {d['delta_expectancy']:.5f} | {d['delta_max_dd']:.3f} | {d['block_reduction_pct']:.1f}% | {d['candidates']} | {d['admitted']} |")
    lines.append("")
    # Note on diversity/fees
    lines.append("> Nota: Ver grid_results_sesgo_fix.csv para fees_share_pct, trades_per_day y diversidad por régimen (unique_regimes, top_regime_share).")
    # Acceptance checks
    lines.append("## Criterios de aceptación")
    lines.append("- Reducción ≥ 20% bloqueos por ADX/VOTES en regímenes afectados")
    lines.append("- pf_net y expectancy iguales o mejores (vs baseline bloqueado ≈ 0)")
    lines.append("- max_dd no empeora más de 10% (no aplica con baseline=0; observar valor absoluto)")
    lines.append("- Diversidad operativa aumentada sin inflar falsos positivos (revisar trades y fees_share en análisis posterior)")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    if wrote_trades:
        print(f"Generados {out_csv}, {out_md} y {out_trades}")
    else:
        print(f"Generados {out_csv} y {out_md}")


if __name__ == "__main__":
    main()

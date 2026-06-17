"""
Simplified, robust backtesting engine entry points aligned with the institutional pipeline.
- Exposes BTConfig, backtesting (wrapper), backtesting_legacy (placeholder), guardar_resultados_por_par
- Provides a CLI without hardcoded 30-day cut; supports --symbols/--months/--days/--master
- Delegates cleaning and data loading to src.core.utilidades and src.pipeline.carga_datos

NOTE: This file intentionally avoids modifying internal legacy simulation logic. If a richer
engine exists elsewhere, wire it in backtesting_legacy. The goal here is to restore a clean
and working module so downstream scripts run again.
"""
from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple, cast, TYPE_CHECKING
import math
from collections import defaultdict

# Loader institucional y freezing
try:
    from src.config_loader import get_institucional_config, freeze_params
except Exception:
    get_institucional_config = None
    freeze_params = None

import numpy as np
import pandas as pd
from pandas.tseries.offsets import DateOffset

if TYPE_CHECKING:
    from src.config_loader import InstitucionalConfig, SymbolConfig


# Logger
logger = logging.getLogger("backtesting")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler("logs/backtesting.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(ch)


# Optional centralized metrics (disabled here to keep this module standalone)
_pf_helper = None  # type: ignore
_mdd_helper = None  # type: ignore


# Reuse helpers from project
try:
    from src.core.utilidades import limpiar_ohlcv  # type: ignore
except Exception:
    def limpiar_ohlcv(df: pd.DataFrame) -> pd.DataFrame:  # minimal fallback
        if df is None or df.empty:
            return pd.DataFrame()
        cols = [c for c in df.columns if isinstance(c, str)]
        df = df[cols].copy()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        for c in ("open", "high", "low", "close", "volume"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=[c for c in ("timestamp", "close") if c in df.columns]).reset_index(drop=True)


try:
    from src.pipeline.carga_datos import cargar_y_combinar_datos  # type: ignore
except Exception:
    def cargar_y_combinar_datos(path: str, client=None, symbol: str | None = None, meses: int = 0) -> pd.DataFrame:  # minimal fallback
        df = pd.read_csv(path)
        if symbol and "symbol" in df.columns:
            df = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        return df.reset_index(drop=True)


# Integración de policies institucionales
try:
    import src.policies.gating as gating_mod  # type: ignore
except Exception:
    gating_mod = None
try:
    import src.policies.regime as regime_mod  # type: ignore
except Exception:
    regime_mod = None
try:
    import src.policies.percentiles as pct_mod  # type: ignore
except Exception:
    pct_mod = None
try:
    import src.policies.votes as votes_mod  # type: ignore
except Exception:
    votes_mod = None

# Indicadores y métricas centralizadas
try:
    from src.core.gestor_indicadores import calcular_todos_los_indicadores  # type: ignore
except Exception:
    calcular_todos_los_indicadores = None
try:
    from src.reporting.metrics import compute_advanced_metrics  # type: ignore
except Exception:
    compute_advanced_metrics = None
try:
    from src.core import config_estrategias as base_cfg  # type: ignore
except Exception:
    class _FallbackCfg:
        RSI_LIMIT_COMPRA = 40
        RSI_LIMIT_VENTA = 60
        ADX_LIMIT = 23
        MIN_VOTES_COMPRA = 4
        MIN_VOTES_VENTA = 2
        SL_MULT = 1.5
        TP_MULT = 3.0
        ATR_MIN = 1.0
        TRAILING_STOP = 1.0
    base_cfg = _FallbackCfg()  # type: ignore


# ------------------------------------------------------------------
# Public config structure compatible with consumers
# ------------------------------------------------------------------
@dataclass
class BTConfig:
    min_distance_bars: int = 8
    # Core backtesting settings
    allowed_regimes: Optional[List[str]] = None
    allowed_hours: Optional[List[int]] = None
    min_atr_pct: float = 0.22
    min_bbw_pct: float = 0.15
    cooldown_bars: int = 2
    max_trades_per_day: int = 6
    starting_capital: float = 100.0
    fee_bps: float = 8.0
    slippage_bps: float = 5.0
    tick_size: float = 0.01
    max_duracion: int = 50
    trailing_stop: bool = True
    # TP/SL dinámico por régimen (Beta A2)
    tp_sl_by_regime: Optional[Dict[str, Dict[str, float]]] = None
    sl_mult: float = getattr(base_cfg, "SL_MULT", 1.5)
    tp_mult: float = getattr(base_cfg, "TP_MULT", 3.0)
    perfil_tp_sl: Optional[str] = None  # 'conservador' o 'agresivo'
    # Guardrails Beta A2
    strict_proximity_bars: int = 2
    min_mfe_mae_ratio: Optional[float] = None
    bar_tolerance: int = 6
    rsi_tolerance: float = 2.0
    admission_mode: str = "conditional"  # "conditional", "both", "any"
    neutral_min_votes: int = 4
    exclude_hours: Optional[List[int]] = None
    min_pf_net: Optional[float] = None
    max_dd_pct: Optional[float] = None
    # Control de ejecución
    symbol: Optional[str] = None
    enforce_net_metrics: bool = True
    debug_counters: bool = False
    # Configuración institucional de guardrails
    guardrails: Dict[str, Any] = field(default_factory=dict)


def _normalize_tp_sl_profile(raw_profile: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    normalized: Dict[str, Dict[str, float]] = {}
    if not isinstance(raw_profile, dict):
        return normalized
    for regime, params in raw_profile.items():
        if not isinstance(params, dict):
            continue
        sl_keys = ("sl_mult", "SL_MULT", "sl", "stop_loss")
        tp_keys = ("tp_mult", "TP_MULT", "tp", "take_profit")
        sl_val: Optional[float] = None
        tp_val: Optional[float] = None
        for key in sl_keys:
            if key in params and params[key] is not None:
                try:
                    sl_val = float(params[key])
                    break
                except Exception:
                    continue
        for key in tp_keys:
            if key in params and params[key] is not None:
                try:
                    tp_val = float(params[key])
                    break
                except Exception:
                    continue
        if sl_val is None and tp_val is None:
            continue
        normalized[str(regime).lower()] = {
            "sl_mult": sl_val if sl_val is not None else float(getattr(base_cfg, "SL_MULT", 1.5)),
            "tp_mult": tp_val if tp_val is not None else float(getattr(base_cfg, "TP_MULT", 3.0)),
        }
    return normalized


def bt_config_from_symbol(
    instit_cfg: "InstitucionalConfig",
    symbol: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> BTConfig:
    symbol_key = str(symbol).upper()
    if symbol_key not in instit_cfg.symbols:
        raise KeyError(f"Símbolo {symbol_key} no definido en institucional.yaml")

    symbol_cfg: "SymbolConfig" = instit_cfg.symbols[symbol_key]
    defaults_filters = dict(instit_cfg.defaults.get("filters", {}))
    filters = dict(defaults_filters)
    filters.update(symbol_cfg.filters or {})

    defaults_execution = dict(instit_cfg.defaults.get("execution", {}))
    execution = dict(defaults_execution)
    execution.update(symbol_cfg.execution or {})

    guardrails_defaults = dict(instit_cfg.defaults.get("guardrails", {}))
    guardrails = dict(guardrails_defaults)
    guardrails.update(overrides.get("guardrails", {}) if overrides else {})

    tp_sl_profile = _normalize_tp_sl_profile(symbol_cfg.tp_sl_by_regime or instit_cfg.defaults.get("tp_sl_by_regime"))

    allowed_hours_raw = filters.get("allowed_hours")
    allowed_hours = None
    if isinstance(allowed_hours_raw, (list, tuple)):
        try:
            allowed_hours = [int(h) % 24 for h in allowed_hours_raw]
        except Exception:
            allowed_hours = None

    allowed_regimes_raw = filters.get("allowed_regimes")
    allowed_regimes = None
    if isinstance(allowed_regimes_raw, (list, tuple)):
        allowed_regimes = [str(r).lower() for r in allowed_regimes_raw]

    cooldown = int(filters.get("cooldown_bars", 2) or 0)
    max_trades_per_day = int(execution.get("max_trades_per_day", guardrails.get("max_trades_per_day", 6)) or 0)
    max_duracion = int(execution.get("max_duracion", 50) or 0)
    trailing_stop = bool(execution.get("trailing_stop", True))

    cfg = BTConfig(
        allowed_regimes=allowed_regimes,
        allowed_hours=allowed_hours,
        min_atr_pct=float(filters.get("min_atr_pct", 0.22) or 0.0),
        min_bbw_pct=float(filters.get("min_bbw_pct", 0.15) or 0.0),
        cooldown_bars=cooldown,
        max_trades_per_day=max_trades_per_day,
        starting_capital=float(execution.get("starting_capital", 100.0) or 100.0),
        fee_bps=float(execution.get("fee_bps", 8.0) or 0.0),
        slippage_bps=float(execution.get("slippage_bps", 5.0) or 0.0),
        tick_size=float(execution.get("tick_size", 0.01) or 0.0),
        max_duracion=max_duracion,
        trailing_stop=trailing_stop,
        tp_sl_by_regime=tp_sl_profile,
        sl_mult=float(execution.get("sl_mult", getattr(base_cfg, "SL_MULT", 1.5))),
        tp_mult=float(execution.get("tp_mult", getattr(base_cfg, "TP_MULT", 3.0))),
        min_mfe_mae_ratio=float(guardrails.get("min_mfe_mae_ratio")) if guardrails.get("min_mfe_mae_ratio") is not None else None,
        strict_proximity_bars=int(filters.get("strict_proximity", guardrails.get("strict_proximity", 0)) or 0),
        guardrails=guardrails,
        perfil_tp_sl=overrides.get("perfil_tp_sl") if overrides else None,
        symbol=symbol_key,
    )

    if overrides:
        for key, value in overrides.items():
            if key == "guardrails":
                continue
            if hasattr(cfg, key):
                setattr(cfg, key, value)

    return cfg


def _safe_float(value: Any, default: float = np.nan) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except Exception:
        return float(default)


def _ensure_percentiles(di: pd.DataFrame, window: int = 200) -> pd.DataFrame:
    if di is None:
        return pd.DataFrame()
    out = pd.DataFrame(di).copy()
    if out.empty:
        return out
    applied = False
    if pct_mod is not None:
        for attr in ("add_atr_bbw_percentiles", "add_atr_bbw_pct"):
            fn = getattr(pct_mod, attr, None)
            if callable(fn):
                try:
                    res = fn(out, atr_col="ATR", bbw_col="BB_Width", window=window)
                    out = pd.DataFrame(cast(Any, res)).copy()
                    applied = True
                    break
                except Exception:
                    logger.debug("Fallo add_atr_bbw_percentiles; usando fallback", exc_info=True)
    if not applied:
        def _pct_rank_last(series: pd.Series) -> float:
            s = pd.Series(series).dropna()
            if s.empty:
                return float("nan")
            return float(s.rank(pct=True).iloc[-1])
        if "ATR" in out.columns:
            out["ATR_pct"] = out["ATR"].rolling(window, min_periods=max(10, window // 5)).apply(_pct_rank_last, raw=False)
        if "BB_Width" in out.columns:
            out["BBW_pct"] = out["BB_Width"].rolling(window, min_periods=max(10, window // 5)).apply(_pct_rank_last, raw=False)
    if "ATR_pct" in out.columns:
        out["ATR_pct"] = pd.to_numeric(out["ATR_pct"], errors="coerce").clip(lower=0.0, upper=1.0)
    else:
        out["ATR_pct"] = np.nan
    if "BBW_pct" in out.columns:
        out["BBW_pct"] = pd.to_numeric(out["BBW_pct"], errors="coerce").clip(lower=0.0, upper=1.0)
    else:
        out["BBW_pct"] = np.nan
    return out


def _classify_regime(row: pd.Series) -> str:
    if regime_mod is not None and hasattr(regime_mod, "classify_regime"):
        try:
            return str(regime_mod.classify_regime(row.to_dict()))
        except Exception:
            logger.debug("classify_regime fallo; fallback", exc_info=True)
    adx = _safe_float(row.get("ADX", np.nan), default=np.nan)
    atrp = _safe_float(row.get("ATR_pct", np.nan), default=np.nan)
    bbwp = _safe_float(row.get("BBW_pct", np.nan), default=np.nan)
    if pd.notna(adx) and adx >= 25 and pd.notna(bbwp) and bbwp >= 0.6:
        return "trend"
    if pd.notna(adx) and adx < 18 and pd.notna(bbwp) and bbwp < 0.4:
        return "range"
    if pd.notna(atrp) and atrp >= 0.75:
        return "high_vol"
    if pd.notna(atrp) and atrp <= 0.25:
        return "low_vol"
    return "neutral"


def _compute_votes(row: pd.Series, side: str, rsi_buy: float, rsi_sell: float, adx_limit: float) -> int:
    if votes_mod is not None and hasattr(votes_mod, "compute_votes"):
        try:
            return int(votes_mod.compute_votes(row.to_dict(), side=side))
        except Exception:
            logger.debug("compute_votes policy fallo; fallback", exc_info=True)
    votes = 0
    rsi_val = _safe_float(row.get("RSI"), default=np.nan)
    if side == "long" and pd.notna(rsi_val) and rsi_val < rsi_buy:
        votes += 1
    if side == "short" and pd.notna(rsi_val) and rsi_val > rsi_sell:
        votes += 1
    adx_val = _safe_float(row.get("ADX"), default=np.nan)
    if pd.notna(adx_val) and adx_val >= adx_limit:
        votes += 1
    atrp = _safe_float(row.get("ATR_pct", 0.5), default=0.5)
    if 0.25 <= atrp <= 0.85:
        votes += 1
    bbw = _safe_float(row.get("BBW_pct", 0.5), default=0.5)
    if bbw <= 0.6:
        votes += 1
    macd_hist = _safe_float(row.get("hist"), default=np.nan)
    if side == "long" and pd.notna(macd_hist) and macd_hist > 0:
        votes += 1
    if side == "short" and pd.notna(macd_hist) and macd_hist < 0:
        votes += 1
    return int(votes)


def _per_regime_thresholds(regime: str, default_adx: float, default_votes: int) -> Tuple[float, int]:
    regime = (regime or "").strip().lower()
    if regime == "trend":
        return (max(default_adx, 21.0), max(default_votes, 3))
    if regime == "neutral":
        return (max(default_adx, 17.0), max(default_votes, 4))
    if regime == "range":
        return (max(default_adx, 17.0), max(default_votes, 3))
    if regime in ("low_vol", "high_vol"):
        return (max(default_adx, 18.0), max(default_votes, 2))
    return (default_adx, default_votes)


def _resolve_tp_sl(cfg: BTConfig, regime: str) -> Tuple[float, float]:
    profile = getattr(cfg, "tp_sl_by_regime", None)
    if isinstance(profile, dict):
        regime_key = str(regime or "neutral").lower()
        regime_cfg = profile.get(regime_key) or profile.get(regime)
        if isinstance(regime_cfg, dict):
            sl = regime_cfg.get("sl_mult")
            if sl is None:
                sl = regime_cfg.get("SL_MULT") or regime_cfg.get("sl") or regime_cfg.get("stop_loss")
            tp = regime_cfg.get("tp_mult")
            if tp is None:
                tp = regime_cfg.get("TP_MULT") or regime_cfg.get("tp") or regime_cfg.get("take_profit")
            sl_final = float(sl) if sl is not None else cfg.sl_mult
            tp_final = float(tp) if tp is not None else cfg.tp_mult
            return (sl_final, tp_final)
    return (cfg.sl_mult, cfg.tp_mult)


def _check_strict_proximity_guardrail(cfg: BTConfig, last_signal_idx: Dict[str, int], current_idx: int, signal_type: str) -> bool:
    """Guardrail Beta A2: Verifica proximidad estricta entre señales del mismo tipo."""
    strict_bars = getattr(cfg, "strict_proximity_bars", 0)
    if strict_bars <= 0:
        return True
    
    last_idx = last_signal_idx.get(signal_type)
    if last_idx is not None and (current_idx - last_idx) < strict_bars:
        return False
    return True


def _check_mfe_mae_ratio_guardrail(cfg: BTConfig, trade: Dict[str, Any]) -> bool:
    """Guardrail Beta A2: Verifica ratio MFE/MAE mínimo."""
    min_ratio = getattr(cfg, "min_mfe_mae_ratio", None)
    if not isinstance(min_ratio, (int, float)) or min_ratio <= 0:
        return True
    
    mfe = trade.get("mfe", 0.0)
    mae = trade.get("mae", 0.0)
    
    if mae <= 0:  # Evitar división por cero
        return True
    
    ratio = abs(mfe) / abs(mae)
    return ratio >= min_ratio


def _check_admission_mode(cfg: BTConfig, indicators: pd.DataFrame, idx: int) -> Tuple[bool, bool]:
    """Beta A2: Verifica modo de admisión (conditional, both, any)."""
    mode = getattr(cfg, "admission_mode", "conditional")
    
    if mode == "both":
        return True, True  # Permitir compra y venta
    elif mode == "any":
        return True, True  # Permitir compra y venta
    else:  # conditional
        # Lógica condicional basada en régimen/indicadores
        regime = indicators.iloc[idx].get("regime", "neutral") if idx < len(indicators) else "neutral"
        
        # Reglas básicas condicionales
        allow_buy = regime in ["bull", "neutral"]
        allow_sell = regime in ["bear", "neutral"]
        
        return allow_buy, allow_sell


def _check_bar_tolerance(cfg: BTConfig, df_prices: pd.DataFrame, idx: int) -> bool:
    """Beta A2: Verifica tolerancia de barras desde el último trade."""
    tolerance = getattr(cfg, "bar_tolerance", 6)
    if tolerance <= 0:
        return True
    
    # Implementación simplificada - en producción verificaría último trade
    return True


def _check_rsi_tolerance(cfg: BTConfig, indicators: pd.DataFrame, idx: int) -> bool:
    """Beta A2: Verifica tolerancia RSI."""
    tolerance = getattr(cfg, "rsi_tolerance", 2.0)
    if tolerance <= 0:
        return True
    
    if idx >= len(indicators) or "rsi" not in indicators.columns:
        return True
    
    rsi = indicators.iloc[idx].get("rsi")
    if pd.isna(rsi):
        return True
    
    # Verificar que RSI no esté en zona extrema fuera de tolerancia
    if rsi < (30 - tolerance) or rsi > (70 + tolerance):
        return False
    
    return True


def _check_neutral_votes_guardrail(cfg: BTConfig, indicators: pd.DataFrame, idx: int) -> bool:
    """Beta A2: Verifica mínimo de votos neutrales."""
    min_votes = getattr(cfg, "neutral_min_votes", 4)
    if min_votes <= 0:
        return True
    
    if idx >= len(indicators):
        return False
    
    # Buscar columnas de votos
    vote_cols = [c for c in indicators.columns if "votos" in c.lower() or "votes" in c.lower()]
    if not vote_cols:
        return True  # Sin datos de votos, permitir
    
    total_votes = 0
    for col in vote_cols:
        val = indicators.iloc[idx].get(col, 0)
        if pd.notna(val):
            total_votes += abs(val)
    
    return total_votes >= min_votes


def _round_price(price: float, tick: float) -> float:
    if tick is None or tick <= 0:
        return float(price)
    try:
        return round(price / tick) * tick
    except Exception:
        return float(price)


def _entry_signal(row: pd.Series, cfg: BTConfig, side: str, cooldown_ok: bool = True) -> Tuple[bool, Dict[str, Any]]:
    debug: Dict[str, Any] = {}
    if not cooldown_ok:
        return False, debug
    ts_raw = row.get("timestamp")
    ts = pd.NaT
    if ts_raw is not None:
        try:
            ts = pd.to_datetime(ts_raw, utc=True)
        except Exception:
            ts = pd.NaT
    # allowed_hours obligatorio
    if cfg.allowed_hours is not None:
        hour = None
        try:
            if ts is not None and hasattr(ts, "hour"):
                hour = int(ts.hour)
            elif ts_raw is not None:
                hour = int(pd.to_datetime(ts_raw, utc=True).hour)
        except Exception:
            hour = None
        if hour is not None and hour not in set(int(h) for h in cfg.allowed_hours):
            return False, debug
    # allowed_regimes obligatorio
    regime = str(row.get("market_regime", "neutral") or "neutral")
    if cfg.allowed_regimes and regime not in set(cfg.allowed_regimes):
        return False, debug
    # Filtro robusto ATR/BBW obligatorio
    atr_pct = _safe_float(row.get("ATR_pct"), default=np.nan)
    if np.isnan(atr_pct):
        try:
            atr = _safe_float(row.get("ATR"), default=np.nan)
            close = _safe_float(row.get("close"), default=np.nan)
            if not np.isnan(atr) and not np.isnan(close) and close != 0:
                atr_pct = (atr / close) * 100
        except Exception:
            pass
    bbw_pct = _safe_float(row.get("BBW_pct"), default=np.nan)
    if np.isnan(bbw_pct):
        bbw = _safe_float(row.get("BBWidth"), default=np.nan)
        if np.isnan(bbw):
            bbw = _safe_float(row.get("BB_Width"), default=np.nan)
        close = _safe_float(row.get("close"), default=np.nan)
        if not np.isnan(bbw) and not np.isnan(close) and close != 0:
            bbw_pct = (bbw / close) * 100
    # Solo rechaza si sigue NaN o menor que min
    if np.isnan(atr_pct) or atr_pct < cfg.min_atr_pct:
        debug.update({"atr_pct": atr_pct, "regime": regime, "bbw_pct": bbw_pct})
        return False, debug
    if np.isnan(bbw_pct) or bbw_pct < cfg.min_bbw_pct:
        debug.update({"atr_pct": atr_pct, "regime": regime, "bbw_pct": bbw_pct})
        return False, debug
    # Gating por RSI/ADX/Votes solo si cfg.use_entry_signal_indicators==True
    use_ind = getattr(cfg, "use_entry_signal_indicators", False)
    rsi_val = _safe_float(row.get("RSI"), default=np.nan)
    adx_val = _safe_float(row.get("ADX"), default=np.nan)
    votes_val = None
    if use_ind:
        rsi_buy = getattr(base_cfg, "RSI_LIMIT_COMPRA", 40)
        rsi_sell = getattr(base_cfg, "RSI_LIMIT_VENTA", 60)
        if side == "long" and (pd.isna(rsi_val) or rsi_val >= rsi_buy):
            debug.update({"atr_pct": atr_pct, "regime": regime, "bbw_pct": bbw_pct, "rsi": rsi_val})
            return False, debug
        if side == "short" and (pd.isna(rsi_val) or rsi_val <= rsi_sell):
            debug.update({"atr_pct": atr_pct, "regime": regime, "bbw_pct": bbw_pct, "rsi": rsi_val})
            return False, debug
        adx_default = getattr(base_cfg, "ADX_LIMIT", 23)
        min_votes_default = getattr(base_cfg, "MIN_VOTES_COMPRA" if side == "long" else "MIN_VOTES_VENTA", 2)
        adx_thr, votes_thr = _per_regime_thresholds(regime, adx_default, min_votes_default)
        if pd.isna(adx_val) or adx_val < adx_thr:
            debug.update({"atr_pct": atr_pct, "regime": regime, "bbw_pct": bbw_pct, "adx": adx_val})
            return False, debug
        votes_val = _compute_votes(row, side, rsi_buy, rsi_sell, adx_thr)
        if votes_val < votes_thr:
            debug.update({"atr_pct": atr_pct, "regime": regime, "bbw_pct": bbw_pct, "votes": votes_val, "votes_thr": votes_thr})
            return False, debug
    debug.update({
        "atr_pct": atr_pct,
        "bbw_pct": bbw_pct,
        "regime": regime,
        "rsi": rsi_val,
        "adx": adx_val,
        "votes": votes_val,
    })
    return True, debug


def _fallback_indicators(df: pd.DataFrame) -> pd.DataFrame:
    base = df.copy().reset_index(drop=True)
    if base.empty:
        return pd.DataFrame(columns=["RSI", "ADX", "ATR", "BB_Width", "hist", "market_regime"])

    result = base.copy()
    for col in ("open", "high", "low", "close"):
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    idx = result.index
    rsi_series = pd.Series(np.nan, index=idx, dtype=float)
    adx_series = pd.Series(np.nan, index=idx, dtype=float)
    atr_series = pd.Series(np.nan, index=idx, dtype=float)
    bbw_series = pd.Series(np.nan, index=idx, dtype=float)
    hist_series = pd.Series(0.0, index=idx, dtype=float)

    try:
        import ta  # type: ignore[import-not-found]
        if "close" in result.columns:
            try:
                rsi_series = ta.momentum.RSIIndicator(close=result["close"], window=14).rsi()  # type: ignore[attr-defined]
            except Exception:
                rsi_series = rsi_series
            try:
                adx_series = ta.trend.ADXIndicator(high=result["high"], low=result["low"], close=result["close"], window=14).adx()  # type: ignore[attr-defined]
            except Exception:
                adx_series = adx_series
            try:
                atr_series = ta.volatility.AverageTrueRange(high=result["high"], low=result["low"], close=result["close"], window=14).average_true_range()  # type: ignore[attr-defined]
            except Exception:
                atr_series = atr_series
            try:
                macd_tmp = ta.trend.MACD(close=result["close"])  # type: ignore[attr-defined]
                if macd_tmp is not None:
                    hist_col = next((c for c in macd_tmp.columns if c.lower().endswith("_h")), None)
                    if hist_col:
                        hist_series = pd.to_numeric(macd_tmp[hist_col], errors="coerce")
            except Exception:
                hist_series = hist_series
    except Exception:
        ta = None  # type: ignore[assignment]

    if "close" in result.columns and "high" in result.columns and "low" in result.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            bbw_series = (pd.to_numeric(result["high"], errors="coerce") - pd.to_numeric(result["low"], errors="coerce")) / pd.to_numeric(result["close"], errors="coerce")
            bbw_series = bbw_series.replace([np.inf, -np.inf], np.nan)

    result["RSI"] = pd.to_numeric(rsi_series, errors="coerce")
    result["ADX"] = pd.to_numeric(adx_series, errors="coerce")
    result["ATR"] = pd.to_numeric(atr_series, errors="coerce")
    result["BB_Width"] = pd.to_numeric(bbw_series, errors="coerce")
    result["hist"] = pd.to_numeric(hist_series, errors="coerce")
    if "market_regime" in result.columns:
        result["market_regime"] = result["market_regime"].fillna("neutral")
    else:
        result["market_regime"] = pd.Series(["neutral"] * len(result), index=result.index, dtype=object)

    return result


def _simulate_trades(df_prices: pd.DataFrame, indicators: pd.DataFrame, cfg: BTConfig) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    last_entry_idx = None
    if df_prices.empty or indicators.empty:
        return [], pd.DataFrame()

    tick = float(cfg.tick_size or 0.0)
    fee_rate = float(cfg.fee_bps or 0.0) / 10_000.0
    slip_rate = float(cfg.slippage_bps or 0.0) / 10_000.0
    max_duracion = max(int(cfg.max_duracion or 0), 1)
    use_trailing = bool(cfg.trailing_stop)

    resultados: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    open_trade: Optional[Dict[str, Any]] = None
    cooldown = 0
    trades_per_day: Dict[pd.Timestamp, int] = defaultdict(int)
    guardrail_stats: Dict[str, int] = defaultdict(int)
    strict_limit = int(getattr(cfg, "strict_proximity_bars", 0) or 0)
    last_signal_idx: Dict[str, int] = {}
    min_mfe_ratio_raw = getattr(cfg, "min_mfe_mae_ratio", None)
    min_mfe_ratio: Optional[float]
    if isinstance(min_mfe_ratio_raw, (int, float)):
        try:
            val = float(min_mfe_ratio_raw)
            min_mfe_ratio = None if math.isnan(val) else val
        except Exception:
            min_mfe_ratio = None
    else:
        min_mfe_ratio = None

    # Instrumentación
    n_bars = 0
    n_buy_true = 0
    n_buy_false = 0
    n_skip_min_distance = 0
    n_exception_buy = 0

    # Contadores de bloqueos/aperturas
    n_block_in_position = 0
    n_block_cash = 0
    n_block_spread_fee = 0
    n_block_missing_prices = 0
    n_opened = 0

    for pos, (idx, row) in enumerate(indicators.iterrows()):
        n_bars += 1
        # Filtro: distancia mínima entre entradas
        if last_entry_idx is not None and (pos - last_entry_idx) < getattr(cfg, "min_distance_bars", 8):
            n_skip_min_distance += 1
            continue
        price_row = df_prices.iloc[pos]
        ts_raw = row.get("timestamp")
        ts = pd.NaT
        if ts_raw is not None:
            try:
                ts = pd.to_datetime(ts_raw, utc=True)
            except Exception:
                ts = pd.NaT

        # Exit management
        if open_trade is not None:
            side = open_trade["side"]
            entry_price = open_trade["entry_price"]
            stop_price = open_trade["stop_price"]
            take_price = open_trade["take_price"]
            highest = open_trade.get("best_high", entry_price)
            lowest = open_trade.get("best_low", entry_price)
            high = _safe_float(price_row.get("high", price_row.get("close")), default=np.nan)
            low = _safe_float(price_row.get("low", price_row.get("close")), default=np.nan)
            close_price = _safe_float(price_row.get("close", entry_price), default=np.nan)
            if np.isnan(high):
                high = close_price
            if np.isnan(low):
                low = close_price
            if np.isnan(close_price):
                close_price = entry_price

            if side == "long":
                highest = max(highest, high)
                open_trade["best_high"] = highest
                lowest = min(lowest, low)
                open_trade["best_low"] = lowest
                if use_trailing and highest - entry_price >= open_trade["risk_abs"]:
                    stop_price = max(stop_price, entry_price)
                    stop_price = max(stop_price, highest - open_trade["risk_abs"])
                    stop_price = _round_price(stop_price, tick)
                exit_reason = None
                exit_price = None
                if low <= stop_price:
                    exit_reason = "stop_loss_atr"
                    exit_price = stop_price
                elif high >= take_price:
                    exit_reason = "take_profit_atr"
                    exit_price = take_price
                elif pos - open_trade["entry_index"] >= max_duracion:
                    exit_reason = "time_exit"
                    exit_price = close_price
                if exit_price is not None:
                    gross = exit_price - entry_price
                    fees = (entry_price + exit_price) * fee_rate
                    slippage_cost = (entry_price + exit_price) * slip_rate
                    net = gross - fees - slippage_cost
                    risk_abs = open_trade["risk_abs"] if open_trade["risk_abs"] > 0 else np.nan
                    mfe_abs = max(0.0, highest - entry_price)
                    mae_abs = max(0.0, entry_price - lowest)
                    mfe_r = (mfe_abs / risk_abs) if risk_abs and not np.isnan(risk_abs) else np.nan
                    mae_r = (mae_abs / risk_abs) if risk_abs and not np.isnan(risk_abs) else np.nan
                    if mae_abs <= 0:
                        mfe_mae_ratio = float("inf")
                    else:
                        try:
                            mfe_mae_ratio = float(mfe_abs / mae_abs)
                        except Exception:
                            mfe_mae_ratio = float("nan")
                    guardrail_fail_reason: Optional[str] = None
                    if min_mfe_ratio is not None and math.isfinite(min_mfe_ratio):
                        ratio_eval = mfe_mae_ratio
                        if not math.isfinite(ratio_eval):
                            ratio_eval = float("inf")
                        if ratio_eval < min_mfe_ratio:
                            guardrail_fail_reason = "mfe_mae_ratio"
                    if guardrail_fail_reason:
                        guardrail_stats[guardrail_fail_reason] += 1
                        resultados.append({
                            "tipo": "guardrail_skip",
                            "precio": exit_price,
                            "indice": int(pos),
                            "timestamp": ts.isoformat() if pd.notna(ts) else None,
                            "signal": guardrail_fail_reason,
                            "market_regime": row.get("market_regime"),
                            "symbol": open_trade.get("symbol"),
                            "mfe": mfe_abs,
                            "mae": mae_abs,
                            "mfe_mae_ratio": mfe_mae_ratio,
                        })
                        open_trade = None
                        cooldown = cfg.cooldown_bars
                        continue
                    trades.append({
                        "side": side,
                        "entry_time": open_trade["entry_time"],
                        "exit_time": ts,
                        "entry_index": open_trade["entry_index"],
                        "exit_index": pos,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "gross_pnl": gross,
                        "net_pnl": net,
                        "fee_paid": fees,
                        "slippage_cost": slippage_cost,
                        "atr_entry": open_trade["atr_entry"],
                        "atr_pct_entry": open_trade["atr_pct_entry"],
                        "bbw_pct_entry": open_trade["bbw_pct_entry"],
                        "stop_price": stop_price,
                        "take_price": take_price,
                        "risk_abs": open_trade["risk_abs"],
                        "r_multiple": gross / risk_abs if risk_abs and not np.isnan(risk_abs) else np.nan,
                        "r_multiple_net": net / risk_abs if risk_abs and not np.isnan(risk_abs) else np.nan,
                        "mfe_abs": mfe_abs,
                        "mae_abs": mae_abs,
                        "mfe_r": mfe_r,
                        "mae_r": mae_r,
                        "mfe_mae_ratio": mfe_mae_ratio,
                        "tp_price": take_price,
                        "sl_price": stop_price,
                        "regime_entry": open_trade["regime"],
                        "regime_exit": row.get("market_regime"),
                        "rsi_entry": open_trade["rsi"],
                        "adx_entry": open_trade["adx"],
                        "votes_entry": open_trade["votes"],
                        "exit_reason": exit_reason,
                        "symbol": open_trade.get("symbol"),
                    })
                    resultados.append({
                        "tipo": "venta",
                        "precio": exit_price,
                        "indice": int(pos),
                        "timestamp": ts.isoformat() if pd.notna(ts) else None,
                        "ganancia": net,
                        "duracion": pos - open_trade["entry_index"],
                        "tipo_mercado": row.get("market_regime"),
                        "signal": exit_reason,
                        "market_regime": row.get("market_regime"),
                        "symbol": open_trade.get("symbol"),
                        "mfe": mfe_abs,
                        "mae": mae_abs,
                        "mfe_mae_ratio": mfe_mae_ratio,
                    })
                    open_trade = None
                    cooldown = cfg.cooldown_bars
            # short side not yet soportado

        if open_trade is not None:
            continue

        if cooldown > 0:
            cooldown -= 1
            continue

        if pd.isna(ts):
            continue

        day_key = ts.normalize()
        if cfg.max_trades_per_day and trades_per_day[day_key] >= cfg.max_trades_per_day:
            continue

        # Instrumentación: evaluar estrategia_compra si posible
        try:
            from src.core.estrategias_bot1 import estrategia_compra
            # Verificar si acepta debug
            import inspect
            params = inspect.signature(estrategia_compra).parameters
            if "debug" in params:
                ret = estrategia_compra(row, debug=True)
                if isinstance(ret, tuple) and len(ret) == 3:
                    ok, used, dbg_estrat = ret
                    if ok:
                        n_buy_true += 1
                    else:
                        n_buy_false += 1
                    # Loguear cada 500 barras
                    if n_bars % 500 == 0:
                        logger.debug(f"estrategia_compra used={used} dbg={dbg_estrat}")
                elif isinstance(ret, tuple) and len(ret) == 2:
                    ok, used = ret
                    if ok:
                        n_buy_true += 1
                    else:
                        n_buy_false += 1
                elif isinstance(ret, bool):
                    if ret:
                        n_buy_true += 1
                    else:
                        n_buy_false += 1
            else:
                ret = estrategia_compra(row)
                if isinstance(ret, tuple) and len(ret) >= 1:
                    ok = ret[0]
                    if ok:
                        n_buy_true += 1
                    else:
                        n_buy_false += 1
                elif isinstance(ret, bool):
                    if ret:
                        n_buy_true += 1
                    else:
                        n_buy_false += 1
        except Exception as e:
            n_exception_buy += 1
            if n_bars % 500 == 0:
                logger.debug(f"Exception in estrategia_compra: {e}")

        allowed, dbg = _entry_signal(row, cfg, side="long", cooldown_ok=True)
        if not allowed:
            continue

        # === GUARDRAILS BETA A2 ===
        # 1. Verificar tolerancia de barras
        if not _check_bar_tolerance(cfg, df_prices, pos):
            guardrail_stats["bar_tolerance_fail"] += 1
            continue

        # 2. Verificar tolerancia RSI
        if not _check_rsi_tolerance(cfg, indicators, pos):
            guardrail_stats["rsi_tolerance_fail"] += 1
            continue

        # 3. Verificar admisión condicional
        allow_buy, allow_sell = _check_admission_mode(cfg, indicators, pos)
        if not allow_buy:  # Solo evaluando long por ahora
            guardrail_stats["admission_mode_fail"] += 1
            continue

        # 4. Verificar votos neutrales mínimos
        if not _check_neutral_votes_guardrail(cfg, indicators, pos):
            guardrail_stats["neutral_votes_fail"] += 1
            continue

        # 5. Verificar proximidad estricta
        regime_signal = str(dbg.get("regime", "neutral") or "neutral")
        if not _check_strict_proximity_guardrail(cfg, last_signal_idx, pos, regime_signal):
            guardrail_stats["strict_proximity_fail"] += 1
            continue

        # === CONTINUAR CON LÓGICA EXISTENTE ===
        if strict_limit > 0:
            prev_idx = last_signal_idx.get(regime_signal)
            if prev_idx is not None and (pos - prev_idx) > strict_limit:
                last_signal_idx[regime_signal] = pos
                continue
            last_signal_idx[regime_signal] = pos
        else:
            last_signal_idx[regime_signal] = pos

        # --- Instrumentación de bloqueos de apertura ---
        blocked = False
        # 1. Ya hay posición abierta
        if open_trade is not None:
            n_block_in_position += 1
            blocked = True
        # 2. Sin capital (simulado: size 0, no implementado aquí, placeholder)
        # if size == 0:
        #     n_block_cash += 1
        #     blocked = True
        # 3. Fees/slippage (placeholder, no implementado)
        # if fee_rate > 0.5 or slip_rate > 0.5:
        #     n_block_spread_fee += 1
        #     blocked = True
        # 4. Precios faltantes
        entry_price = _safe_float(price_row.get("close"), default=np.nan)
        if np.isnan(entry_price):
            n_block_missing_prices += 1
            blocked = True
        atr_val = _safe_float(row.get("ATR"), default=np.nan)
        if pd.isna(atr_val) or atr_val <= 0:
            n_block_missing_prices += 1
            blocked = True
        if blocked:
            continue
        # --- Fin instrumentación bloqueos ---
        sl_mult, tp_mult = _resolve_tp_sl(cfg, dbg.get("regime", "neutral"))
        risk_abs = max(sl_mult * atr_val, 1e-8)
        stop_price = _round_price(entry_price - risk_abs, tick)
        take_price = _round_price(entry_price + tp_mult * atr_val, tick)

        # Si se abre un trade, actualizar last_entry_idx
        last_entry_idx = pos
        symbol = row.get("symbol")
        if symbol is None and isinstance(price_row, pd.Series):
            symbol = price_row.get("symbol")

        open_trade = {
            "side": "long",
            "entry_index": pos,
            "entry_time": ts,
            "entry_price": entry_price,
            "atr_entry": atr_val,
            "atr_pct_entry": dbg.get("atr_pct"),
            "bbw_pct_entry": dbg.get("bbw_pct"),
            "votes": dbg.get("votes"),
            "adx": dbg.get("adx"),
            "rsi": dbg.get("rsi"),
            "regime": dbg.get("regime"),
            "risk_abs": risk_abs,
            "stop_price": stop_price,
            "take_price": take_price,
            "best_high": entry_price,
            "best_low": entry_price,
            "symbol": symbol,
        }
        trades_per_day[day_key] += 1
        n_opened += 1

        resultados.append({
            "tipo": "compra",
            "precio": entry_price,
            "indice": int(pos),
            "timestamp": ts.isoformat() if pd.notna(ts) else None,
            "indicadores_usados": ["RSI", "ADX", "ATR_pct", "BBW_pct"],
            "rsi": dbg.get("rsi"),
            "adx": dbg.get("adx"),
            "votes": dbg.get("votes"),
            "atr_pct": dbg.get("atr_pct"),
            "bbw_pct": dbg.get("bbw_pct"),
            "signal": "compra",
            "market_regime": dbg.get("regime"),
            "symbol": symbol,
            "tp_price": take_price,
            "sl_price": stop_price,
        })

    trades_df = pd.DataFrame(trades)
    try:
        setattr(cfg, "_guardrail_stats", dict(guardrail_stats))
    except Exception:
        pass
    # Instrumentación final
    logger.info(f"Resumen instrumentación: bars={n_bars}, buy_true={n_buy_true}, buy_false={n_buy_false}, skip_min_distance={n_skip_min_distance}, exceptions={n_exception_buy}, opened={n_opened}, block_in_position={n_block_in_position}, block_cash={n_block_cash}, block_spread_fee={n_block_spread_fee}, block_missing_prices={n_block_missing_prices}")
    return resultados, trades_df


# ------------------------------------------------------------------
# Legacy engine wrapper (placeholder). Replace with project engine.
# ------------------------------------------------------------------

def backtesting(df: pd.DataFrame, cfg: Optional[BTConfig] = None, params: Optional[Dict[str, Any]] = None):
    """Stable wrapper used by institutional scripts. Delegates to backtesting_legacy.
    Returns (resultados, resumen, trades_enriched) when available.
    """
    return backtesting_legacy(df, config_obj=cfg or BTConfig())



def backtesting_legacy(df: pd.DataFrame, config_obj: Optional[BTConfig] = None, writer: Any = None):

    """Institutional engine: calculates indicators, applies gating/regime/votes, and simulates trades."""
    cfg = config_obj or BTConfig()
    df_clean = limpiar_ohlcv(df)
    if df_clean is None or df_clean.empty:
        resumen_vacio = {
            "profit_factor": 0.0,
            "winrate": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "trades": 0,
        }
        return [], resumen_vacio, []

    prices = df_clean.reset_index(drop=True)
    indicators = pd.DataFrame()

    if calcular_todos_los_indicadores is not None:
        try:
            calc_res = calcular_todos_los_indicadores(prices, export_snapshot=False, snapshot_prefix="bt_legacy")
            indicators = pd.DataFrame(calc_res)
        except Exception:
            logger.debug("calcular_todos_los_indicadores fallo; usando fallback", exc_info=True)
            indicators = pd.DataFrame()

    if indicators.empty:
        indicators = _fallback_indicators(prices)
    else:
        indicators = indicators.reset_index(drop=True)
        if len(indicators) != len(prices):
            indicators = indicators.reindex(range(len(prices))).reset_index(drop=True)
        fallback = _fallback_indicators(prices)
        for col in ("RSI", "ADX", "ATR", "BB_Width", "hist", "market_regime"):
            if col not in indicators.columns or pd.to_numeric(indicators[col], errors="coerce").isna().all():
                if col in fallback.columns:
                    indicators[col] = fallback[col]
                else:
                    indicators[col] = np.nan

    prices = prices.reset_index(drop=True)
    for base_col in prices.columns:
        indicators[base_col] = prices[base_col]

    indicators = _ensure_percentiles(indicators)

    if "market_regime" not in indicators.columns:
        indicators["market_regime"] = indicators.apply(_classify_regime, axis=1)
    else:
        mask = indicators["market_regime"].isna()
        if mask.any():
            indicators.loc[mask, "market_regime"] = indicators.loc[mask].apply(_classify_regime, axis=1)

    price_cols = [c for c in ("timestamp", "open", "high", "low", "close", "volume", "symbol") if c in indicators.columns]
    if not {"open", "high", "low", "close"}.issubset(price_cols):
        price_cols = [c for c in ("timestamp", "open", "high", "low", "close", "volume", "symbol") if c in prices.columns]
        price_frame = prices[price_cols].copy()
    else:
        price_frame = indicators[price_cols].copy()

    indicadores_frame = indicators.reset_index(drop=True)
    price_frame = price_frame.reset_index(drop=True)

    resultados, trades_df = _simulate_trades(price_frame, indicadores_frame, cfg)
    trades_enriched = trades_df.to_dict(orient="records")

    pnl = pd.to_numeric(trades_df.get("net_pnl", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    n_trades = int(len(pnl))
    if n_trades > 0:
        gains = pnl[pnl > 0].sum()
        losses = -pnl[pnl < 0].sum()
        if losses > 0:
            profit_factor = float(gains / losses)
        else:
            profit_factor = float("inf") if gains > 0 else 0.0
        expectancy = float(pnl.mean())
        equity = pnl.cumsum()
        dd = equity - equity.cummax()
        max_drawdown = float(dd.min()) if not dd.empty else 0.0
        winrate = float((pnl > 0).mean() * 100.0)
    else:
        profit_factor = 0.0
        expectancy = 0.0
        max_drawdown = 0.0
        winrate = 0.0

    resumen: Dict[str, Any] = {
        "profit_factor": profit_factor,
        "winrate": winrate,
        "expectancy": expectancy,
        "max_drawdown": max_drawdown,
        "trades": n_trades,
    }

    if compute_advanced_metrics is not None and not trades_df.empty:
        try:
            adv_metrics = compute_advanced_metrics(trades_df)
            resumen["advanced_metrics"] = adv_metrics
            resumen.setdefault("profit_factor", adv_metrics.get("pf_net", profit_factor))
            resumen.setdefault("expectancy", adv_metrics.get("expectancy", expectancy))
            resumen.setdefault("max_drawdown", adv_metrics.get("max_dd", max_drawdown))
        except Exception:
            logger.debug("compute_advanced_metrics fallo; se continúa con resumen básico", exc_info=True)

    guardrails_status: Dict[str, bool] = {}
    guardrails_cfg = getattr(cfg, "guardrails", {}) if isinstance(getattr(cfg, "guardrails", {}), dict) else {}
    if guardrails_cfg:
        metrics_pf = resumen.get("advanced_metrics", {}).get("pf_net", resumen.get("profit_factor"))
        min_pf_net = guardrails_cfg.get("min_pf_net")
        if min_pf_net is not None:
            try:
                guardrails_status["min_pf_net"] = float(metrics_pf) >= float(min_pf_net)
            except Exception:
                guardrails_status["min_pf_net"] = False

        max_dd_pct = guardrails_cfg.get("max_dd_pct")
        if max_dd_pct is not None and cfg.starting_capital:
            try:
                dd_pct = abs(float(resumen.get("max_drawdown", 0.0))) / float(cfg.starting_capital)
            except Exception:
                dd_pct = float("inf")
            resumen.setdefault("max_drawdown_pct", dd_pct)
            try:
                guardrails_status["max_dd_pct"] = dd_pct <= float(max_dd_pct)
            except Exception:
                guardrails_status["max_dd_pct"] = False

        max_fees_pct = guardrails_cfg.get("max_fees_pct")
        if max_fees_pct is not None and not trades_df.empty:
            fees_series = pd.to_numeric(trades_df.get("fee_paid", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
            entry_abs = pd.to_numeric(trades_df.get("entry_price", pd.Series(dtype=float)), errors="coerce").abs()
            exit_abs = pd.to_numeric(trades_df.get("exit_price", pd.Series(dtype=float)), errors="coerce").abs()
            notionals_sum = float((entry_abs + exit_abs).sum())
            fees_total = float(fees_series.sum())
            fees_pct = (fees_total / notionals_sum) if notionals_sum > 0 else 0.0
            resumen.setdefault("fees_pct", fees_pct)
            try:
                guardrails_status["max_fees_pct"] = fees_pct <= float(max_fees_pct)
            except Exception:
                guardrails_status["max_fees_pct"] = False

        min_trades_total = guardrails_cfg.get("min_trades_total")
        if min_trades_total is not None:
            try:
                guardrails_status["min_trades_total"] = n_trades >= int(min_trades_total)
            except Exception:
                guardrails_status["min_trades_total"] = False

    resumen["guardrails_status"] = guardrails_status
    resumen["guardrails_passed"] = all(guardrails_status.values()) if guardrails_status else True

    trade_guardrails = getattr(cfg, "_guardrail_stats", None)
    if trade_guardrails:
        resumen["trade_guardrails"] = trade_guardrails

    if writer is not None:
        try:
            writer.write(resumen)
        except Exception:
            logger.debug("Writer proporcionado no soporta write", exc_info=True)

    return resultados, resumen, trades_enriched


# ------------------------------------------------------------------
# Persistence helpers used by other scripts
# ------------------------------------------------------------------

def guardar_resultados_por_par(
    symbol: str,
    periodo_label: str,
    resultados: List[dict],
    resumen: Dict[str, Any],
    starting_capital: Optional[float] = None,
    run_dir: Optional[str] = None,
    trades_enriched: Optional[List[dict]] = None,
):
    out_dir = os.path.join(run_dir or os.path.join("data", "backtesting"), symbol)
    os.makedirs(out_dir, exist_ok=True)

    df = pd.DataFrame(resultados)
    resultados_file = os.path.join(out_dir, f"resultados_{symbol}_{periodo_label}.csv")
    df.to_csv(resultados_file, index=False)

    # Equity simple basado en ganancia si existe
    if "ganancia" in df.columns:
        pnl = pd.to_numeric(df["ganancia"], errors="coerce").fillna(0.0)
        start_cap = float(starting_capital or 100.0)
        equity = start_cap + pnl.cumsum()
        df["equity"] = equity
    df.to_csv(os.path.join(out_dir, f"resultados_{symbol}_{periodo_label}_with_equity.csv"), index=False)

    # Resumen JSON/CSV
    resumen_file = os.path.join(out_dir, f"resumen_{symbol}_{periodo_label}.json")
    with open(resumen_file, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, indent=2, ensure_ascii=False)
    pd.DataFrame([resumen]).to_csv(os.path.join(out_dir, f"resumen_{symbol}_{periodo_label}.csv"), index=False)

    # Trades enriched if provided (compute net metrics preferentially)
    if trades_enriched:
        te = pd.DataFrame(trades_enriched)
        te.to_csv(os.path.join(out_dir, f"trades_enriched_{symbol}_{periodo_label}.csv"), index=False)
        try:
            s = pd.to_numeric(te.get("net_pnl", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
            eq = s.cumsum()
            dd = (eq.cummax() - eq)
            pos = s[s > 0].sum()
            neg = s[s <= 0].sum()
            pf = (pos / abs(neg)) if neg < 0 else (float("inf") if pos > 0 else 0.0)
            metrics_net = {
                "symbol": symbol,
                "periodo": periodo_label,
                "trades": int(len(s)),
                "pf_net": float(pf if np.isfinite(pf) else 0.0),
                "expectancy_net": float(s.mean()),
                "max_dd_net": float(dd.max() if not dd.empty else 0.0),
                "winrate_net": float((s > 0).mean() * 100.0) if len(s) else 0.0,
            }
            pd.DataFrame([metrics_net]).to_csv(os.path.join(out_dir, f"metrics_net_{symbol}_{periodo_label}.csv"), index=False)
        except Exception:
            pass

    return {
        "resultados_file": resultados_file,
        "resumen_json": resumen_file,
        "resumen_csv": os.path.join(out_dir, f"resumen_{symbol}_{periodo_label}.csv"),
    }


# ------------------------------------------------------------------
# CLI: multi-symbol backtest without hardcoded 30-day cut
# ------------------------------------------------------------------


def _slice_df_by_period(df_full: pd.DataFrame, days: int = 0, months: int = 0) -> Tuple[pd.DataFrame, str]:
    if df_full is None or df_full.empty:
        return pd.DataFrame(), "empty"
    ts = pd.to_datetime(df_full["timestamp"], utc=True, errors="coerce")
    df_full = df_full.loc[~ts.isna()].reset_index(drop=True)
    ts = pd.to_datetime(df_full["timestamp"], utc=True)
    end = ts.max()
    if days and days > 0:
        cutoff = end - pd.Timedelta(days=int(days))
        return df_full.loc[ts >= cutoff].reset_index(drop=True), f"{int(days)}d"
    if months and months > 0:
        cutoff = end - DateOffset(months=int(months))
        return df_full.loc[ts >= cutoff].reset_index(drop=True), f"{int(months)}m"
    return df_full.reset_index(drop=True), "full"



def _run_cli():
    import argparse as _argparse
    ap = _argparse.ArgumentParser(description="Backtesting engine (multi-symbol)")
    ap.add_argument("--symbols", type=str, default="BTCUSDT,ETHUSDT,BNBUSDT,WLDUSDT", help="Lista separada por comas")
    ap.add_argument("--months", type=int, default=12, help="Meses a retroceder (0=todo)")
    ap.add_argument("--days", type=int, default=0, help="Días a retroceder (prioriza sobre months si >0)")
    ap.add_argument("--master", type=str, default="", help="Ruta CSV maestro; si vacío, autodetecta")
    args = ap.parse_args()

    # run dir
    base_bt_dir = os.path.join("data", "backtesting")
    os.makedirs(base_bt_dir, exist_ok=True)
    run_stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
    run_dir = os.path.join(base_bt_dir, run_stamp)
    os.makedirs(run_dir, exist_ok=True)
    os.environ["BACKTEST_RUN_DIR"] = run_dir


    # maestro
    master_env = os.environ.get("BACKTEST_MASTER_FILE")
    master_15m = os.path.join("data", "historiales", "historial_trading_maestro_15m.csv")
    master_alt = os.path.join("data", "historiales", "historial_trading_limpio.csv")
    master = args.master or (master_env if (master_env and os.path.exists(master_env)) else (master_15m if os.path.exists(master_15m) else master_alt))
    logger.info("Usando maestro: %s", master)

    # Cargar config institucional y congelar parámetros
    institucional_cfg = None
    if get_institucional_config is not None:
        try:
            institucional_cfg = get_institucional_config()
            logger.info("Config institucional cargado (versión %s)", institucional_cfg.version)
            if freeze_params is not None:
                freeze_params(run_dir, institucional_cfg)
        except Exception as e:
            logger.warning(f"No se pudo cargar config institucional: {e}")

    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    for symbol in symbols:
        # Seleccionar perfil ganador (A2) y parámetros institucionales
        cfg_obj = BTConfig()
        if institucional_cfg is not None and symbol in institucional_cfg.symbols:
            sym_cfg = institucional_cfg.symbols[symbol]
            # allowed_hours, allowed_regimes, min_atr_pct, min_bbw_pct, max_trades_per_day
            filters = sym_cfg.filters or {}
            cfg_obj.allowed_hours = filters.get("allowed_hours")
            cfg_obj.allowed_regimes = filters.get("allowed_regimes")
            cfg_obj.min_atr_pct = float(filters.get("min_atr_pct", 0.22))
            cfg_obj.min_bbw_pct = float(filters.get("min_bbw_pct", 0.15))
            cfg_obj.max_trades_per_day = int(filters.get("max_trades_per_day", 6))
            # execution: fee_bps, slippage_bps
            exec_cfg = sym_cfg.execution or {}
            for k in ["fee_bps", "slippage_bps"]:
                if hasattr(cfg_obj, k):
                    setattr(cfg_obj, k, exec_cfg.get(k, getattr(cfg_obj, k, None)))
        try:
            df_full = cargar_y_combinar_datos(master, client=None, symbol=symbol, meses=0)
        except Exception as e:
            logger.error("Error cargando histórico %s: %s", symbol, e)
            continue
        if df_full is None or df_full.empty:
            logger.warning("Sin datos para %s", symbol)
            continue
        df_slice, period_label = _slice_df_by_period(df_full, days=args.days, months=args.months)
        df_slice = limpiar_ohlcv(df_slice)
        if df_slice.empty:
            logger.warning("Sin datos tras limpieza para %s (%s)", symbol, period_label)
            continue
        logger.info(
            "Procesando %s — ventana %s: %s → %s (%d filas)",
            symbol,
            period_label,
            pd.to_datetime(df_slice["timestamp"]).min(),
            pd.to_datetime(df_slice["timestamp"]).max(),
            len(df_slice),
        )
        bt_res: Any = backtesting_legacy(df_slice, config_obj=cfg_obj)
        if isinstance(bt_res, tuple) and len(bt_res) == 3:
            resultados, resumen, trades_enriched = bt_res
        else:
            resultados, resumen = bt_res
            trades_enriched = []
        guardar_resultados_por_par(
            symbol,
            period_label,
            resultados,
            resumen,
            starting_capital=100.0,
            run_dir=run_dir,
            trades_enriched=trades_enriched,
        )

    # summary.csv (best-effort)
    try:
        rows: List[Dict[str, Any]] = []
        label = "full" if args.days == 0 and args.months == 0 else (f"{args.days}d" if args.days > 0 else f"{args.months}m")
        for sym in symbols:
            path = os.path.join(run_dir, sym, f"resumen_{sym}_{label}.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    r = json.load(fh)
                r["symbol"] = sym
                rows.append(r)
        if rows:
            pd.DataFrame(rows).to_csv(os.path.join(run_dir, "summary.csv"), index=False)
    except Exception:
        pass

    logger.info("Run completado. Carpeta: %s", run_dir)


# ------------------------------------------------------------------
# Integración Beta A2: Configuración institucional
# ------------------------------------------------------------------

def configure_from_institucional(yaml_path: str, symbol: str = "BTCUSDT", perfil: str = "conservador") -> BTConfig:
    """
    Configura BTConfig desde configuración institucional YAML con soporte Beta A2 completo.
    
    Args:
        yaml_path: Ruta al archivo config/institucional.yaml
        symbol: Símbolo para configurar (ej: "BTCUSDT")
        perfil: Perfil TP/SL ("conservador" o "agresivo")
    
    Returns:
        BTConfig configurado con guardrails Beta A2 y TP/SL dinámico
    """
    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Error cargando configuración institucional {yaml_path}: {e}")
        return BTConfig()
    
    # Configuración base
    cfg = BTConfig()
    
    # Defaults generales
    defaults = config_data.get("defaults", {})
    cfg.min_atr_pct = defaults.get("min_atr_pct", 0.22)
    cfg.min_bbw_pct = defaults.get("min_bbw_pct", 0.15)
    cfg.fee_bps = defaults.get("fees", {}).get("spot_fee_bps", 8.0)
    cfg.exclude_hours = defaults.get("exclude_hours", [])
    
    # Configuración Beta A2 específica
    cfg.strict_proximity_bars = defaults.get("strict_proximity", 2)
    cfg.bar_tolerance = defaults.get("bar_tolerance", 6)
    cfg.rsi_tolerance = defaults.get("rsi_tolerance", 2.0)
    cfg.admission_mode = defaults.get("admission", "conditional")
    cfg.neutral_min_votes = defaults.get("neutral_min_votes", 4)
    
    # Guardrails institucionales
    guardrails_cfg = config_data.get("guardrails", {})
    cfg.min_pf_net = guardrails_cfg.get("min_pf_net")
    cfg.max_dd_pct = guardrails_cfg.get("max_dd_pct")
    cfg.min_mfe_mae_ratio = guardrails_cfg.get("min_mfe_mae_ratio")
    cfg.guardrails = guardrails_cfg
    
    # TP/SL por régimen (Beta A2 dinámico)
    tp_sl_profiles = config_data.get("tp_sl_profiles", {})
    if perfil in tp_sl_profiles:
        cfg.tp_sl_by_regime = tp_sl_profiles[perfil]
        cfg.perfil_tp_sl = perfil
        logger.info(f"Configurado perfil TP/SL '{perfil}' con {len(cfg.tp_sl_by_regime)} regímenes")
    
    # Configuración por símbolo
    symbols_cfg = config_data.get("symbols", {})
    if symbol in symbols_cfg:
        symbol_config = symbols_cfg[symbol]
        cfg.tick_size = symbol_config.get("tick_size", cfg.tick_size)
        cfg.max_trades_per_day = symbol_config.get("max_trades_per_day", cfg.max_trades_per_day)
        
        # Override con configuración específica del símbolo si existe
        if "min_atr_pct" in symbol_config:
            cfg.min_atr_pct = symbol_config["min_atr_pct"]
        if "min_bbw_pct" in symbol_config:
            cfg.min_bbw_pct = symbol_config["min_bbw_pct"]
    
    cfg.symbol = symbol
    cfg.debug_counters = True  # Habilitar para auditoría Beta A2
    cfg.enforce_net_metrics = True
    
    logger.info(f"BTConfig configurado para {symbol} con perfil {perfil}")
    logger.debug(f"Guardrails activos: proximity={cfg.strict_proximity_bars}, mfe_mae={cfg.min_mfe_mae_ratio}")
    
    return cfg


def load_institucional_config(yaml_path: str = "config/institucional.yaml") -> Dict[str, Any]:
    """
    Carga configuración institucional YAML para inspección.
    
    Args:
        yaml_path: Ruta al archivo YAML
    
    Returns:
        Diccionario con la configuración completa
    """
    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error cargando {yaml_path}: {e}")
        return {}


if __name__ == "__main__":
    _run_cli()
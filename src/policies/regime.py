from __future__ import annotations
from typing import Mapping, Any

# Preferir implementación existente para no cambiar comportamiento
def classify_regime(row: Mapping[str, Any]) -> str:
    # Try to reuse existing classification if present elsewhere
    try:
        from src.core.backtesting import classify_regime as _bk_regime  # type: ignore
        return _bk_regime(row)  # noqa
    except Exception:
        try:
            from scripts.ab_sesgo_fix import classify_regime as _ab_regime  # type: ignore
            return _ab_regime(row)  # noqa
        except Exception:
            pass
    # Fallback simple y estable
    adx = float(row.get("ADX", 0) or 0)
    bbw_pct = float(row.get("BBW_pct", 0) or 0)
    rsi = float(row.get("RSI", 50) or 50)
    if adx >= 25 and bbw_pct >= 0.5:
        return "trend"
    if bbw_pct < 0.25:
        return "low_vol"
    if 45 <= rsi <= 55:
        return "neutral"
    return "range"

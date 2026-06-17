from __future__ import annotations
from typing import Iterable, List, Set, Dict, Any
import datetime as _dt


def _parse_hour_range(r: str) -> Set[int]:
    # "HH:MM-HH:MM" -> set of hour ints covered (1h blocks)
    try:
        a, b = r.split("-")
        h1 = int(a.split(":")[0])
        h2 = int(b.split(":")[0])
    except Exception:
        return set()
    hours = set()
    for h in range(h1, (h2 % 24) or 24):
        hours.add(h % 24)
        if (h + 1) % 24 == h2 % 24:
            break
    return hours


def normalize_hours(exclude_hours: List[str] | None) -> List[str] | None:
    if not exclude_hours:
        return None
    excluded: Set[int] = set()
    for r in exclude_hours:
        excluded |= _parse_hour_range(str(r))
    allowed = [h for h in range(24) if h not in excluded]
    # return as "HH:00-HH:59"
    return [f"{h:02d}:00-{h:02d}:59" for h in sorted(allowed)]


def _allowed_to_ints(allowed_hours: Iterable[str | int] | None) -> Set[int] | None:
    if allowed_hours is None:
        return None
    out: Set[int] = set()
    for item in allowed_hours:
        if isinstance(item, int):
            out.add(item % 24)
        else:
            try:
                a, b = str(item).split("-")
                out.add(int(a.split(":")[0]) % 24)
            except Exception:
                continue
    return out


def should_trade(context: Dict[str, Any]) -> bool:
    """
    context keys expected (robust to missing):
      - ts: pd.Timestamp | datetime | str
      - allowed_hours: list[int] | list["HH:MM-HH:MM"] | None
      - atr_pct: float | None
      - bbw_pct: float | None
      - atr_min_percentile: float | None
      - bbw_min_percentile: float | None
      - regime: str | None
      - allowed_regimes: list[str] | None
    """
    ts = context.get("ts")
    hour = None
    try:
        if hasattr(ts, "hour"):
            hour = int(ts.hour)
        else:
            hour = _dt.datetime.fromisoformat(str(ts)).hour
    except Exception:
        hour = None

    allowed_hours = _allowed_to_ints(context.get("allowed_hours"))
    if allowed_hours is not None and hour is not None and hour not in allowed_hours:
        return False

    atr_pct = context.get("atr_pct")
    bbw_pct = context.get("bbw_pct")
    atr_min = context.get("atr_min_percentile")
    bbw_min = context.get("bbw_min_percentile")
    if atr_min is not None and atr_pct is not None and atr_pct < float(atr_min):
        return False
    if bbw_min is not None and bbw_pct is not None and bbw_pct < float(bbw_min):
        return False

    regime = (context.get("regime") or "").strip()
    allowed_regimes = context.get("allowed_regimes")
    if allowed_regimes and regime and regime not in set(allowed_regimes):
        return False

    return True

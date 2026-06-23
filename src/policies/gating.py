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


def passes_edge_filter(
    atr_pct: float | None,
    tp_mult: float | None,
    fee_bps: float | None = 8.0,
    slippage_bps: float | None = 5.0,
    min_edge_mult: float | None = 1.5,
) -> bool:
    """
    Filtro de edge neto: rechaza trades cuyo take-profit esperado no cubre el
    costo de ida y vuelta (round-trip) multiplicado por un margen minimo.

    IMPORTANTE - unidades:
      - `atr_pct` viene en ESCALA PORCENTUAL (p. ej. 0.30 == 0.30%), consistente
        con `min_atr_pct=0.22` usado en backtesting. Se normaliza a fraccion
        dividiendo por 100 antes de comparar contra los costos.
      - `fee_bps` y `slippage_bps` estan en basis points (1 bps = 0.01%).

    tp_esperado_frac = tp_mult * (atr_pct / 100)
    costo_rt_frac    = (fee_bps + slippage_bps) / 10_000 * 2   # entrada + salida

    Devuelve True si el trade tiene edge suficiente (o si faltan datos para
    evaluarlo, en cuyo caso NO bloquea: fail-open para no romper el flujo).
    """
    try:
        tp_m = float(tp_mult) if tp_mult is not None else 0.0
        atr_p = float(atr_pct) if atr_pct is not None else 0.0
    except (TypeError, ValueError):
        return True  # datos no numericos: no bloquear

    # Sin datos suficientes para evaluar el edge -> no bloquear.
    if tp_m <= 0.0 or atr_p <= 0.0:
        return True

    fee = float(fee_bps) if fee_bps is not None else 0.0
    slip = float(slippage_bps) if slippage_bps is not None else 0.0
    edge_mult = float(min_edge_mult) if min_edge_mult is not None else 1.5

    tp_expected_frac = tp_m * (atr_p / 100.0)
    cost_rt_frac = (fee + slip) / 10_000.0 * 2.0

    return tp_expected_frac >= cost_rt_frac * edge_mult


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

    # Filtro de edge neto (costos). Solo se evalua si el context trae tp_mult y
    # atr_pct; en caso contrario passes_edge_filter devuelve True (fail-open) y
    # el comportamiento previo se mantiene intacto.
    if not passes_edge_filter(
        atr_pct=context.get("atr_pct"),
        tp_mult=context.get("tp_mult"),
        fee_bps=context.get("fee_bps", 8.0),
        slippage_bps=context.get("slippage_bps", 5.0),
        min_edge_mult=context.get("min_edge_mult", 1.5),
    ):
        return False

    return True

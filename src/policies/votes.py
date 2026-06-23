from __future__ import annotations
from typing import Mapping, Sequence, Any, Optional


def compute_votes(row: Mapping[str, Any], side: str = "long", signal_cols: Optional[Sequence[str]] = None) -> int:
    """
    Suma señales booleanas como votos. Si no se especifican columnas,
    toma prefijo 'sig_' y/o columnas booleanas típicas.
    """
    if signal_cols is None:
        signal_cols = [c for c, v in row.items() if c.startswith("sig_")]
        if not signal_cols:
            # heurística mínima
            signal_cols = [c for c, v in row.items() if isinstance(v, (bool,))]

    votes = 0
    for c in signal_cols:
        try:
            v = row.get(c)
            votes += int(bool(v))
        except Exception:
            continue
    return int(votes)

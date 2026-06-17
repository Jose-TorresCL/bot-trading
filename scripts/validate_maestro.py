import sys
from pathlib import Path
import pandas as pd


def validate_master(path: Path, expected_days: int = 360, freq_min: int = 15) -> int:
    errs = []
    if not path.exists():
        print(f"[FAIL] File not found: {path}")
        return 1

    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"[FAIL] Could not read CSV: {e}")
        return 1

    required_cols = {"timestamp", "symbol"}
    missing = required_cols - set(df.columns)
    if missing:
        errs.append(f"Missing columns: {sorted(missing)}")

    # Parse timestamp
    try:
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    except Exception as e:
        errs.append(f"Timestamp parse error: {e}")
        ts = pd.Series([pd.NaT] * len(df))

    if ts.isna().any():
        n_na = int(ts.isna().sum())
        errs.append(f"Found {n_na} NaT timestamps after parsing")
    df["timestamp"] = ts

    # Basic UTC check
    if not getattr(ts.dt.tz, "key", "UTC").upper().startswith("UTC"):
        errs.append("Timestamps are not UTC (coerced to UTC during parse)")

    # Duplicate check per (symbol, timestamp)
    if {"symbol", "timestamp"}.issubset(df.columns):
        dup_mask = df.duplicated(subset=["symbol", "timestamp"], keep=False)
        n_dups = int(dup_mask.sum())
        if n_dups:
            errs.append(f"Found {n_dups} duplicated (symbol,timestamp) rows")

    # Coverage and gaps per symbol
    sym_summaries = []
    expected_freq = f"{freq_min}T"
    for sym, g in df.groupby("symbol"):
        g = g.sort_values("timestamp").dropna(subset=["timestamp"]).copy()
        if g.empty:
            sym_summaries.append((sym, 0, 0, 0, 0))
            continue
        start, end = g["timestamp"].iloc[0], g["timestamp"].iloc[-1]
        span_days = (end - start).total_seconds() / 86400.0
        # detect gaps
        gaps = (g["timestamp"].diff().dt.total_seconds() // 60 != freq_min).fillna(False).sum()
        # reindex to expected range for a stricter gap count
        full_index = pd.date_range(start=start, end=end, freq=expected_freq, tz="UTC")
        n_expected = len(full_index)
        n_rows = len(g)
        missing_bars = max(0, n_expected - n_rows)
        sym_summaries.append((sym, span_days, n_rows, gaps, missing_bars))

    # Print summary
    print("Symbol,span_days,rows,gaps,missing_bars")
    for sym, span_days, n_rows, gaps, missing_bars in sym_summaries:
        print(f"{sym},{span_days:.1f},{n_rows},{gaps},{missing_bars}")

    # Check expected days roughly (>= expected_days - 1 to allow off-by-one)
    short_syms = [s for s, d, *_ in sym_summaries if d < expected_days - 1]
    if short_syms:
        errs.append(f"Coverage < {expected_days} days for: {sorted(short_syms)}")

    # Consider small number of missing acceptable (< 0.1% of rows), else flag
    high_missing = [s for s, _, n_rows, _, miss in sym_summaries if n_rows and miss / n_rows > 0.001]
    if high_missing:
        errs.append(f"Excessive missing bars (>0.1%) for: {sorted(high_missing)}")

    if errs:
        print("\n[FAIL] Validation issues:")
        for e in errs:
            print(f"- {e}")
        return 2
    print("\n[PASS] Master 15m CSV looks consistent (UTC, ~360 days, no critical gaps/dups)")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/historiales/historial_trading_maestro_15m.csv")
    code = validate_master(path)
    sys.exit(code)

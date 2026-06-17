import argparse
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
import numpy as np

# Inputs: winners by symbol, path to Fase1_ext root
# Outputs per symbol: tp_sl_matrix.csv, trades_enriched_tp_sl.csv, delta_tp_sl.md, resumen_tecnico.md

WINNERS_DEFAULT = {
    "BTCUSDT": "A2",
    "ETHUSDT": "A2",
    "BNBUSDT": "A2",
    "WLDUSDT": "A1",  # control adverso, no institucionalizable
}

F1_EXT_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase1_ext")
OUT_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase2_tp_sl")

# Conservative TP/SL presets per regime as starting points (multiples of ATR-based R or empirical R)
REGIME_PRESETS = {
    "trend":        {"tp_R": 1.8, "sl_R": 1.0},
    "high_vol":     {"tp_R": 1.6, "sl_R": 1.1},
    "range":        {"tp_R": 1.4, "sl_R": 0.9},
    "neutral":      {"tp_R": 1.5, "sl_R": 1.0},
    "low_vol":      {"tp_R": 1.7, "sl_R": 0.9},
}

REQUIRED_COLS = [
    "symbol","side","entry_time","exit_time","net_pnl","r_multiple_net","mfe","mae","regime_entry","regime_exit"
]


def _safe_read(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def _as_num(s) -> pd.Series:
    # Accept Series, list-like, or DataFrame (pick last column)
    if isinstance(s, pd.DataFrame):
        if s.shape[1] == 0:
            return pd.Series(dtype=float)
        s = s.iloc[:, -1]
    try:
        return pd.to_numeric(s, errors="coerce")
    except Exception:
        return pd.Series(dtype=float)


def _perf_metrics(df: pd.DataFrame) -> Dict[str, float]:
    pnl = _as_num(df.get("net_pnl", pd.Series(dtype=float))).fillna(0.0)
    pf = float(pnl[pnl>0].sum() / abs(pnl[pnl<0].sum())) if (pnl[pnl<0].sum()!=0) else (float("inf") if pnl[pnl>0].sum()>0 else 0.0)
    exp = float(pnl.mean()) if len(pnl) else np.nan
    # proxy max_dd over equity curve
    eq = pnl.cumsum()
    dd = (eq - eq.cummax()).min() if not eq.empty else 0.0
    # diversity proxy: compute top regime share from trades if possible
    top_share = np.nan
    if "regime_entry" in df.columns:
        try:
            counts = df["regime_entry"].astype(str).value_counts(normalize=True)
            if counts.size:
                top_share = float(counts.max())
        except Exception:
            top_share = np.nan
    return {"pf_net": float(pf), "expectancy": exp, "max_dd": float(dd), "top_regime_share": top_share}


def _regime_distribution(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("regime_entry").agg(
        n=("net_pnl","size"),
        r_med=("r_multiple_net",lambda x: _as_num(x).median()),
        mfe_med=("mfe",lambda x: _as_num(x).median()),
        mae_med=("mae",lambda x: _as_num(x).abs().median()),
    ).reset_index().rename(columns={"regime_entry":"regime"})
    # ratio mfe/mae
    g["mfe_mae_ratio_med"] = g.apply(lambda r: (r["mfe_med"] / r["mae_med"]) if (pd.notna(r["mfe_med"]) and pd.notna(r["mae_med"]) and r["mae_med"]!=0) else np.nan, axis=1)
    return g


def _apply_tp_sl(df: pd.DataFrame, matrix: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    out = df.copy()
    # we re-score trades by clipping r_multiple_net to regime-specific tp/sl
    r = _as_num(out.get("r_multiple_net", pd.Series(dtype=float))).copy()
    # interpret R as multiples of risk; clip by tp/sl per regime
    regs_col = out.get("regime_entry")
    if regs_col is None:
        regs = pd.Series([None]*len(out))
    else:
        regs = regs_col.astype(str)
    tp_arr = regs.map(lambda rg: matrix.get(rg, {}).get("tp_R", np.nan))
    sl_arr = regs.map(lambda rg: -abs(matrix.get(rg, {}).get("sl_R", np.nan)))
    # If missing regime in matrix, do not clip
    r_adj = r.copy()
    mask_tp = pd.notna(tp_arr)
    mask_sl = pd.notna(sl_arr)
    r_adj = np.where(mask_tp & (r > tp_arr), tp_arr, r_adj)
    r_adj = np.where(mask_sl & (r_adj < sl_arr), sl_arr, r_adj)
    out["r_multiple_net_tp_sl"] = r_adj
    # scale net_pnl accordingly by ratio of R
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.where(r!=0, r_adj / r, 1.0)
    ratio = np.nan_to_num(ratio, nan=1.0, posinf=1.0, neginf=1.0)
    out["net_pnl_tp_sl"] = _as_num(out.get("net_pnl", pd.Series(dtype=float))).fillna(0.0) * ratio
    return out


def _guardrails(baseline_metrics: Dict[str, float], new_metrics: Dict[str, float]) -> Dict[str, Any]:
    ok_pf = (new_metrics.get("pf_net", 0) >= 1.5)
    dd_base = baseline_metrics.get("max_dd", np.nan)
    dd_new = new_metrics.get("max_dd", np.nan)
    ok_dd = (np.isnan(dd_base) or np.isnan(dd_new) or (dd_new <= dd_base * 1.10))
    ok_trs = (np.isnan(new_metrics.get("top_regime_share", np.nan)) or new_metrics.get("top_regime_share", 0) <= 0.45)
    return {"ok_pf": ok_pf, "ok_dd": ok_dd, "ok_top_regime": ok_trs, "accepted": bool(ok_pf and ok_dd and ok_trs)}


def process_symbol(symbol: str, winner_combo: str, root_f1: Path, out_root: Path) -> None:
    in_csv = root_f1 / winner_combo / f"trades_enriched_beta_{winner_combo}.csv"
    df = _safe_read(in_csv)
    if not df.empty:
        sym_col = df.get("symbol")
        if sym_col is not None:
            df = df.loc[sym_col.astype(str) == str(symbol)].copy()
    # ensure required columns
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        # best effort: create them
        for c in missing:
            df[c] = np.nan
    # baseline metrics
    base_metrics = _perf_metrics(df)
    # regime dist and proposal
    reg_dist = _regime_distribution(df)
    matrix = {}
    for _, r in reg_dist.iterrows():
        rg = str(r["regime"]) if pd.notna(r["regime"]) else "unknown"
        presets = REGIME_PRESETS.get(rg, {"tp_R": 1.5, "sl_R": 1.0})
        # conservative adjustment: if r_med low and mfe/mae weak, tighten tp; if strong, allow a bit more
        tp = float(presets["tp_R"])
        sl = float(presets["sl_R"])
        r_med = r.get("r_med", np.nan)
        ratio = r.get("mfe_mae_ratio_med", np.nan)
        if pd.notna(r_med):
            if r_med < 0.2:
                tp = max(1.2, tp - 0.2)
            elif r_med > 0.8:
                tp = min(2.2, tp + 0.2)
        if pd.notna(ratio):
            if ratio < 1.2:
                sl = min(1.2, sl + 0.1)
            elif ratio > 1.8:
                sl = max(0.8, sl - 0.1)
        matrix[rg] = {"tp_R": round(tp, 2), "sl_R": round(sl, 2)}
    # apply and compute metrics
    df2 = _apply_tp_sl(df, matrix)
    df2_eval = df2.copy()
    # ensure single net_pnl column for evaluation
    try:
        df2_eval["net_pnl"] = df2_eval["net_pnl_tp_sl"]
    except Exception:
        pass
    metrics2 = _perf_metrics(df2_eval)
    g = _guardrails(base_metrics, metrics2)

    # write artifacts
    out_dir = out_root / symbol
    _ensure_dir(out_dir)
    pd.DataFrame([{"regime": k, **v} for k,v in matrix.items()]).to_csv(out_dir / "tp_sl_matrix.csv", index=False)
    df2.to_csv(out_dir / "trades_enriched_tp_sl.csv", index=False)
    # delta
    lines = [
        f"# TP/SL por régimen — {symbol}",
        "",
        f"Ganador base: {winner_combo}",
        "",
        "## Métricas baseline (Fase 1_ext)",
        f"- pf_net: {base_metrics['pf_net']:.3f}",
        f"- expectancy: {base_metrics['expectancy']:.4f}",
        f"- max_dd: {base_metrics['max_dd']:.0f}",
        f"- top_regime_share: {base_metrics['top_regime_share'] if not np.isnan(base_metrics['top_regime_share']) else 'N/A'}",
        "",
        "## Métricas con TP/SL por régimen",
        f"- pf_net: {metrics2['pf_net']:.3f}",
        f"- expectancy: {metrics2['expectancy']:.4f}",
        f"- max_dd: {metrics2['max_dd']:.0f}",
        f"- top_regime_share: {metrics2['top_regime_share'] if not np.isnan(metrics2['top_regime_share']) else 'N/A'}",
        "",
        "## Guardrails",
        f"- pf_net ≥ 1.5: {'OK' if g['ok_pf'] else 'NO'}",
        f"- drawdown ≤ baseline +10%: {'OK' if g['ok_dd'] else 'NO'}",
        f"- top_regime_share ≤ 0.45: {'OK' if g['ok_top_regime'] else 'NO'}",
        "",
        f"Veredicto: {'ACEPTADO' if g['accepted'] else 'DESCARTADO'}",
    ]
    (out_dir / "delta_tp_sl.md").write_text("\n".join(lines), encoding="utf-8")
    # resumen
    resumen = [
        f"# Resumen técnico — {symbol}",
        "",
        "- Matriz TP/SL conservadora por régimen generada y aplicada.",
        "- Comparado vs baseline de Fase 1_ext sin TP/SL.",
        "- Resultado indicado en delta_tp_sl.md con guardrails.",
    ]
    (out_dir / "resumen_tecnico.md").write_text("\n".join(resumen), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root-f1", type=str, default=str(F1_EXT_ROOT_DEFAULT))
    ap.add_argument("--out-root", type=str, default=str(OUT_ROOT_DEFAULT))
    ap.add_argument("--winners", type=str, default=",".join([f"{k}:{v}" for k,v in WINNERS_DEFAULT.items()]), help="Formato: SYM:COMBO, ...")
    args = ap.parse_args()
    root_f1 = Path(args.root_f1)
    out_root = Path(args.out_root)
    winners: Dict[str, str] = {}
    for part in args.winners.split(","):
        if not part.strip():
            continue
        if ":" in part:
            s, c = part.split(":", 1)
            winners[s.strip()] = c.strip()
    for sym, combo in winners.items():
        process_symbol(sym, combo, root_f1, out_root)
    print(f"Hecho. Artefactos en {out_root}")


if __name__ == "__main__":
    main()

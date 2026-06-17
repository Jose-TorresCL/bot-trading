import argparse
from pathlib import Path
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

F1_EXT_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase1_ext")
F2_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase2_tp_sl")
OUT_MD = Path("data/backtesting/ANALISIS/Fase2_tp_sl/consolidado_fase2_tp_sl.md")
VIS_DIR = Path("data/backtesting/ANALISIS/Fase2_tp_sl/visuals")
SYMBOLS_DEFAULT = ["BTCUSDT","ETHUSDT","BNBUSDT","WLDUSDT"]
WINNERS_DEFAULT = {"BTCUSDT":"A2","ETHUSDT":"A2","BNBUSDT":"A2","WLDUSDT":"A1"}

METRICS = ["pf_net","expectancy","max_dd","trades_per_day","fees_share_pct","top_regime_share"]

plt.switch_backend('Agg')


def _read_csv(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def _metric(df: pd.DataFrame, sym: str, col: str) -> float:
    if df.empty:
        return np.nan
    col_sym = None
    for c in ("symbol","Symbol","SYMBOL"):
        if c in df.columns:
            col_sym = c
            break
    d = df if col_sym is None else df.loc[df[col_sym] == sym]
    if d.empty or col not in d.columns:
        return np.nan
    v = pd.to_numeric(d[col], errors='coerce')
    return float(v.iloc[0]) if len(v) else np.nan


def _as_num(s):
    try:
        return pd.to_numeric(s, errors='coerce')
    except Exception:
        return pd.Series(dtype=float)


def _perf_from_trades(df: pd.DataFrame) -> Dict[str, float]:
    pnl = _as_num(df.get('net_pnl', pd.Series(dtype=float))).fillna(0.0)
    pf = float(pnl[pnl>0].sum() / abs(pnl[pnl<0].sum())) if (pnl[pnl<0].sum()!=0) else (float('inf') if pnl[pnl>0].sum()>0 else 0.0)
    exp = float(pnl.mean()) if len(pnl) else np.nan
    eq = pnl.cumsum()
    dd = (eq - eq.cummax()).min() if not eq.empty else 0.0
    # freq
    tcol = 'exit_time' if 'exit_time' in df.columns else None
    tpd = np.nan
    if tcol:
        ts = pd.to_datetime(df[tcol], errors='coerce')
        if ts.notna().any():
            per_day = df.groupby(ts.dt.date).size()
            tpd = float(per_day.mean()) if len(per_day) else np.nan
    # fees%
    gross = _as_num(df.get('gross_pnl', pd.Series(dtype=float))).abs().sum()
    fees = _as_num(df.get('commission_paid', pd.Series(dtype=float))).sum() + _as_num(df.get('slippage_cost', pd.Series(dtype=float))).sum()
    fees_pct = float((fees/gross)*100.0) if gross>0 else np.nan
    # diversity
    trs = np.nan
    if 'regime_entry' in df.columns:
        cnt = df['regime_entry'].astype(str).value_counts(normalize=True)
        if cnt.size:
            trs = float(cnt.max())
    return {'pf_net': float(pf), 'expectancy': exp, 'max_dd': float(dd), 'trades_per_day': tpd, 'fees_share_pct': fees_pct, 'top_regime_share': trs}


def _plot_bars(data: Dict[str, Dict[str, float]], metric: str, out_dir: Path) -> None:
    _ensure_dir(out_dir)
    syms = list(data.keys())
    before = [data[s].get(f'{metric}_before', np.nan) for s in syms]
    after  = [data[s].get(f'{metric}_after', np.nan) for s in syms]
    x = np.arange(len(syms))
    w = 0.35
    fig, ax = plt.subplots(figsize=(8,4))
    ax.bar(x - w/2, before, width=w, label='Antes')
    ax.bar(x + w/2, after,  width=w, label='Después')
    ax.set_title(metric)
    ax.set_xticks(x);
    ax.set_xticklabels(syms)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / f'{metric}.png', dpi=140)
    plt.close(fig)


def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def build_consolidado(root_f1: Path, root_f2: Path, winners: Dict[str,str], out_md: Path, vis_dir: Path, symbols: List[str], weighting: str = 'equal') -> None:
    lines: List[str] = ["# Fase 2 — Consolidado TP/SL por régimen", "", f"Ponderación agregada: {weighting}", ""]
    data_for_plots: Dict[str, Dict[str, float]] = {}

    # Per-symbol comparison
    lines += ["## Tabla comparativa por símbolo", "", "| Symbol | pf_net (A/B) | expectancy (A/B) | max_dd (A/B) | trades/día (A/B) | fees% (A/B) | top_regime_share (A/B) | Veredicto |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    per_metrics: Dict[str, Dict[str, float]] = {}
    for sym in symbols:
        combo = winners.get(sym, 'A2')
        # Baseline F1_ext
        grid = _read_csv(root_f1 / combo / f'grid_results_beta_{combo}.csv')
        before = {
            'pf_net': _metric(grid, sym, 'pf_net'),
            'expectancy': _metric(grid, sym, 'expectancy'),
            'max_dd': _metric(grid, sym, 'max_dd'),
            'trades_per_day': _metric(grid, sym, 'trades_per_day'),
            'fees_share_pct': _metric(grid, sym, 'fees_share_pct'),
            'top_regime_share': _metric(grid, sym, 'top_regime_share'),
        }
        # After TP/SL from trades
        trades = _read_csv(root_f2 / sym / 'trades_enriched_tp_sl.csv')
        after = _perf_from_trades(trades)
        # Guardrails & verdict
        ok_pf = (after.get('pf_net', 0) >= 1.5)
        # max_dd in grids suele venir en negativo; comparamos magnitudes (abs)
        bef_dd = before['max_dd']
        aft_dd = after['max_dd']
        ok_dd = (
            np.isnan(bef_dd) or np.isnan(aft_dd)
            or (abs(aft_dd) <= abs(bef_dd) * 1.10)
        )
        ok_trs = (np.isnan(after.get('top_regime_share', np.nan)) or after['top_regime_share'] <= 0.45)
        verdict = 'ACEPTADO' if (ok_pf and ok_dd and ok_trs) else 'DESCARTADO'
        lines.append(f"| {sym} | {before['pf_net']:.3f} / {after['pf_net']:.3f} | {before['expectancy']:.4f} / {after['expectancy']:.4f} | {before['max_dd']:.0f} / {after['max_dd']:.0f} | {before['trades_per_day']:.3f} / {after['trades_per_day'] if not np.isnan(after['trades_per_day']) else float('nan'):.3f} | {before['fees_share_pct']:.2f} / {after['fees_share_pct']:.2f} | {before['top_regime_share']:.2f} / {after['top_regime_share']:.2f} | {verdict} |")
        data_for_plots[sym] = {f'{m}_before': before[m] for m in METRICS} | {f'{m}_after': after[m] for m in METRICS}
        per_metrics[sym] = before | {f'{m}_after': after[m] for m in METRICS}

    # Plots
    for m in METRICS:
        _plot_bars(data_for_plots, m, vis_dir)

    # Sensitivity suggestion (±0.1R): detect regimes with low r_med or poor mfe/mae
    lines += ["", "## Sensibilidad cruzada — ajustes sugeridos ±0.1R", ""]
    for sym in symbols:
        matrix = _read_csv(root_f2 / sym / 'tp_sl_matrix.csv')
        if matrix.empty:
            continue
        sugg: List[str] = []
        for _, r in matrix.iterrows():
            rg = str(r.get('regime',''))
            tp = float(r.get('tp_R', np.nan)) if pd.notna(r.get('tp_R', np.nan)) else np.nan
            sl = float(r.get('sl_R', np.nan)) if pd.notna(r.get('sl_R', np.nan)) else np.nan
            # Heurística simple: si pf_after < pf_before y top_regime_share alto, sugerir suavizar TP (+0.1R) o SL (-0.1R)
            b = per_metrics[sym]
            pf_bef = b['pf_net']; pf_aft = b['pf_net_after']
            trs_aft = b.get('top_regime_share_after', np.nan)
            if (not np.isnan(pf_aft) and not np.isnan(pf_bef) and pf_aft < pf_bef) or (not np.isnan(trs_aft) and trs_aft > 0.45):
                if not np.isnan(tp):
                    sugg.append(f"{rg}: considerar TP {tp:+.1f}→{tp+0.1:.1f}")
                if not np.isnan(sl):
                    sugg.append(f"{rg}: considerar SL {sl:+.1f}→{max(0.8, sl-0.1):.1f}")
        if sugg:
            lines += [f"- {sym}: "] + [f"  - {s}" for s in sugg]
        else:
            lines += [f"- {sym}: sin ajustes sugeridos (robusto en ±0.1R)"]

    # Multi-symbol aggregate
    lines += ["", "## Agregado multisimbolo (BTC, ETH, BNB)", ""]
    agg_syms = [s for s in symbols if s in ('BTCUSDT','ETHUSDT','BNBUSDT')]
    # weights
    if weighting == 'equal':
        w = {s: 1.0/len(agg_syms) for s in agg_syms}
    else:
        # vol-based: inverse of std of net_pnl from trades
        w = {}
        inv = []
        for s in agg_syms:
            t = _read_csv(root_f2 / s / 'trades_enriched_tp_sl.csv')
            std = _as_num(t.get('net_pnl', pd.Series(dtype=float))).std() if not t.empty else np.nan
            inv.append((s, 1.0/float(std) if (not np.isnan(std) and std>0) else np.nan))
        # normalize ignoring NaNs
        vals = [v for _, v in inv if not np.isnan(v)]
        if vals:
            ssum = sum(vals)
            for s, v in inv:
                w[s] = (v/ssum) if (not np.isnan(v)) else 0.0
        else:
            w = {s: 1.0/len(agg_syms) for s in agg_syms}
    # aggregate equity
    eq = None
    for s in agg_syms:
        t = _read_csv(root_f2 / s / 'trades_enriched_tp_sl.csv')
        if t.empty:
            continue
        pnl = _as_num(t.get('net_pnl', pd.Series(dtype=float))).fillna(0.0)  # already adjusted in file
        e = pnl * w.get(s, 0.0)
        eq = e if eq is None else (eq + e)
    dd = float((eq.cumsum() - eq.cumsum().cummax()).min()) if eq is not None and len(eq)>0 else 0.0
    lines += [f"- Ponderación: {weighting}", f"- Max drawdown agregado: {dd:.0f}"]

    # Save markdown
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding='utf-8')

    # Save a few visuals from per-symbol
    _ensure_dir(vis_dir)
    for m in METRICS:
        # already plotted per-symbol bars
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root-f1', type=str, default=str(F1_EXT_ROOT_DEFAULT))
    ap.add_argument('--root-f2', type=str, default=str(F2_ROOT_DEFAULT))
    ap.add_argument('--winners', type=str, default=",".join([f"{k}:{v}" for k,v in WINNERS_DEFAULT.items()]))
    ap.add_argument('--symbols', type=str, default=" ".join(SYMBOLS_DEFAULT))
    ap.add_argument('--weighting', type=str, choices=['equal','vol'], default='equal')
    args = ap.parse_args()
    winners = {}
    for p in args.winners.split(','):
        if ':' in p:
            s,c = p.split(':',1)
            winners[s.strip()] = c.strip()
    symbols = [s for s in args.symbols.split() if s]
    build_consolidado(Path(args.root_f1), Path(args.root_f2), winners, OUT_MD, VIS_DIR, symbols, weighting=args.weighting)
    print(f"Consolidado listo: {OUT_MD}")


if __name__ == '__main__':
    main()

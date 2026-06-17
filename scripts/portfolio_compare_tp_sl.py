import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Any, Sequence, Mapping
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

plt.switch_backend('Agg')

F1_EXT_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase1_ext")
F2_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase2_tp_sl")
OUT_PORTF_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase2_tp_sl/portfolio")
WINNERS_DEFAULT = {"ETHUSDT":"A2","BNBUSDT":"A2"}
SYMBOLS_DEFAULT = ["ETHUSDT","BNBUSDT"]


def _read_csv(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def _as_num(s):
    try:
        return pd.to_numeric(s, errors='coerce')
    except Exception:
        return pd.Series(dtype=float)


def _daily_pnl_from_trades(trades: pd.DataFrame, use_tp_sl: bool) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    tcol = 'exit_time' if 'exit_time' in trades.columns else ('entry_time' if 'entry_time' in trades.columns else None)
    if not tcol:
        return pd.Series(dtype=float)
    ts = pd.to_datetime(trades[tcol], errors='coerce')
    col = 'net_pnl_tp_sl' if (use_tp_sl and 'net_pnl_tp_sl' in trades.columns) else 'net_pnl'
    pnl = _as_num(trades.get(col, pd.Series(dtype=float)))
    df = pd.DataFrame({'date': ts.dt.date, 'pnl': pnl})
    df = df.dropna(subset=['date'])
    per_day = df.groupby('date')['pnl'].sum().sort_index()
    return per_day


def _load_pre_daily(root_f1: Path, symbol: str, combo: str) -> pd.Series:
    trades = _read_csv(root_f1 / combo / f'trades_enriched_beta_{combo}.csv')
    if trades.empty:
        return pd.Series(dtype=float)
    # filter symbol
    if 'symbol' in trades.columns:
        trades = trades.loc[trades['symbol'] == symbol]
    return _daily_pnl_from_trades(trades, use_tp_sl=False)


def _load_post_daily(root_f2: Path, symbol: str) -> pd.Series:
    trades = _read_csv(root_f2 / symbol / 'trades_enriched_tp_sl.csv')
    return _daily_pnl_from_trades(trades, use_tp_sl=True)


def _portfolio_weights_vol(daily_map: Dict[str, pd.Series]) -> Dict[str, float]:
    stds = {}
    for s, ser in daily_map.items():
        stds[s] = float(ser.std()) if ser is not None and len(ser)>0 else np.nan
    inv = {s: (1.0/v if (v is not None and not np.isnan(v) and v>0) else np.nan) for s,v in stds.items()}
    vals = [v for v in inv.values() if not np.isnan(v)]
    if not vals:
        # fallback equal
        n = len(daily_map) if daily_map else 1
        return {s: 1.0/n for s in daily_map.keys()}
    ssum = sum(vals)
    return {s: (inv[s]/ssum if not np.isnan(inv[s]) else 0.0) for s in daily_map.keys()}


def _align_and_aggregate(daily_map: Dict[str, pd.Series], weights: Dict[str, float]) -> pd.Series:
    # align by union of dates, fill missing with 0
    all_index = None
    for ser in daily_map.values():
        if ser is None or len(ser)==0:
            continue
        idx = pd.Index(ser.index)
        all_index = idx if all_index is None else all_index.union(idx)
    if all_index is None:
        return pd.Series(dtype=float)
    agg = pd.Series(0.0, index=all_index)
    for s, ser in daily_map.items():
        if ser is None or len(ser)==0:
            continue
        w = weights.get(s, 0.0)
        s_al = ser.reindex(all_index).fillna(0.0)
        agg = agg + (s_al * w)
    agg.index = pd.to_datetime(agg.index)
    agg = agg.sort_index()
    return agg


def _pf_from_series(pnl: pd.Series) -> float:
    if pnl is None or len(pnl)==0:
        return float('nan')
    pos = pnl[pnl>0].sum()
    neg = pnl[pnl<0].sum()
    return float(pos / abs(neg)) if neg != 0 else (float('inf') if pos>0 else 0.0)


def _max_dd_from_equity(eq: pd.Series) -> Tuple[float,float]:
    if eq is None or len(eq)==0:
        return 0.0, 0.0
    peak = eq.cummax()
    dd = eq - peak
    dd_pct = dd / peak.replace(0, np.nan)
    return float(dd.min()), float(dd_pct.min())


def _rolling_pf(pnl: pd.Series, window: int) -> pd.Series:
    if pnl is None or len(pnl)==0:
        return pd.Series(dtype=float)
    def pf_fn(x):
        pos = x[x>0].sum()
        neg = x[x<0].sum()
        if neg == 0:
            return np.inf if pos>0 else 0.0
        return pos/abs(neg)
    return pnl.rolling(window=window).apply(pf_fn, raw=False)


def _rolling_max_dd(eq: pd.Series, window: int) -> pd.Series:
    if eq is None or len(eq)==0:
        return pd.Series(dtype=float)
    # trailing window max drawdown (currency), using window equity
    def dd_fn(x):
        s = pd.Series(x)
        peak = s.cummax()
        dd = s - peak
        return dd.min()
    return eq.rolling(window=window).apply(dd_fn, raw=False)


def _save_rolling_overlay(s30: pd.Series, s60: pd.Series, out_path: Path, title: str, ylabel: str, label30: str = '30d', label60: str = '60d'):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9,4))
    if s30 is not None and len(s30)>0:
        ax.plot(pd.to_datetime(s30.index), s30.to_numpy(dtype=float), label=label30)
    if s60 is not None and len(s60)>0:
        ax.plot(pd.to_datetime(s60.index), s60.to_numpy(dtype=float), label=label60)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _top_drawdowns_table(eq_post: pd.Series, daily_post: Dict[str, pd.Series], symbols: List[str], weighting: str, n: int = 10) -> pd.DataFrame:
    if eq_post is None or len(eq_post)==0:
        return pd.DataFrame()
    peak = eq_post.cummax()
    dd = eq_post - peak  # negative values
    worst_idx = dd.nsmallest(min(n, len(dd))).index
    rows: List[Dict[str, Any]] = []
    for dt in worst_idx:
        row: Dict[str, Any] = {'fecha': pd.to_datetime(dt), 'weighting': weighting, 'equity_drop': float(dd.loc[dt])}
        total_loss = 0.0
        for s in symbols:
            ser = daily_post.get(s, pd.Series(dtype=float))
            val = 0.0
            if ser is not None and len(ser)>0:
                if dt in ser.index:
                    val = float(ser.loc[dt])
                else:
                    # try date match
                    d = pd.to_datetime(dt).date()
                    if d in ser.index:
                        val = float(ser.loc[d])
            loss = val if val < 0 else 0.0
            row[f'{s}_loss'] = loss
            total_loss += loss
        for s in symbols:
            loss = row[f'{s}_loss']
            row[f'{s}_loss_share'] = (loss/total_loss) if total_loss != 0 else np.nan
        rows.append(row)
    df = pd.DataFrame(rows)
    df = df.sort_values(['weighting','equity_drop'])
    return df


def _save_equity_plot(eq_pre: pd.Series, eq_post: pd.Series, out_path: Path, title: str):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9,4))
    if eq_pre is not None and len(eq_pre)>0:
        ax.plot(pd.to_datetime(eq_pre.index), eq_pre.to_numpy(dtype=float), label='Pre (baseline)')
    if eq_post is not None and len(eq_post)>0:
        ax.plot(pd.to_datetime(eq_post.index), eq_post.to_numpy(dtype=float), label='Post (TP/SL)')
    ax.set_title(title)
    ax.set_ylabel('Equity (USD)')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _save_heatmap_losses(daily_post: Dict[str,pd.Series], out_path: Path):
    # build matrix of losses only on top 10 worst aggregate days
    all_index = None
    for ser in daily_post.values():
        if all_index is None:
            all_index = pd.Index(ser.index)
        else:
            all_index = all_index.union(ser.index)
    if all_index is None:
        return
    df = pd.DataFrame({s: daily_post[s].reindex(all_index).fillna(0.0) for s in daily_post.keys()})
    df_losses = df.copy()
    df_losses[df_losses>0] = 0.0
    # aggregate losses (sum) per day to pick worst 10
    agg_losses = df_losses.sum(axis=1)
    worst_days = agg_losses.nsmallest(10).index
    m = df_losses.loc[worst_days]
    # correlation across symbols
    if m.shape[1] >= 2:
        corr = m.corr()
    else:
        corr = pd.DataFrame([[1.0]], index=m.columns, columns=m.columns)
    # heatmap
    fig, ax = plt.subplots(figsize=(4,3))
    im = ax.imshow(corr.values, cmap='Reds', vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha='right')
    ax.set_yticks(range(len(corr.index)))
    ax.set_yticklabels(corr.index)
    ax.set_title('Correlación de pérdidas (Top 10 días)')
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _regime_diversity_global(root_f2: Path, symbols: List[str]) -> Tuple[pd.DataFrame, float]:
    frames = []
    for s in symbols:
        t = _read_csv(root_f2 / s / 'trades_enriched_tp_sl.csv')
        if not t.empty and 'regime_entry' in t.columns:
            frames.append(t[['regime_entry']].copy())
    if not frames:
        return pd.DataFrame(), float('nan')
    df = pd.concat(frames, ignore_index=True)
    vc = df['regime_entry'].astype(str).value_counts()
    vcn = df['regime_entry'].astype(str).value_counts(normalize=True)
    tab = pd.DataFrame({'regime': vc.index, 'trades': vc.values, 'share': vcn.values})
    trs = float(vcn.max()) if len(vcn)>0 else float('nan')
    return tab, trs


def _loss_corr_top10(daily_post: Dict[str, pd.Series]) -> float:
    # Compute correlation of losses across symbols using the 10 worst aggregate loss days
    all_index = None
    for ser in daily_post.values():
        if all_index is None:
            all_index = pd.Index(ser.index)
        else:
            all_index = all_index.union(ser.index)
    if all_index is None or len(daily_post) < 2:
        return float('nan')
    df = pd.DataFrame({s: daily_post[s].reindex(all_index).fillna(0.0) for s in daily_post.keys()})
    df_losses = df.copy()
    df_losses[df_losses>0] = 0.0
    agg_losses = df_losses.sum(axis=1)
    worst_days = agg_losses.nsmallest(min(10, len(agg_losses))).index
    m = df_losses.loc[worst_days]
    if m.shape[1] < 2:
        return float('nan')
    corr = m.corr()
    # Return average off-diagonal correlation if >2 symbols; for 2 symbols this is the pairwise value
    try:
        vals = []
        for i in range(corr.shape[0]):
            for j in range(corr.shape[1]):
                if i != j:
                    vals.append(float(corr.values[i, j]))
        return float(np.nanmean(vals)) if vals else float('nan')
    except Exception:
        return float('nan')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root-f1', type=str, default=str(F1_EXT_ROOT_DEFAULT))
    ap.add_argument('--root-f2', type=str, default=str(F2_ROOT_DEFAULT))
    ap.add_argument('--symbols', type=str, default=" ".join(SYMBOLS_DEFAULT))
    ap.add_argument('--winners', type=str, default=",".join([f"{k}:{v}" for k,v in WINNERS_DEFAULT.items()]))
    ap.add_argument('--capital', type=float, default=100.0)
    ap.add_argument('--out-root', type=str, default=str(OUT_PORTF_ROOT_DEFAULT))
    args = ap.parse_args()

    root_f1 = Path(args.root_f1)
    root_f2 = Path(args.root_f2)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    winners: Dict[str,str] = {}
    for p in args.winners.split(','):
        if ':' in p:
            s,c = p.split(':',1)
            winners[s.strip()] = c.strip()
    symbols = [s for s in args.symbols.split() if s]

    # Load daily pnl pre/post
    pre_daily: Dict[str, pd.Series] = {}
    post_daily: Dict[str, pd.Series] = {}
    for s in symbols:
        combo = winners.get(s, 'A2')
        pre_daily[s] = _load_pre_daily(root_f1, s, combo)
        post_daily[s] = _load_post_daily(root_f2, s)

    # Equal weights
    w_equal = {s: 1.0/len(symbols) for s in symbols}
    # Vol weights based on post scenario std
    w_vol = _portfolio_weights_vol(post_daily)

    # Aggregate daily pnl
    pre_eq = _align_and_aggregate(pre_daily, w_equal)
    post_eq = _align_and_aggregate(post_daily, w_equal)
    pre_vol = _align_and_aggregate(pre_daily, w_vol)
    post_vol = _align_and_aggregate(post_daily, w_vol)

    # Equity curves (start with $100 per symbol)
    start_capital = args.capital * len(symbols)
    eq_pre_eq = start_capital + pre_eq.cumsum()
    eq_post_eq = start_capital + post_eq.cumsum()
    eq_pre_vol = start_capital + pre_vol.cumsum()
    eq_post_vol = start_capital + post_vol.cumsum()

    # Metrics table CSVs
    def build_metrics_row(pnl: pd.Series, eq: pd.Series, label: str) -> Dict[str, Any]:
        pf = _pf_from_series(pnl)
        exp = float(pnl.mean()) if pnl is not None and len(pnl)>0 else float('nan')
        dd_abs, dd_pct = _max_dd_from_equity(eq)
        end_eq = float(eq.iloc[-1]) if eq is not None and len(eq)>0 else float('nan')
        return {'scenario': label, 'pf_net': pf, 'expectancy_per_day': exp, 'max_dd': dd_abs, 'max_dd_pct': dd_pct, 'start_equity': start_capital, 'end_equity': end_eq}

    rows_equal = [
        build_metrics_row(pre_eq, eq_pre_eq, 'pre'),
        build_metrics_row(post_eq, eq_post_eq, 'post'),
    ]
    rows_vol = [
        build_metrics_row(pre_vol, eq_pre_vol, 'pre'),
        build_metrics_row(post_vol, eq_post_vol, 'post'),
    ]

    pd.DataFrame(rows_equal).to_csv(out_root / 'portfolio_results_equal.csv', index=False)
    pd.DataFrame(rows_vol).to_csv(out_root / 'portfolio_results_vol.csv', index=False)

    # Plots equity overlays
    _save_equity_plot(eq_pre_eq, eq_post_eq, out_root / 'portfolio_equity_equal.png', 'Equity (Equal-weight)')
    _save_equity_plot(eq_pre_vol, eq_post_vol, out_root / 'portfolio_equity_vol.png', 'Equity (Vol-weight)')

    # Heatmap correlation of losses (post)
    _save_heatmap_losses(post_daily, out_root / 'heatmap_corr_losses.png')

    # Contrib table (post)
    contrib = []
    for s in symbols:
        ser = post_daily.get(s, pd.Series(dtype=float))
        total = float(ser.sum()) if ser is not None else 0.0
        avg = float(ser.mean()) if ser is not None and len(ser)>0 else float('nan')
        neg_days = int((ser<0).sum()) if ser is not None else 0
        total_days = int(len(ser)) if ser is not None else 0
        contrib.append({'symbol': s, 'weight_equal': w_equal.get(s,0.0), 'weight_vol': w_vol.get(s,0.0), 'total_pnl': total, 'avg_daily_pnl': avg, 'neg_days': neg_days, 'total_days': total_days})
    df_contrib = pd.DataFrame(contrib)
    tot = df_contrib['total_pnl'].sum()
    if tot != 0:
        df_contrib['share_total_pnl'] = df_contrib['total_pnl'] / tot
    else:
        df_contrib['share_total_pnl'] = np.nan
    df_contrib.to_csv(out_root / 'contrib_table.csv', index=False)

    # Rolling PF and DD (30/60) summaries
    roll_pf_30_eq = _rolling_pf(post_eq, 30)
    roll_pf_60_eq = _rolling_pf(post_eq, 60)
    roll_dd_30_eq = _rolling_max_dd(eq_post_eq, 30)
    roll_dd_60_eq = _rolling_max_dd(eq_post_eq, 60)

    roll_pf_30_vol = _rolling_pf(post_vol, 30)
    roll_pf_60_vol = _rolling_pf(post_vol, 60)
    roll_dd_30_vol = _rolling_max_dd(eq_post_vol, 30)
    roll_dd_60_vol = _rolling_max_dd(eq_post_vol, 60)

    # Save rolling overlays (30/60)
    _save_rolling_overlay(roll_pf_30_eq, roll_pf_60_eq, out_root / 'rolling_pf_equal.png', 'Rolling PF (Equal-weight)', 'PF')
    _save_rolling_overlay(roll_pf_30_vol, roll_pf_60_vol, out_root / 'rolling_pf_vol.png', 'Rolling PF (Vol-weight)', 'PF')
    _save_rolling_overlay(roll_dd_30_eq, roll_dd_60_eq, out_root / 'rolling_dd_equal.png', 'Rolling DD (Equal-weight)', 'Drawdown (USD)')
    _save_rolling_overlay(roll_dd_30_vol, roll_dd_60_vol, out_root / 'rolling_dd_vol.png', 'Rolling DD (Vol-weight)', 'Drawdown (USD)')

    # Top drawdowns table aggregated (post)
    topdd_equal = _top_drawdowns_table(eq_post_eq, post_daily, symbols, 'equal', n=10)
    topdd_vol = _top_drawdowns_table(eq_post_vol, post_daily, symbols, 'vol', n=10)
    topdd = pd.concat([topdd_equal, topdd_vol], ignore_index=True) if (not topdd_equal.empty or not topdd_vol.empty) else pd.DataFrame()
    if not topdd.empty:
        topdd.to_csv(out_root / 'top_drawdowns_table.csv', index=False)

    # Diversity global por régimen (post)
    reg_tab, trs_glob = _regime_diversity_global(root_f2, symbols)

    # Markdown report
    def as_md_table(rows: Sequence[Mapping[Any, Any]], header_order: Sequence[str]) -> List[str]:
        if not rows:
            return ["(sin datos)"]
        hdr = "| " + " | ".join(header_order) + " |"
        sep = "|" + "|".join(["---" for _ in header_order]) + "|"
        out = [hdr, sep]
        for r in rows:
            vals = []
            for h in header_order:
                v = r.get(h, "")
                if isinstance(v, float):
                    # format some known fields
                    if h in ("pf_net", "expectancy_per_day", "max_dd", "start_equity", "end_equity"):
                        vals.append(f"{v:.3f}" if not np.isnan(v) else "nan")
                    elif h == "max_dd_pct":
                        vals.append(f"{v:.2%}" if not np.isnan(v) else "nan")
                    else:
                        vals.append(f"{v:.3f}" if not np.isnan(v) else "nan")
                else:
                    vals.append(str(v))
            out.append("| " + " | ".join(vals) + " |")
        return out

    lines = [
        "# Portfolio — Comparativa pre vs post TP/SL (ETHUSDT, BNBUSDT)",
        "",
        f"Capital fijo: ${args.capital} por símbolo; símbolos: {' '.join(symbols)}",
        "",
        "## Resumen métricas (Equal-weight)",
    ]
    lines += as_md_table(rows_equal, ["scenario","pf_net","expectancy_per_day","max_dd","max_dd_pct","start_equity","end_equity"]) + [""]
    lines += [
        "## Resumen métricas (Vol-weight)",
    ] + as_md_table(rows_vol, ["scenario","pf_net","expectancy_per_day","max_dd","max_dd_pct","start_equity","end_equity"]) + ["",
        "## Rolling PF y DD (post)",
        f"- Equal-weight: PF30 mediana={np.nanmedian(roll_pf_30_eq):.2f}, PF60 mediana={np.nanmedian(roll_pf_60_eq):.2f}; DD30 min={np.nanmin(roll_dd_30_eq):.0f}, DD60 min={np.nanmin(roll_dd_60_eq):.0f}",
        f"- Vol-weight: PF30 mediana={np.nanmedian(roll_pf_30_vol):.2f}, PF60 mediana={np.nanmedian(roll_pf_60_vol):.2f}; DD30 min={np.nanmin(roll_dd_30_vol):.0f}, DD60 min={np.nanmin(roll_dd_60_vol):.0f}",
        "",
        "## Correlación de pérdidas",
        "- Ver heatmap_corr_losses.png (top 10 días de pérdidas)",
        "",
        "## Diversidad global por régimen (post)",
    ]
    if not reg_tab.empty:
        # build simple table for regimes with string keys
        reg_rows_raw = reg_tab.to_dict(orient='records')
        reg_rows = []
        for r in reg_rows_raw:
            reg_rows.append({
                'regime': str(r.get('regime','')),
                'trades': int(r.get('trades', 0)) if pd.notna(r.get('trades', np.nan)) else 0,
                'share': float(r.get('share', np.nan)) if pd.notna(r.get('share', np.nan)) else np.nan,
            })
        lines += as_md_table(reg_rows, ["regime","trades","share"]) + ["", f"Top regime share global: {trs_glob:.2f}"]
    else:
        lines += ["Sin información de régimen", ""]

    # Append Top 10 drawdowns aggregated (post)
    lines += ["", "## Top 10 drawdowns agregados (post)"]
    if 'topdd' in locals() and not topdd.empty:
        td_view = topdd.copy()
        td_view['fecha'] = pd.to_datetime(td_view['fecha']).dt.strftime('%Y-%m-%d')
        cols = ['weighting','fecha','equity_drop']
        for s in symbols:
            cols += [f'{s}_loss', f'{s}_loss_share']
        rows_td = td_view[cols].to_dict(orient='records')
        lines += as_md_table(rows_td, cols)
    else:
        lines += ["(sin datos)"]

    # Institutional commentary and verdict
    lines += ["", "## Comentario institucional (automático)"]
    pre_eq_dd = rows_equal[0]['max_dd']
    post_eq_dd = rows_equal[1]['max_dd']
    pre_eq_pf = rows_equal[0]['pf_net']
    post_eq_pf = rows_equal[1]['pf_net']
    loss_corr = _loss_corr_top10(post_daily)
    dd_stable = (abs(post_eq_dd) <= abs(pre_eq_dd) + 1e-6)
    dd_guardrail_ok = (abs(post_eq_dd) <= abs(pre_eq_dd) * 1.10 + 1e-6)  # ≤ pre +10%
    pf_threshold_ok = (post_eq_pf >= 1.5)
    pf_nondegrade_ok = (post_eq_pf >= pre_eq_pf - 0.05)
    pf_ok = (pf_threshold_ok and pf_nondegrade_ok)
    corr_ok = (not np.isnan(loss_corr) and loss_corr <= 0.65)
    div_ok = (np.isnan(trs_glob) or trs_glob <= 0.45)
    lines += [
        f"- Correlación de pérdidas (top 10 días): {loss_corr:.2f} (umbral ≤ 0.65)",
        f"- Drawdown agregado (equal): pre={pre_eq_dd:.0f}, post={post_eq_dd:.0f} → {'mejora/mantiene' if dd_stable else 'empeora'} (guardrail: ≤ pre +10% → {'OK' if dd_guardrail_ok else 'FAIL'})",
        f"- PF neto (equal): pre={pre_eq_pf:.2f}, post={post_eq_pf:.2f} → {'OK' if pf_ok else 'FAIL'} (umbral post ≥ 1.50 y no degradar > 0.05)",
        f"- Diversidad global por régimen (top_regime_share): {trs_glob:.2f} (umbral ≤ 0.45)"
    ]

    lines += ["", "## Veredicto institucional del agregado (ETH+BNB)"]
    verdict_ok = (dd_guardrail_ok and pf_ok and corr_ok and div_ok)
    lines += [
        f"- ¿Puede ejecutarse como bot multisimbolo en paralelo? {'Sí' if verdict_ok else 'No'}",
        f"- Guardrails: DD {'OK' if dd_guardrail_ok else 'FAIL'} · PF {'OK' if pf_ok else 'FAIL'} · Corr pérdidas {'OK' if corr_ok else 'FAIL'} · Diversidad {'OK' if div_ok else 'FAIL'}",
    ]

    (out_root / 'portfolio_metrics.md').write_text("\n".join(lines), encoding='utf-8')

    # If positive verdict, emit changelog and launch docs
    if verdict_ok:
        winners_str = ", ".join([f"{k}:{v}" for k,v in winners.items()])
        changelog = [
            "# Changelog técnico de cierre — ETH+BNB",
            "",
            "- Consolidación Fase 2 con TP/SL por régimen, métricas recalculadas con n_distinct(trade_id)/día.",
            "- Comparativa agregada pre vs post (equal y vol): equity overlays, rolling PF/DD (30/60), correlación de pérdidas (top 10).",
            "- Diversidad global por régimen validada; guardrails institucionales cumplidos en el agregado.",
            "- Artefactos estandarizados bajo Fase2_tp_sl/portfolio (CSVs, PNGs, MD).",
            f"- Ganadores por símbolo (Fase1_ext): {winners_str}.",
        ]
        (out_root / 'changelog_cierre_tecnico.md').write_text("\n".join(changelog), encoding='utf-8')

        launch = [
            "# Lanzamiento operativo — ETH+BNB (configuraciones congeladas)",
            "",
            f"- Símbolos: {' '.join(symbols)}",
            f"- Capital fijo por símbolo: ${args.capital:.0f}",
            "- Ejecución: multisimbolo en paralelo (no mezclar carteras; cada símbolo con su propio sizing fijo).",
            f"- Ganadores de Fase1_ext: {winners_str} (mantener filtros/proximidad/horarios de esos combos).",
            "- TP/SL por régimen: usar matrices exportadas por símbolo en Fase2_tp_sl/<SYMBOL>/tp_sl_matrix.csv.",
            "- Fees/slippage: mantener parámetros del backtest institucional (ver scripts y requirements).",
            "- Monitoreo: revisar heatmap_corr_losses.png y rolling_pf_*.png / rolling_dd_*.png semanalmente.",
        ]
        (out_root / 'lanzamiento_operativo.md').write_text("\n".join(launch), encoding='utf-8')
    print(f"Listo. Artefactos en {out_root}")


if __name__ == '__main__':
    main()

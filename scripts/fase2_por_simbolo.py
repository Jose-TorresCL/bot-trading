import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import traceback
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

plt.switch_backend('Agg')

F1_EXT_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase1_ext")
F2_ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase2_tp_sl")
WINNERS_DEFAULT = {"BTCUSDT":"A2","ETHUSDT":"A2","BNBUSDT":"A2","WLDUSDT":"A1"}
SYMBOLS_DEFAULT = ["BTCUSDT","ETHUSDT","BNBUSDT","WLDUSDT"]


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


def _trades_per_day_distinct(trades: pd.DataFrame) -> float:
    if trades.empty:
        return float('nan')
    tcol = 'exit_time' if 'exit_time' in trades.columns else ('entry_time' if 'entry_time' in trades.columns else None)
    if tcol is None or tcol not in trades.columns:
        return float('nan')
    ts = pd.to_datetime(trades[tcol], errors='coerce')
    if 'trade_id' in trades.columns:
        key = trades['trade_id']
    else:
        # fallback: use index to approximate distinct trades
        key = trades.index.astype(str)
    df = pd.DataFrame({'date': ts.dt.date, 'tid': key})
    df = df.dropna(subset=['date'])
    per_day = df.groupby('date')['tid'].nunique()
    return float(per_day.mean()) if len(per_day) else float('nan')


def _perf_from_trades(trades: pd.DataFrame, capital: float) -> Tuple[Dict[str,float], pd.Series, pd.Series]:
    # prefer TP/SL-adjusted net if present
    pnl_col = 'net_pnl_tp_sl' if 'net_pnl_tp_sl' in trades.columns else 'net_pnl'
    pnl = _as_num(trades.get(pnl_col, pd.Series(dtype=float))).fillna(0.0)
    gross = _as_num(trades.get('gross_pnl', pd.Series(dtype=float))).fillna(0.0)
    comm = _as_num(trades.get('commission_paid', pd.Series(dtype=float))).fillna(0.0)
    slip = _as_num(trades.get('slippage_cost', pd.Series(dtype=float))).fillna(0.0)

    pf = float(pnl[pnl>0].sum() / abs(pnl[pnl<0].sum())) if (pnl[pnl<0].sum()!=0) else (float('inf') if pnl[pnl>0].sum()>0 else 0.0)
    exp = float(pnl.mean()) if len(pnl) else float('nan')

    equity = capital + pnl.cumsum()
    # ensure numeric array for plotting and dd calculations
    equity = pd.Series(_as_num(equity).astype(float))
    rolling_peak = equity.cummax()
    denom = rolling_peak.replace(0, np.nan).astype(float)
    dd_curve = (equity - rolling_peak) / denom
    max_dd_pct = float(dd_curve.min()) if not dd_curve.empty else 0.0

    fees_total = float((comm + slip).sum())
    gross_abs = float(gross.abs().sum())
    fees_pct = float((fees_total / gross_abs) * 100.0) if gross_abs > 0 else float('nan')

    trs = float('nan')
    if 'regime_entry' in trades.columns:
        cnt = trades['regime_entry'].astype(str).value_counts(normalize=True)
        if cnt.size:
            trs = float(cnt.max())

    tpd = _trades_per_day_distinct(trades)

    m = {
        'pf_net': float(pf),
        'expectancy': float(exp),
        'max_dd_pct': max_dd_pct,  # negative value, e.g. -0.18 for -18%
        'trades_per_day': tpd,
        'fees_share_pct': float(fees_pct),
        'top_regime_share': trs,
    }
    return m, equity, dd_curve


def _baseline_dd_abs(root_f1: Path, sym: str, combo: str) -> float:
    grid = _read_csv(root_f1 / combo / f'grid_results_beta_{combo}.csv')
    if grid.empty:
        return float('nan')
    col_sym = None
    for c in ('symbol','Symbol','SYMBOL'):
        if c in grid.columns:
            col_sym = c
            break
    d = grid if col_sym is None else grid.loc[grid[col_sym] == sym]
    val = _as_num(d.get('max_dd', pd.Series(dtype=float)))
    return float(val.iloc[0]) if len(val) else float('nan')


def _write_md(p: Path, lines: List[str]):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines), encoding='utf-8')


def _update_delta_with_verdict(sym_dir: Path, symbol: str, verdict: str, checks: Dict[str, str]):
    # Update both existing delta_tp_sl.md and a symbol-specific copy
    base = sym_dir / 'delta_tp_sl.md'
    sym_copy = sym_dir / f'delta_tp_sl_{symbol}.md'
    block = [
        "\n---\n",
        "## Veredicto institucional",
        f"- Símbolo: {symbol}",
        f"- Veredicto: {verdict}",
        "- Guardrails:",
    ] + [f"  - {k}: {v}" for k,v in checks.items()] + ["\n"]
    try:
        if base.exists():
            txt = base.read_text(encoding='utf-8')
        else:
            txt = ""
        txt2 = txt + "\n" + "\n".join(block)
        base.write_text(txt2, encoding='utf-8')
        sym_copy.write_text(txt2, encoding='utf-8')
    except Exception:
        # best-effort
        sym_copy.write_text("\n".join(block), encoding='utf-8')


def process_symbol(root_f1: Path, root_f2: Path, symbol: str, combo: str, capital: float):
    sym_dir = root_f2 / symbol
    log_file = sym_dir / 'fase2_por_simbolo.log'
    try:
        print(f"[START] {symbol}")
        trades = _read_csv(sym_dir / 'trades_enriched_tp_sl.csv')
        if trades.empty:
            msg = f"[WARN] No trades for {symbol}"
            print(msg)
            log_file.write_text(msg + "\n", encoding='utf-8')
            return

        # metrics after
        metrics, equity, dd_curve = _perf_from_trades(trades, capital)

        # baseline dd absolute (currency)
        dd_baseline_abs = _baseline_dd_abs(root_f1, symbol, combo)

        # PNG equity
        fig, ax = plt.subplots(figsize=(9,4))
        ax.plot(equity.to_numpy(dtype=float), label=f'Equity ${capital} base')
        ax.set_title(f'Equity Curve {symbol} (TP/SL por régimen)')
        ax.set_ylabel('Equity (USD)')
        ax.legend()
        fig.tight_layout()
        out_png = sym_dir / f'equity_curve_{symbol}.png'
        fig.savefig(out_png, dpi=140)
        plt.close(fig)

        # regime diversity md
        div_lines = [f"# Regime diversity — {symbol}", ""]
        if 'regime_entry' in trades.columns:
            vc = trades['regime_entry'].astype(str).value_counts()
            vc_norm = trades['regime_entry'].astype(str).value_counts(normalize=True)
            div_lines.append("| Regime | trades | share |")
            div_lines.append("|---|---:|---:|")
            for rg, cnt in vc.items():
                div_lines.append(f"| {rg} | {int(cnt)} | {vc_norm.get(rg,0.0):.2f} |")
            div_lines.append("")
            div_lines.append(f"Top regime share: {metrics['top_regime_share']:.2f}")
        else:
            div_lines.append("Sin columna 'regime_entry'")
        _write_md(sym_dir / f'regime_diversity_{symbol}.md', div_lines)

        # metrics md
        met_lines = [f"# Métricas por símbolo — {symbol}", "",
                     f"- pf_net: {metrics['pf_net']:.3f}",
                     f"- expectancy: {metrics['expectancy']:.4f} USD por trade",
                     f"- max_dd_pct: {metrics['max_dd_pct']:.2%}",
                     f"- trades/día (n_distinct trade_id): {metrics['trades_per_day']:.3f}",
                     f"- fees_share_pct: {metrics['fees_share_pct']:.2f}%",
                     f"- top_regime_share: {metrics['top_regime_share']:.2f}",
                     "",
                     f"Baseline max_dd (abs, grid {combo}): {dd_baseline_abs:.0f}"]
        _write_md(sym_dir / f'metrics_{symbol}.md', met_lines)

        # verdict per institutional guardrails
        checks: Dict[str, str] = {}
        ok_pf = metrics['pf_net'] >= 1.5
        checks['pf_net ≥ 1.5'] = 'OK' if ok_pf else f"FAIL ({metrics['pf_net']:.2f})"
        ok_dd20 = abs(metrics['max_dd_pct']) <= 0.20
        checks['drawdown_pct < 20%'] = 'OK' if ok_dd20 else f"FAIL ({metrics['max_dd_pct']:.1%})"
        ok_trs = (np.isnan(metrics['top_regime_share']) or metrics['top_regime_share'] <= 0.45)
        checks['top_regime_share ≤ 0.45'] = 'OK' if ok_trs else f"FAIL ({metrics['top_regime_share']:.2f})"
        ok_tpd = (not np.isnan(metrics['trades_per_day']) and metrics['trades_per_day'] >= 1.0)
        checks['frecuencia ≥ 1 trade/día'] = 'OK' if ok_tpd else f"FAIL ({metrics['trades_per_day']:.2f})"
        ok_fees = (not np.isnan(metrics['fees_share_pct']) and metrics['fees_share_pct'] < 10.0)
        checks['fees% < 10%'] = 'OK' if ok_fees else f"FAIL ({metrics['fees_share_pct']:.2f}%)"
        ok_exp = metrics['expectancy'] > 0.0
        checks['expectancy > 0'] = 'OK' if ok_exp else f"FAIL ({metrics['expectancy']:.4f})"

        verdict = '✅ INSTITUCIONALIZAR' if (ok_pf and ok_dd20 and ok_trs and ok_tpd and ok_fees and ok_exp) else '❌ DESCARTAR'

        _update_delta_with_verdict(sym_dir, symbol, verdict, checks)
        print(f"[DONE] {symbol}: {verdict}")
    except Exception as ex:
        tb = traceback.format_exc()
        msg = f"[ERROR] {symbol}: {ex}\n{tb}"
        print(msg)
        try:
            log_file.write_text(msg, encoding='utf-8')
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root-f1', type=str, default=str(F1_EXT_ROOT_DEFAULT))
    ap.add_argument('--root-f2', type=str, default=str(F2_ROOT_DEFAULT))
    ap.add_argument('--symbols', type=str, default=" ".join(SYMBOLS_DEFAULT))
    ap.add_argument('--winners', type=str, default=",".join([f"{k}:{v}" for k,v in WINNERS_DEFAULT.items()]))
    ap.add_argument('--capital', type=float, default=100.0)
    args = ap.parse_args()

    winners: Dict[str, str] = {}
    for p in args.winners.split(','):
        if ':' in p:
            s,c = p.split(':',1)
            winners[s.strip()] = c.strip()
    root_f1 = Path(args.root_f1)
    root_f2 = Path(args.root_f2)
    symbols = [s for s in args.symbols.split() if s]

    for sym in symbols:
        combo = winners.get(sym, 'A2')
        process_symbol(root_f1, root_f2, sym, combo, args.capital)


if __name__ == '__main__':
    main()

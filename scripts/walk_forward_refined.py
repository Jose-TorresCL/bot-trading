import os
import json
import argparse
from datetime import datetime
from math import ceil
from typing import List, Dict, Any
from src.reporting.metrics import profit_factor as _pf_helper
from src.reporting.metrics import max_drawdown as _mdd_helper

import pandas as pd

"""Walk-Forward Refinado por Bloques de Trades (cuantiles de tiempo)

Objetivo: Ventanas con 8–10 trades (si la muestra lo permite) usando el orden por exit_time
(que equivale a cuantiles de tiempo). Si la muestra es insuficiente para 3 ventanas de >=8 trades,
se aplica un fallback para obtener 3 ventanas balanceadas con menor tamaño y se documenta la razón.

Métricas por ventana:
- trades
- pf_net
- winrate_net
- max_dd_net
- expectancy_net
- expectancy_per_min (expectancy / avg_duration_min)
- expectancy_per_notional (expectancy / avg_notional)
- r_multiple_median_net
- skew_r_multiple_net
- cumulative_pnl_net
- start_exit_time / end_exit_time
- time_span_ratio (span ventana / span global)
- trade_share_ratio (trades ventana / trades global)

Flags heurísticos:
- stable_pf: |pf - global_pf|/global_pf <= pf_tolerance (si global_pf>0)
- degrade_pf: pf < global_pf * pf_degradation_factor
- cluster_concentration: (trade_share_ratio / max(time_span_ratio, 1e-9)) > concentration_factor

JSON flags: por ventana { pf_net, estable, skew_r, degrade_pf, cluster_concentration }

Limitaciones: con N=18 trades no es posible generar ≥3 ventanas de 8-10 (se necesitarían ≥24). Se aplica fallback.
"""


def calc_profit_factor(pnls: pd.Series) -> float:
    return float(_pf_helper(pnls)) if len(pnls) else 0.0


def calc_max_dd(pnls: pd.Series) -> float:
    if pnls.empty:
        return 0.0
    # helper devuelve negativo; reportar magnitud
    return float(abs(_mdd_helper(pnls)))


def skew_series(x: pd.Series) -> float:
    x = x.dropna()
    n = len(x)
    if n < 3:
        return 0.0
    mean = x.mean()
    std = x.std(ddof=1)
    if std == 0:
        return 0.0
    m3 = ((x - mean) ** 3).sum() / n
    g1 = (n * m3) / ((n - 1) * (n - 2) * (std ** 3))
    return float(g1)


def compute_window_metrics(df: pd.DataFrame, global_start, global_end) -> Dict[str, Any]:
    pf = calc_profit_factor(df['net_pnl'])
    winrate = float((df['net_pnl'] > 0).mean() * 100) if not df.empty else 0.0
    expectancy = float(df['net_pnl'].mean()) if not df.empty else 0.0
    max_dd = calc_max_dd(df['net_pnl'])
    r_med = float(df['r_multiple_net'].median()) if 'r_multiple_net' in df.columns and not df.empty else 0.0
    skew_r = skew_series(df['r_multiple_net']) if 'r_multiple_net' in df.columns else 0.0
    cum_pnl = float(df['net_pnl'].sum())

    # Duraciones
    if 'entry_time' in df.columns and 'exit_time' in df.columns:
        try:
            durations = (pd.to_datetime(df['exit_time']) - pd.to_datetime(df['entry_time'])).dt.total_seconds() / 60.0
        except Exception:
            durations = pd.Series([0]*len(df))
    else:
        durations = pd.Series([0]*len(df))
    avg_duration = durations.mean() if len(durations) else 0
    expectancy_per_min = expectancy / avg_duration if avg_duration else 0.0

    # Notional
    if 'notional' in df.columns and df['notional'].mean() != 0:
        expectancy_per_notional = expectancy / df['notional'].mean()
    else:
        expectancy_per_notional = 0.0

    start_exit = pd.to_datetime(df['exit_time']).min() if 'exit_time' in df.columns and not df.empty else None
    end_exit = pd.to_datetime(df['exit_time']).max() if 'exit_time' in df.columns and not df.empty else None

    if start_exit is not None and end_exit is not None and global_start is not None and global_end is not None:
        time_span_ratio = (end_exit - start_exit).total_seconds() / max((global_end - global_start).total_seconds(), 1)
    else:
        time_span_ratio = 0.0

    return {
        'trades': int(len(df)),
        'pf_net': pf,
        'winrate_net': winrate,
        'expectancy_net': expectancy,
        'max_dd_net': max_dd,
        'r_multiple_median_net': r_med,
        'skew_r_multiple_net': skew_r,
        'cumulative_pnl_net': cum_pnl,
        'expectancy_per_min': expectancy_per_min,
        'expectancy_per_notional': expectancy_per_notional,
        'avg_duration_min': float(avg_duration) if avg_duration == avg_duration else 0.0,
        'start_exit_time': start_exit,
        'end_exit_time': end_exit,
        'time_span_ratio': time_span_ratio
    }


def segment_trades(df: pd.DataFrame, min_block=8, max_block=10, min_windows=3):
    n = len(df)
    segments = []
    fallback = None
    if n >= min_block * min_windows:
        # Intentar usar block size cercano al promedio
        # Calcular número de ventanas ideal usando block size medio
        target_block = (min_block + max_block) // 2
        windows = max(min_windows, n // target_block + (1 if n % target_block else 0))
        # Asegurar block dentro de rango
        block_size = min(max_block, max(min_block, ceil(n / windows)))
        start = 0
        while start < n:
            end = min(n, start + block_size)
            segments.append(df.iloc[start:end])
            start = end
        # Si última ventana quedó < min_block intentar redistribuir
        if len(segments) >= 2 and len(segments[-1]) < min_block:
            short_len = len(segments[-1])
            segments[-2] = pd.concat([segments[-2], segments[-1]])
            segments.pop()
            fallback = f'Redistribuido último bloque pequeño (len={short_len}).'
    else:
        # Fallback: crear exactamente min_windows ventanas balanceadas
        base = n // min_windows
        rem = n % min_windows
        idx = 0
        for i in range(min_windows):
            size = base + (1 if i < rem else 0)
            if size == 0:
                continue
            segments.append(df.iloc[idx: idx + size])
            idx += size
        fallback = f'Muestra insuficiente (n={n}) para ventanas de {min_block}-{max_block}; usando {len(segments)} ventanas balanceadas (~{base} o {base+1} trades).'
    return segments, fallback


def main():
    parser = argparse.ArgumentParser(description='Walk-forward refinado por bloques de trades')
    parser.add_argument('--run-id', help='ID de run (carpeta ANALISIS)')
    parser.add_argument('--analysis-root', default=os.path.join('data','backtesting','ANALISIS'))
    parser.add_argument('--min-block', type=int, default=8)
    parser.add_argument('--max-block', type=int, default=10)
    parser.add_argument('--min-windows', type=int, default=3)
    args = parser.parse_args()

    # Detectar run si no se pasa
    if not args.run_id:
        candidates = [d for d in os.listdir(args.analysis_root) if d.startswith('202') and os.path.isdir(os.path.join(args.analysis_root, d))]
        if not candidates:
            raise RuntimeError('No runs encontrados')
        run_id = sorted(candidates)[-1]
    else:
        run_id = args.run_id

    trades_path = os.path.join(args.analysis_root, run_id, 'modelo_costos', 'trades_enriched_global.csv')
    if not os.path.isfile(trades_path):
        raise FileNotFoundError(f'No existe {trades_path}')

    df = pd.read_csv(trades_path)
    if 'exit_time' in df.columns:
        try:
            df['exit_time'] = pd.to_datetime(df['exit_time'])
        except Exception:
            pass
    if 'entry_time' in df.columns:
        try:
            df['entry_time'] = pd.to_datetime(df['entry_time'])
        except Exception:
            pass

    df = df.sort_values('exit_time').reset_index(drop=True)
    if 'r_multiple_net' not in df.columns and 'r_multiple' in df.columns:
        df['r_multiple_net'] = df['r_multiple']  # fallback
    elif 'r_multiple_net' not in df.columns:
        df['r_multiple_net'] = 0.0

    global_start = df['exit_time'].min() if 'exit_time' in df.columns else None
    global_end = df['exit_time'].max() if 'exit_time' in df.columns else None

    segments, fallback_reason = segment_trades(df, args.min_block, args.max_block, args.min_windows)

    # Métricas globales
    global_metrics = compute_window_metrics(df, global_start, global_end)

    pf_tolerance = 0.50  # +/-50%
    pf_degradation_factor = 0.50
    concentration_factor = 2.0

    windows_info: Dict[str, Any] = {}
    for i, seg in enumerate(segments, start=1):
        metrics = compute_window_metrics(seg, global_start, global_end)
        trade_share_ratio = metrics['trades'] / max(len(df),1)
        metrics['trade_share_ratio'] = trade_share_ratio
        # cluster concentration
        if metrics['time_span_ratio'] > 0:
            concentration_ratio = trade_share_ratio / metrics['time_span_ratio']
        else:
            concentration_ratio = float('inf') if trade_share_ratio > 0 else 0.0
        cluster_concentration = concentration_ratio > concentration_factor

        if global_metrics['pf_net'] > 0:
            stable_pf = abs(metrics['pf_net'] - global_metrics['pf_net']) / global_metrics['pf_net'] <= pf_tolerance
            degrade_pf = metrics['pf_net'] < global_metrics['pf_net'] * pf_degradation_factor
        else:
            stable_pf = True
            degrade_pf = False

        windows_info[f'ventana_{i}'] = {**metrics,
                                         'stable_pf': stable_pf,
                                         'degrade_pf': degrade_pf,
                                         'cluster_concentration': cluster_concentration,
                                         'concentration_ratio': concentration_ratio}

    # Derivar drift de r_multiple_median y expectancy
    r_meds = [w['r_multiple_median_net'] for w in windows_info.values()]
    expectancies = [w['expectancy_net'] for w in windows_info.values()]
    drift_r = all(r_meds[i] < r_meds[i-1] for i in range(1, len(r_meds))) and len(r_meds) >= 3
    drift_expectancy = all(expectancies[i] < expectancies[i-1] for i in range(1, len(expectancies))) and len(expectancies) >= 3

    out_dir = os.path.join(args.analysis_root, run_id, 'modelo_costos')
    flags_path = os.path.join(out_dir, 'walk_forward_flags_refined.json')
    report_path = os.path.join(out_dir, 'summary_walk_forward_refined.md')

    flags = {
        'run_id': run_id,
        'generated_utc': datetime.utcnow().isoformat() + 'Z',
        'global_metrics': global_metrics,
        'params': {
            'pf_tolerance': pf_tolerance,
            'pf_degradation_factor': pf_degradation_factor,
            'concentration_factor': concentration_factor,
            'min_block': args.min_block,
            'max_block': args.max_block,
            'min_windows': args.min_windows
        },
        'fallback_reason': fallback_reason,
        'windows': {k: {
            'pf_net': v['pf_net'],
            'estable': v['stable_pf'],
            'skew_r': v['skew_r_multiple_net'],
            'degrade_pf': v['degrade_pf'],
            'cluster_concentration': v['cluster_concentration']
        } for k, v in windows_info.items()},
        'drift': {
            'r_multiple_median_monotonic_decrease': drift_r,
            'expectancy_monotonic_decrease': drift_expectancy
        }
    }

    with open(flags_path, 'w', encoding='utf-8') as f:
        json.dump(flags, f, ensure_ascii=False, indent=2, default=str)

    # Reporte MD
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('# Walk-Forward Refinado (Bloques de Trades)\n\n')
        f.write(f'Run: {run_id}  \nGenerado: {datetime.utcnow().isoformat()}Z\n\n')
        if fallback_reason:
            f.write(f'> Nota: {fallback_reason}\n\n')
        f.write('## Métricas Globales\n\n')
        f.write('| trades | pf_net | winrate_net | max_dd_net | expectancy_net | r_med_net | skew_r | cum_pnl | exp_per_min | exp_per_notional |\n')
        f.write('|---|---|---|---|---|---|---|---|---|---|\n')
        f.write(f"| {global_metrics['trades']} | {global_metrics['pf_net']:.4f} | {global_metrics['winrate_net']:.2f} | {global_metrics['max_dd_net']:.4f} | {global_metrics['expectancy_net']:.4f} | {global_metrics['r_multiple_median_net']:.4f} | 0.0000 | {global_metrics['cumulative_pnl_net']:.4f} | {global_metrics['expectancy_net']:.4f} | 0.0000 |\n\n")

        f.write('## Ventanas\n\n')
        f.write('| ventana | trades | start_exit | end_exit | pf_net | winrate | max_dd | expectancy | r_med_net | skew_r | cum_pnl | exp_per_min | exp_per_notional | time_span_ratio | trade_share_ratio | stable_pf | degrade_pf | cluster_conc | conc_ratio |\n')
        f.write('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n')
        for name, v in windows_info.items():
            f.write('|' + ' | '.join([
                name,
                str(v['trades']),
                str(v['start_exit_time']),
                str(v['end_exit_time']),
                f"{v['pf_net']:.4f}",
                f"{v['winrate_net']:.2f}",
                f"{v['max_dd_net']:.4f}",
                f"{v['expectancy_net']:.4f}",
                f"{v['r_multiple_median_net']:.4f}",
                f"{v['skew_r_multiple_net']:.4f}",
                f"{v['cumulative_pnl_net']:.4f}",
                f"{v['expectancy_per_min']:.4f}",
                f"{v['expectancy_per_notional']:.6f}",
                f"{v['time_span_ratio']:.4f}",
                f"{v['trade_share_ratio']:.4f}",
                str(v['stable_pf']),
                str(v['degrade_pf']),
                str(v['cluster_concentration']),
                f"{v['concentration_ratio']:.4f}"
            ]) + '|\n')
        f.write('\n')

        # Observaciones
        f.write('## Observaciones\n\n')
        observations: List[str] = []
        if fallback_reason:
            observations.append(f'- Fallback aplicado: {fallback_reason}')
        for name, v in windows_info.items():
            if v['degrade_pf']:
                observations.append(f'- {name}: PF < 50% del global (posible degradación).')
            if not v['stable_pf'] and not v['degrade_pf']:
                observations.append(f'- {name}: PF fuera de banda de estabilidad.')
            if v['cluster_concentration']:
                observations.append(f'- {name}: Concentración temporal (trades>>tiempo).')
            if abs(v['skew_r_multiple_net']) > 1:
                skew_val = v['skew_r_multiple_net']
                observations.append(f"- {name}: Skew elevado en r (|skew|>1) = {skew_val:.2f}.")
        if not observations:
            observations.append('- Sin señales fuertes de drift/concentración con la muestra actual.')
        f.write('\n'.join(observations) + '\n\n')

        # Recomendaciones
        f.write('## Recomendaciones\n\n')
        recs: List[str] = []
        if any(v['degrade_pf'] for v in windows_info.values()):
            recs.append('- Aplicar throttling o reducción de tamaño hasta confirmar estabilidad adicional.')
        if any(v['cluster_concentration'] for v in windows_info.values()):
            recs.append('- Recolectar más datos en periodos con actividad baja para balancear la muestra.')
        if any(abs(v['skew_r_multiple_net']) > 1 for v in windows_info.values()):
            recs.append('- Revisar distribución de outcomes; posible dependencia de outliers.')
        if not recs:
            recs.append('- Continuar a gating preliminar tras ampliar muestra.')
        f.write('\n'.join(recs) + '\n')

    print(f'Reporte refinado: {report_path}')
    print(f'Flags refinado: {flags_path}')


if __name__ == '__main__':
    main()

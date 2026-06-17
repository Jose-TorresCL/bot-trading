import os
import json
import argparse
from datetime import datetime
from typing import List, Dict, Any

import pandas as pd
import numpy as np
from src.reporting.metrics import profit_factor as calc_profit_factor, max_drawdown as calc_max_dd

"""Walk-Forward / Validación Temporal

Divide el conjunto global de trades de un run en N ventanas temporales consecutivas
ordenadas por exit_time y calcula métricas de estabilidad para cada ventana.

Métricas por ventana:
- trades
- pf_net (wins_sum / abs(losses_sum)) (0.0 si no hay pérdidas)
- winrate_net (% trades con net_pnl > 0)
- expectancy_net (media net_pnl)
- max_dd_net (máximo drawdown intra-ventana)
- r_multiple_median_net (mediana de r_multiple_net)
- cumulative_pnl_net (suma net_pnl)

Flags heurísticos:
- stable_pf: |pf - global_pf|/global_pf <= pf_tolerance (si global_pf>0, else True)
- degrade_pf: pf < global_pf * pf_degradation_factor
- low_trades: trades < min_trades_window
- instability: coeficiente de variación de pf > pf_cv_limit (calculado globalmente)
- drift_detected (global): pf estrictamente decreciente o expectancy estrictamente decreciente.

Outputs:
- summary_walk_forward.md
- walk_forward_flags.json
"""


"""
Nota: Se reutilizan los helpers centralizados de src.reporting.metrics
      para evitar divergencias (profit_factor, max_drawdown).
"""


def compute_window_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    pf = calc_profit_factor(df['net_pnl'])
    winrate = float((df['net_pnl'] > 0).mean() * 100) if not df.empty else 0.0
    expectancy = float(df['net_pnl'].mean()) if not df.empty else 0.0
    max_dd = calc_max_dd(df['net_pnl'])
    r_med = float(df['r_multiple_net'].median()) if 'r_multiple_net' in df.columns and not df.empty else 0.0
    cum_pnl = float(df['net_pnl'].sum())
    return {
        'trades': int(len(df)),
        'pf_net': pf,
        'winrate_net': winrate,
        'expectancy_net': expectancy,
        'max_dd_net': max_dd,
        'r_multiple_median_net': r_med,
        'cumulative_pnl_net': cum_pnl,
        'start_exit_time': df['exit_time'].min() if 'exit_time' in df.columns and not df.empty else None,
        'end_exit_time': df['exit_time'].max() if 'exit_time' in df.columns and not df.empty else None,
    }


def detect_latest_run(base_dir: str) -> str:
    candidates = [d for d in os.listdir(base_dir) if d.startswith('202') and os.path.isdir(os.path.join(base_dir, d))]
    if not candidates:
        raise RuntimeError('No se encontraron runs en ANALISIS')
    return sorted(candidates)[-1]


def load_trades(run_id: str, analysis_root: str) -> pd.DataFrame:
    path = os.path.join(analysis_root, run_id, 'modelo_costos', 'trades_enriched_global.csv')
    if not os.path.isfile(path):
        raise FileNotFoundError(f'No existe trades_enriched_global.csv en {run_id}')
    df = pd.read_csv(path)
    if 'exit_time' in df.columns:
        try:
            df['exit_time'] = pd.to_datetime(df['exit_time'])
        except Exception:
            pass
    return df


def main():
    parser = argparse.ArgumentParser(description='Walk-forward validation de un run')
    parser.add_argument('--run-id', help='ID de run (carpeta en ANALISIS). Si se omite usa el más reciente')
    parser.add_argument('--windows', type=int, default=3, help='Número de ventanas (>=3)')
    parser.add_argument('--analysis-root', default=os.path.join('data', 'backtesting', 'ANALISIS'))
    args = parser.parse_args()

    if args.windows < 3:
        raise ValueError('Se requieren al menos 3 ventanas')

    analysis_root = args.analysis_root
    run_id = args.run_id or detect_latest_run(analysis_root)
    run_dir = os.path.join(analysis_root, run_id, 'modelo_costos')

    df = load_trades(run_id, analysis_root)
    if 'net_pnl' not in df.columns:
        raise ValueError('Columna net_pnl ausente')
    if 'r_multiple_net' not in df.columns:
        # fallback si no estuviera
        df['r_multiple_net'] = 0.0

    # Ordenar por exit_time si disponible
    if 'exit_time' in df.columns:
        df = df.sort_values('exit_time').reset_index(drop=True)

    # Split en ventanas lo más balanceadas posible
    # División uniforme en N ventanas usando numpy.array_split
    indices = np.arange(len(df))
    windows_raw = np.array_split(indices, args.windows) if len(indices) else [np.array([], dtype=int)]
    window_frames: List[pd.DataFrame] = [df.iloc[idxs.tolist()] for idxs in windows_raw]

    # Métrica global para referencia
    global_metrics = compute_window_metrics(df)

    # Parámetros heurísticos
    pf_tolerance = 0.50  # +/-50% respecto al global para considerarlo estable (muestra pequeña)
    pf_degradation_factor = 0.50  # <50% del PF global se considera degradación
    min_trades_window = max(5, int(len(df) * 0.15))  # al menos 15% de trades globales o 5

    results: Dict[str, Any] = {}
    pf_values = []
    expectancy_values = []

    for i, wdf in enumerate(window_frames, start=1):
        metrics = compute_window_metrics(wdf)
        pf_values.append(metrics['pf_net'])
        expectancy_values.append(metrics['expectancy_net'])
        # Flags por ventana
        if global_metrics['pf_net'] > 0:
            stable_pf = abs(metrics['pf_net'] - global_metrics['pf_net']) / global_metrics['pf_net'] <= pf_tolerance
            degrade_pf = metrics['pf_net'] < global_metrics['pf_net'] * pf_degradation_factor
        else:
            stable_pf = True
            degrade_pf = False
        low_trades = metrics['trades'] < min_trades_window

        results[f'ventana_{i}'] = {
            **metrics,
            'stable_pf': stable_pf,
            'degrade_pf': degrade_pf,
            'low_trades': low_trades,
        }

    # Drift / estabilidad global
    drift_pf = all(pf_values[i] < pf_values[i-1] for i in range(1, len(pf_values))) and len(pf_values) >= 3
    drift_expectancy = all(expectancy_values[i] < expectancy_values[i-1] for i in range(1, len(expectancy_values))) and len(expectancy_values) >= 3

    # Coeficiente variación PF
    import math
    if len(pf_values) > 1:
        mean_pf = sum(pf_values)/len(pf_values)
        std_pf = math.sqrt(sum((x-mean_pf)**2 for x in pf_values)/(len(pf_values)-1)) if len(pf_values) > 1 else 0.0
        pf_cv = std_pf/mean_pf if mean_pf else 0.0
    else:
        pf_cv = 0.0

    pf_cv_limit = 0.75  # alta variabilidad si CV > 0.75
    instability = pf_cv > pf_cv_limit

    flags = {
        'run_id': run_id,
        'generated_utc': datetime.utcnow().isoformat() + 'Z',
        'global_metrics': global_metrics,
        'params': {
            'pf_tolerance': pf_tolerance,
            'pf_degradation_factor': pf_degradation_factor,
            'min_trades_window': min_trades_window,
            'pf_cv_limit': pf_cv_limit
        },
        'windows': results,
        'drift': {
            'pf_monotonic_decrease': drift_pf,
            'expectancy_monotonic_decrease': drift_expectancy,
            'pf_cv': pf_cv,
            'instability': instability
        }
    }

    # Guardar JSON
    out_json = os.path.join(run_dir, 'walk_forward_flags.json')
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(flags, f, ensure_ascii=False, indent=2, default=str)

    # Reporte MD
    out_md = os.path.join(run_dir, 'summary_walk_forward.md')
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('# Walk-Forward Validation\n\n')
        f.write(f'Run: {run_id}  \nGenerado: {datetime.utcnow().isoformat()}Z\n\n')
        f.write('## Métricas Globales\n\n')
        f.write('| trades | pf_net | winrate_net | max_dd_net | expectancy_net | r_multiple_median_net | cumulative_pnl_net |\n')
        f.write('|---|---|---|---|---|---|---|\n')
        f.write(f"| {global_metrics['trades']} | {global_metrics['pf_net']:.4f} | {global_metrics['winrate_net']:.2f} | {global_metrics['max_dd_net']:.4f} | {global_metrics['expectancy_net']:.4f} | {global_metrics['r_multiple_median_net']:.4f} | {global_metrics['cumulative_pnl_net']:.4f} |\n\n")

        f.write('## Ventanas\n\n')
        f.write('| ventana | trades | start_exit | end_exit | pf_net | winrate_net | max_dd_net | expectancy_net | r_multiple_median_net | cumulative_pnl_net | stable_pf | degrade_pf | low_trades |\n')
        f.write('|---|---|---|---|---|---|---|---|---|---|---|---|---|\n')
        for name, m in results.items():
            f.write('|' + ' | '.join([
                name,
                str(m['trades']),
                str(m['start_exit_time']),
                str(m['end_exit_time']),
                f"{m['pf_net']:.4f}",
                f"{m['winrate_net']:.2f}",
                f"{m['max_dd_net']:.4f}",
                f"{m['expectancy_net']:.4f}",
                f"{m['r_multiple_median_net']:.4f}",
                f"{m['cumulative_pnl_net']:.4f}",
                str(m['stable_pf']),
                str(m['degrade_pf']),
                str(m['low_trades'])
            ]) + '|\n')
        f.write('\n')

        # Observaciones
        f.write('## Observaciones\n\n')
        obs: List[str] = []
        if flags['drift']['pf_monotonic_decrease']:
            obs.append('- Drift negativo en PF (monótono decreciente).')
        if flags['drift']['expectancy_monotonic_decrease']:
            obs.append('- Drift negativo en Expectancy (monótono decreciente).')
        if flags['drift']['instability']:
            obs.append(f"- Alta variabilidad en PF (CV={flags['drift']['pf_cv']:.2f} > {pf_cv_limit}).")
        for wname, m in results.items():
            if m['degrade_pf']:
                obs.append(f"- {wname}: PF significativamente inferior (< {pf_degradation_factor*100:.0f}% del global).")
            if (not m['stable_pf']) and (not m['degrade_pf']):
                obs.append(f"- {wname}: PF fuera de banda de estabilidad pero no degradado severamente.")
            if m['low_trades']:
                obs.append(f"- {wname}: pocos trades (n={m['trades']}) reduce confiabilidad.")
        if not obs:
            obs.append('- No se detectaron señales fuertes de drift con la muestra actual.')
        f.write('\n'.join(obs) + '\n\n')

        # Recomendaciones
        f.write('## Recomendaciones\n\n')
        recs: List[str] = []
        if flags['drift']['pf_monotonic_decrease'] or flags['drift']['expectancy_monotonic_decrease']:
            recs.append('- Considerar revisar parámetros / condiciones de entrada (drift detectado).')
        if flags['drift']['instability']:
            recs.append('- Aumentar muestra o aplicar smoothing de sizing hasta estabilizar PF.')
        if any(m['degrade_pf'] for m in results.values()):
            recs.append('- Aplicar cooldown o reducción de riesgo en ventanas degradadas.')
        if all(m['stable_pf'] for m in results.values()):
            recs.append('- Continuar a fase de gating; estabilidad preliminar aceptable dado tamaño de muestra.')
        if not recs:
            recs.append('- Recolectar más datos antes de decisiones estructurales.')
        f.write('\n'.join(recs) + '\n')

    print(f'Reporte walk-forward: {out_md}')
    print(f'Flags walk-forward: {out_json}')


if __name__ == '__main__':
    main()

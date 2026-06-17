import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List
from src.reporting.metrics import profit_factor as calc_profit_factor
from src.reporting.metrics import max_drawdown as _mdd_helper

import pandas as pd


# ------------------------------------------------------------
# Drop Tests Script
# ------------------------------------------------------------
"""Genera análisis de sensibilidad excluyendo cada símbolo del portafolio.

Para un run específico (carpeta en data/backtesting/ANALISIS/<run_id>/modelo_costos):
- Lee trades_enriched_global.csv
- Calcula métricas baseline: PF_net, max_dd_net, expectancy_net, total_pnl_net y pnl_share por símbolo.
- Para cada símbolo, recalcula métricas sin ese símbolo y cuantifica deltas.
- Genera:
    drop_tests_report.md   (tabla comparativa + observaciones + recomendaciones)
    drop_tests_flags.json  (estructura JSON con flags de fragilidad / valor aportado)

Definiciones:
- PF_net = sum(net_pnl > 0)/abs(sum(net_pnl < 0)); si no hay pérdidas => 0.0 (evita infinito artificial)
- Expectancy_net = mean(net_pnl)
- Max_dd_net = Máxima caída (peak -> trough) del equity acumulado ordenado por exit_time
- pnl_share = (suma net_pnl símbolo / suma net_pnl global) * 100

Flags (heurísticos, versión 1):
- pf_improvement_threshold = 0.05 (5%)
- dd_reduction_threshold = 0.05 (5%)
- low_pnl_share_threshold = 0.10 (10%)
- min_trades_reliable = 30

Un símbolo se marca "fragile" si su remoción mejora PF_net o reduce Max DD por encima de los umbrales y además tiene baja participación de PnL o pocos trades.
"""


def calc_max_dd(net_pnls: pd.Series, times: pd.Series) -> float:
    if net_pnls.empty:
        return 0.0
    # Ordenar por tiempo de salida si se puede para reproducibilidad
    try:
        if times.notna().all():
            order = times.argsort().to_numpy()
            pnls = net_pnls.iloc[order]
        else:
            pnls = net_pnls
    except Exception:
        pnls = net_pnls
    # El helper devuelve drawdown como negativo, reportamos magnitud positiva
    return float(abs(_mdd_helper(pnls)))


def compute_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    pf = calc_profit_factor(df['net_pnl'])
    expectancy = float(df['net_pnl'].mean()) if not df.empty else 0.0
    max_dd = calc_max_dd(df['net_pnl'], df['exit_time'])
    total_pnl = float(df['net_pnl'].sum())
    return {
        'pf_net': pf,
        'expectancy_net': expectancy,
        'max_dd_net': max_dd,
        'total_pnl_net': total_pnl,
        'trades': int(len(df))
    }


def load_trades(run_id: str, base_dir: str) -> pd.DataFrame:
    trades_path = os.path.join(base_dir, run_id, 'modelo_costos', 'trades_enriched_global.csv')
    if not os.path.isfile(trades_path):
        raise FileNotFoundError(f'No existe trades_enriched_global.csv en run {run_id}')
    df = pd.read_csv(trades_path)
    # Parse exit_time si existe
    if 'exit_time' in df.columns:
        try:
            df['exit_time'] = pd.to_datetime(df['exit_time'])
        except Exception:
            pass
    return df


def detect_latest_run(base_dir: str) -> str:
    runs = []
    for name in os.listdir(base_dir):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path) and name.startswith('202'):
            runs.append(name)
    if not runs:
        raise RuntimeError('No se encontraron runs en ANALISIS')
    return sorted(runs)[-1]


def format_float(x: float, nd: int = 6) -> str:
    return f'{x:.6f}'


def main():
    parser = argparse.ArgumentParser(description='Drop tests de símbolos')
    parser.add_argument('--run-id', help='ID de run (carpeta de ANALISIS). Si no se pasa se usa el último')
    parser.add_argument('--analysis-root', default=os.path.join('data', 'backtesting', 'ANALISIS'))
    args = parser.parse_args()

    analysis_root = args.analysis_root
    run_id = args.run_id or detect_latest_run(analysis_root)
    run_dir = os.path.join(analysis_root, run_id, 'modelo_costos')

    df = load_trades(run_id, analysis_root)
    if 'symbol' not in df.columns or 'net_pnl' not in df.columns:
        raise ValueError('El dataset global no contiene columnas obligatorias: symbol, net_pnl')

    symbols = sorted(df['symbol'].unique())

    baseline = compute_metrics(df)

    # pnl share baseline por símbolo
    total_pnl = baseline['total_pnl_net'] if baseline['total_pnl_net'] != 0 else 1.0
    pnl_share = df.groupby('symbol')['net_pnl'].sum() / total_pnl * 100.0

    # thresholds
    pf_improvement_threshold = 0.05
    dd_reduction_threshold = 0.05
    low_pnl_share_threshold = 0.10  # 10%
    min_trades_reliable = 30

    rows = []
    flags: Dict[str, Any] = {
        'run_id': run_id,
        'generated_utc': datetime.utcnow().isoformat() + 'Z',
        'baseline': baseline,
        'thresholds': {
            'pf_improvement_threshold': pf_improvement_threshold,
            'dd_reduction_threshold': dd_reduction_threshold,
            'low_pnl_share_threshold': low_pnl_share_threshold,
            'min_trades_reliable': min_trades_reliable
        },
        'symbols': {}
    }

    for sym in symbols:
        df_drop = df[df['symbol'] != sym]
        metrics_drop = compute_metrics(df_drop)
        # deltas relativos
        delta_pf = metrics_drop['pf_net'] - baseline['pf_net']
        delta_expectancy = metrics_drop['expectancy_net'] - baseline['expectancy_net']
        delta_total_pnl = metrics_drop['total_pnl_net'] - baseline['total_pnl_net']
        delta_max_dd = metrics_drop['max_dd_net'] - baseline['max_dd_net']  # negativo mejora dd

        # individuales
        df_sym = df[df['symbol'] == sym]
        indiv = compute_metrics(df_sym)
        indiv['pnl_share_pct'] = float(pnl_share.get(sym, 0.0))

        # flags heurísticos
        pf_improvement = (baseline['pf_net'] > 0 and metrics_drop['pf_net'] > baseline['pf_net'] * (1 + pf_improvement_threshold))
        dd_improvement = (baseline['max_dd_net'] > 0 and metrics_drop['max_dd_net'] < baseline['max_dd_net'] * (1 - dd_reduction_threshold))
        low_pnl_share = indiv['pnl_share_pct'] < (low_pnl_share_threshold * 100)
        few_trades = indiv['trades'] < min_trades_reliable

        fragile = (pf_improvement or dd_improvement) and (low_pnl_share or few_trades)
        value_add = (metrics_drop['pf_net'] < baseline['pf_net'] * (1 - pf_improvement_threshold)) or (metrics_drop['max_dd_net'] > baseline['max_dd_net'] * (1 + dd_reduction_threshold))

        reasons: List[str] = []
        if pf_improvement:
            reasons.append('remocion_mejora_pf')
        if dd_improvement:
            reasons.append('remocion_reduce_dd')
        if low_pnl_share:
            reasons.append('baja_participacion_pnl')
        if few_trades:
            reasons.append('pocos_trades')
        if value_add:
            reasons.append('valor_agregado_pf_ou_dd')

        flags['symbols'][sym] = {
            'individual': indiv,
            'drop_scenario': metrics_drop,
            'deltas': {
                'delta_pf': delta_pf,
                'delta_expectancy': delta_expectancy,
                'delta_max_dd': delta_max_dd,
                'delta_total_pnl': delta_total_pnl
            },
            'flags': {
                'fragile': fragile,
                'value_add': value_add,
                'pf_improvement_if_removed': pf_improvement,
                'dd_improvement_if_removed': dd_improvement,
                'low_pnl_share': low_pnl_share,
                'few_trades': few_trades
            },
            'reasons': reasons
        }

        rows.append({
            'drop_symbol': sym,
            'remaining_trades': metrics_drop['trades'],
            'pf_net_without': metrics_drop['pf_net'],
            'max_dd_net_without': metrics_drop['max_dd_net'],
            'expectancy_net_without': metrics_drop['expectancy_net'],
            'total_pnl_net_without': metrics_drop['total_pnl_net'],
            'delta_pf': delta_pf,
            'delta_max_dd': delta_max_dd,
            'delta_expectancy': delta_expectancy,
            'delta_total_pnl': delta_total_pnl,
            'pnl_share_pct_symbol': indiv['pnl_share_pct'],
            'symbol_trades': indiv['trades']
        })

    # Ordenar tabla por mejora en PF (descendente)
    rows_sorted = sorted(rows, key=lambda r: r['delta_pf'], reverse=True)

    # Crear carpeta de salida
    out_dir = os.path.join(run_dir, 'drop_tests')
    os.makedirs(out_dir, exist_ok=True)

    # Guardar JSON flags
    json_path = os.path.join(out_dir, 'drop_tests_flags.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(flags, f, ensure_ascii=False, indent=2)

    # Reporte MD
    report_path = os.path.join(out_dir, 'drop_tests_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f'# Drop Tests Report\n\n')
        f.write(f'Run: {run_id}  \nGenerado: {datetime.utcnow().isoformat()}Z\n\n')
        f.write('## Baseline (Todos los símbolos)\n\n')
        f.write('| trades | pf_net | max_dd_net | expectancy_net | total_pnl_net |\n')
        f.write('|---|---|---|---|---|\n')
        f.write(f"| {baseline['trades']} | {format_float(baseline['pf_net'],4)} | {format_float(baseline['max_dd_net'],4)} | {format_float(baseline['expectancy_net'],4)} | {format_float(baseline['total_pnl_net'],4)} |\n\n")

        f.write('## Tabla de Escenarios (Removiendo un símbolo)\n\n')
        f.write('| drop_symbol | remaining_trades | pf_net_without | Δpf | max_dd_net_without | Δmax_dd | expectancy_net_without | Δexpectancy | total_pnl_net_without | Δtotal_pnl | pnl_share_pct_symbol | symbol_trades |\n')
        f.write('|---|---|---|---|---|---|---|---|---|---|---|---|\n')
        for r in rows_sorted:
            f.write('|' + ' | '.join([
                r['drop_symbol'],
                str(r['remaining_trades']),
                format_float(r['pf_net_without'],4),
                format_float(r['delta_pf'],4),
                format_float(r['max_dd_net_without'],4),
                format_float(r['delta_max_dd'],4),
                format_float(r['expectancy_net_without'],4),
                format_float(r['delta_expectancy'],4),
                format_float(r['total_pnl_net_without'],4),
                format_float(r['delta_total_pnl'],4),
                format_float(r['pnl_share_pct_symbol'],2),
                str(r['symbol_trades'])
            ]) + '|\n')
        f.write('\n')

        # Observaciones automáticas
        f.write('## Observaciones\n\n')
        obs_lines: List[str] = []
        for sym, info in flags['symbols'].items():
            fl = info['flags']
            if fl['fragile']:
                obs_lines.append(f"- {sym}: Remoción mejora PF o DD y símbolo con baja robustez (reasons={info['reasons']})")
            elif fl['value_add']:
                obs_lines.append(f"- {sym}: Aporta valor (su remoción degrada PF o aumenta DD).")
            else:
                obs_lines.append(f"- {sym}: Neutro en PF/DD dentro de umbrales actuales.")
        if not obs_lines:
            obs_lines.append('- No se detectaron efectos significativos con umbrales actuales.')
        f.write('\n'.join(obs_lines) + '\n\n')

        # Recomendaciones basadas en banderas
        f.write('## Recomendaciones\n\n')
        recs: List[str] = []
        frag_symbols = [s for s, v in flags['symbols'].items() if v['flags']['fragile']]
        if frag_symbols:
            recs.append(f"- Considerar pausar / recolectar más datos de: {', '.join(frag_symbols)} antes de promoción.")
        value_add_syms = [s for s, v in flags['symbols'].items() if v['flags']['value_add']]
        if value_add_syms:
            recs.append(f"- Mantener y priorizar en análisis de estabilidad: {', '.join(value_add_syms)}.")
        low_share_syms = [s for s, v in flags['symbols'].items() if v['flags']['low_pnl_share']]
        if low_share_syms:
            recs.append(f"- Re-evaluar asignación de capital a símbolos de baja contribución: {', '.join(low_share_syms)}.")
        few_trades_syms = [s for s, v in flags['symbols'].items() if v['flags']['few_trades']]
        if few_trades_syms:
            recs.append(f"- Aumentar muestra (más trades) para: {', '.join(few_trades_syms)} para robustecer inferencias.")
        if not recs:
            recs.append('- Sin acciones críticas inmediatas; proceder con walk-forward.')
        f.write('\n'.join(recs) + '\n')

    print(f'Reporte: {report_path}')
    print(f'Flags:   {json_path}')


if __name__ == '__main__':
    main()

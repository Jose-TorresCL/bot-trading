"""Aplicar modelo de costos trade-a-trade (v0.2).

Salida solicitada:
 - metrics_cost_adjusted.csv (UNA FILA POR TRADE) columnas:
         symbol, timestamp, price, size, notional, commission_paid, slippage_cost, gross_pnl, net_pnl
 - summary_cost_model.md con métricas netas vs brutas por símbolo:
         PF neto vs bruto, winrate neto vs bruto, expectancy neta vs bruta, impacto porcentual costos.
 - README.md con parámetros (fee_pct, slippage_pct), fecha y versión.

Ubicación: ANALISIS/<timestamp>/modelo_costos/
    (donde <timestamp> = nombre de la carpeta del run, p.ej. 2025-09-07_00-53)

Supuestos:
 - size=1 por defecto; opcional inferencia (--infer-qty) usando pnl y diferencia de precios.
 - price base para notional = entry_price; costos sobre notional.
 - commission_paid = notional * fee_pct (fee_pct ya incluye ida+vuelta).
 - slippage_cost = notional * slippage_pct.
 - gross_pnl = columna pnl original.
 - net_pnl = gross_pnl - commission_paid - slippage_cost.

CLI (v0.2):
    --fee-pct / --fee-bps (compat)
    --slippage-pct / --slip-bps (compat)
    --analisis-dir (default data/backtesting/ANALISIS)
    --infer-qty
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import math
import datetime as dt

import pandas as pd


@dataclass
class CostParams:
    fee_pct: float  # porcentaje total round-trip (0.001 = 0.1%)
    slippage_pct: float  # porcentaje de slippage sobre entrada
    infer_qty: bool = False


def cargar_trades_symbol(run_dir: Path, symbol: str) -> Optional[pd.DataFrame]:
    trades_path = run_dir / symbol / 'trades.csv'
    if not trades_path.exists():
        return None
    try:
        df = pd.read_csv(trades_path)
        if df.empty:
            return None
        return df
    except Exception:
        return None


def inferir_qty(row) -> float:
    # Intento de inferencia: pnl = (exit - entry) * qty para long
    #                        pnl = (entry - exit) * qty para short
    side = row.get('side')
    try:
        entry = float(row.get('entry_price'))
        exit_ = float(row.get('exit_price'))
        pnl = float(row.get('pnl'))
    except Exception:
        return 1.0
    diff = exit_ - entry
    if diff == 0:
        return 1.0
    if side == 'long':
        qty = pnl / diff if diff != 0 else 1.0
    else:  # short
        qty = -pnl / diff if diff != 0 else 1.0
    if not math.isfinite(qty) or qty <= 0:
        return 1.0
    return qty


def aplicar_costos(df: pd.DataFrame, params: CostParams) -> pd.DataFrame:
    out = df.copy()
    for c in ['entry_price','pnl','entry_time']:
        if c not in out.columns:
            raise ValueError(f"Falta columna requerida '{c}' en trades.csv")
    if params.infer_qty and 'exit_price' in out.columns:
        out['size'] = out.apply(inferir_qty, axis=1)
    else:
        out['size'] = 1.0
    out['price'] = out['entry_price']
    out['notional'] = out['price'] * out['size']
    out['commission_paid'] = out['notional'] * params.fee_pct
    out['slippage_cost'] = out['notional'] * params.slippage_pct
    out['gross_pnl'] = out['pnl']
    out['net_pnl'] = out['gross_pnl'] - out['commission_paid'] - out['slippage_cost']
    out['timestamp'] = out['exit_time'] if 'exit_time' in out.columns else out['entry_time']
    keep = ['timestamp','price','size','notional','commission_paid','slippage_cost','gross_pnl','net_pnl','side','entry_time','exit_time']
    out = out[[c for c in keep if c in out.columns]]
    return out


def agregar_metricas(df_cost: pd.DataFrame) -> Dict[str, Any]:
    gross_pnl_total = df_cost['gross_pnl'].sum()
    net_pnl_total = df_cost['net_pnl'].sum()
    commissions = df_cost['commission_paid'].sum()
    slippage = df_cost['slippage_cost'].sum()
    wins_g = df_cost[df_cost['gross_pnl'] > 0]['gross_pnl'].sum()
    losses_g = df_cost[df_cost['gross_pnl'] <= 0]['gross_pnl'].sum()
    wins_n = df_cost[df_cost['net_pnl'] > 0]['net_pnl'].sum()
    losses_n = df_cost[df_cost['net_pnl'] <= 0]['net_pnl'].sum()
    pf_g = (wins_g/abs(losses_g)) if losses_g < 0 else 0
    pf_n = (wins_n/abs(losses_n)) if losses_n < 0 else 0
    winrate_g = (df_cost['gross_pnl'] > 0).mean()*100 if not df_cost.empty else 0
    winrate_n = (df_cost['net_pnl'] > 0).mean()*100 if not df_cost.empty else 0
    expectancy_g = df_cost['gross_pnl'].mean() if not df_cost.empty else 0
    expectancy_n = df_cost['net_pnl'].mean() if not df_cost.empty else 0
    impact = ((gross_pnl_total - net_pnl_total)/gross_pnl_total*100) if gross_pnl_total != 0 else 0
    return {
        'trades': len(df_cost),
        'gross_pnl_total': round(gross_pnl_total,6),
        'net_pnl_total': round(net_pnl_total,6),
        'commissions': round(commissions,6),
        'slippage': round(slippage,6),
        'impact_cost_pct': round(impact,4),
        'gross_pf': round(pf_g,6),
        'net_pf': round(pf_n,6),
        'winrate_gross': round(winrate_g,4),
        'winrate_net': round(winrate_n,4),
        'expectancy_gross': round(expectancy_g,6),
        'expectancy_net': round(expectancy_n,6)
    }


def guardar_readme(out_dir: Path, params: CostParams, run_dir: Path):
    content = [
        '# README Modelo de Costos',
        f'- Versión script: 0.2',
        f'- Run origen: {run_dir.name}',
        f'- Fecha de generación: {dt.datetime.utcnow().isoformat()}Z',
        f'- Parámetros: fee_pct={params.fee_pct} ({params.fee_pct*100:.4f}%), slippage_pct={params.slippage_pct} ({params.slippage_pct*100:.4f}%), infer_qty={params.infer_qty}',
        '',
        '## Fórmulas',
        '- notional = entry_price * size',
        '- commission_paid = notional * fee_pct',
        '- slippage_cost = notional * slippage_pct',
        '- net_pnl = gross_pnl - commission_paid - slippage_cost',
        '',
        '## Campos principales CSV',
        '- symbol, timestamp, price, size, notional, commission_paid, slippage_cost, gross_pnl, net_pnl',
        '',
        '## Notas',
        '- Ajustar fee/slippage para escenarios de stress.',
        '- Implementar tamaños reales cuando se disponga de volumen.'
    ]
    (out_dir / 'README.md').write_text('\n'.join(content), encoding='utf-8')


def guardar_resumen_markdown(out_dir: Path, params: CostParams, metrics_por_symbol: Dict[str, Dict[str, Any]]):
    lines = [
        '# Resumen Modelo de Costos (v0.2)',
        '',
        f'- Fecha cálculo: {dt.datetime.utcnow().isoformat()}Z',
        f'- fee_pct: {params.fee_pct} ({params.fee_pct*100:.4f}%)',
        f'- slippage_pct: {params.slippage_pct} ({params.slippage_pct*100:.4f}%)',
        f'- Inferir size: {"sí" if params.infer_qty else "no (size=1)"}',
        '',
        '## Métricas por símbolo',
        '',
        '| Symbol | Trades | Gross PnL | Net PnL | PF Bruto | PF Neto | Winrate Bruto % | Winrate Neto % | Expect Bruta | Expect Neta | Impacto % |',
        '|--------|--------|-----------|---------|----------|---------|-----------------|----------------|--------------|-------------|-----------|'
    ]
    for sym, m in metrics_por_symbol.items():
        lines.append(f"| {sym} | {m['trades']} | {m['gross_pnl_total']} | {m['net_pnl_total']} | {m['gross_pf']} | {m['net_pf']} | {m['winrate_gross']} | {m['winrate_net']} | {m['expectancy_gross']} | {m['expectancy_net']} | {m['impact_cost_pct']} |")
    if metrics_por_symbol:
        import pandas as _pd
        dfm = _pd.DataFrame.from_dict(metrics_por_symbol, orient='index')
        gross_sum = dfm['gross_pnl_total'].sum()
        net_sum = dfm['net_pnl_total'].sum()
        wins_g = dfm[dfm['gross_pnl_total']>0]['gross_pnl_total'].sum()
        losses_g = dfm[dfm['gross_pnl_total']<0]['gross_pnl_total'].sum()
        wins_n = dfm[dfm['net_pnl_total']>0]['net_pnl_total'].sum()
        losses_n = dfm[dfm['net_pnl_total']<0]['net_pnl_total'].sum()
        pf_g = (wins_g/abs(losses_g)) if losses_g < 0 else 0
        pf_n = (wins_n/abs(losses_n)) if losses_n < 0 else 0
        impact = ((gross_sum - net_sum)/gross_sum*100) if gross_sum!=0 else 0
        lines += [
            '',
            '## Agregado',
            f'- PnL bruto total: {round(gross_sum,6)}',
            f'- PnL neto total: {round(net_sum,6)}',
            f'- PF bruto agregado: {round(pf_g,6)}',
            f'- PF neto agregado: {round(pf_n,6)}',
            f'- Impacto costos agregado: {round(impact,4)}%',
            '',
            '## Observaciones',
            '- Revisar símbolos con mayor impacto porcentual.',
            '- Expectancy neta negativa => ajustar filtros o tamaño.',
            '- Gran gap PF bruto/neto => fricción transaccional elevada.'
        ]
    (out_dir / 'summary_cost_model.md').write_text('\n'.join(lines), encoding='utf-8')


def detect_symbols(run_dir: Path) -> List[str]:
    symbols = []
    for p in run_dir.glob('*'):
        if p.is_dir() and (p / 'trades.csv').exists():
            symbols.append(p.name)
    return symbols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True, help='Carpeta del run (contiene subcarpetas por símbolo)')
    ap.add_argument('--analisis-dir', default='data/backtesting/ANALISIS', help='Carpeta ANALISIS')
    ap.add_argument('--fee-pct', type=float, default=None, help='Comisión total round-trip en decimal (0.001=0.1%)')
    ap.add_argument('--slippage-pct', type=float, default=None, help='Slippage en decimal (0.0005=0.05%)')
    ap.add_argument('--fee-bps', type=float, default=None, help='(Compat) comisión en bps')
    ap.add_argument('--slip-bps', type=float, default=None, help='(Compat) slippage en bps')
    ap.add_argument('--infer-qty', action='store_true', help='Inferir size a partir de pnl')
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        raise SystemExit(f"Run dir no existe: {run_dir}")

    if args.fee_pct is not None:
        fee_pct = args.fee_pct
    elif args.fee_bps is not None:
        fee_pct = args.fee_bps / 10_000.0
    else:
        fee_pct = 0.001
    if args.slippage_pct is not None:
        slippage_pct = args.slippage_pct
    elif args.slip_bps is not None:
        slippage_pct = args.slip_bps / 10_000.0
    else:
        slippage_pct = 0.0005

    params = CostParams(fee_pct=fee_pct, slippage_pct=slippage_pct, infer_qty=args.infer_qty)

    analisis_dir = Path(args.analisis_dir)
    analisis_dir.mkdir(parents=True, exist_ok=True)
    ts_dir = analisis_dir / run_dir.name / 'modelo_costos'
    ts_dir.mkdir(parents=True, exist_ok=True)

    symbols = detect_symbols(run_dir)
    if not symbols:
        raise SystemExit('No se detectaron símbolos con trades.csv')

    metrics_por_symbol: Dict[str, Dict[str, Any]] = {}
    trades_frames: List[pd.DataFrame] = []
    for sym in symbols:
        raw = cargar_trades_symbol(run_dir, sym)
        if raw is None:
            continue
        try:
            cost_df = aplicar_costos(raw, params)
        except ValueError as e:
            print(f"Saltando {sym}: {e}")
            continue
        cost_df.insert(0,'symbol', sym)
        trades_frames.append(cost_df)
        metrics_por_symbol[sym] = agregar_metricas(cost_df)

    if not trades_frames:
        raise SystemExit('No se generaron trades con costos.')

    trades_all = pd.concat(trades_frames, ignore_index=True)
    final_cols = ['symbol','timestamp','price','size','notional','commission_paid','slippage_cost','gross_pnl','net_pnl']
    for c in final_cols:
        if c not in trades_all.columns:
            trades_all[c] = None
    trades_all = trades_all[final_cols]
    metrics_path = ts_dir / 'metrics_cost_adjusted.csv'
    trades_all.to_csv(metrics_path, index=False)
    guardar_resumen_markdown(ts_dir, params, metrics_por_symbol)
    guardar_readme(ts_dir, params, run_dir)
    print(f"Modelo de costos aplicado. Archivos en: {ts_dir}")


if __name__ == '__main__':
    main()

"""run_backtest_15m.py
Orquesta un backtest multi-símbolo usando el maestro 15m construido previamente.

Flujo:
 1. Carga maestro 15m
 2. Filtra por símbolos solicitados (default: BTCUSDT,ETHUSDT,BNBUSDT,WLDUSDT)
 3. Para cada símbolo: limpia datos, ejecuta backtesting, guarda resultados en run_dir timestamped
 4. Genera summary.csv consolidado y estado_resumido base
 5. (Opcional) Aplica modelo de costos si flag --apply-cost-model

Uso:
  python scripts/run_backtest_15m.py --maestro data/historiales/historial_trading_maestro_15m.csv \
       --symbols BTCUSDT,ETHUSDT,BNBUSDT,WLDUSDT --days 5 --run-tag 15m_test --apply-cost-model
"""
from __future__ import annotations
import sys, os, json, argparse
from pathlib import Path
from datetime import datetime, UTC
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

try:
    from src.core.backtesting import backtesting_legacy, guardar_resultados_por_par, limpiar_ohlcv
except ModuleNotFoundError:
    from core.backtesting import backtesting_legacy, guardar_resultados_por_par, limpiar_ohlcv  # type: ignore

RUN_BASE = Path('data') / 'backtesting'

def load_maestro(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if 'timestamp' not in df.columns:
        raise ValueError('Maestro sin columna timestamp')
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
    df = df.dropna(subset=['timestamp'])
    return df

def filter_days(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if days <= 0:
        return df
    end = df['timestamp'].max()
    cutoff = end - pd.Timedelta(days=days)
    return df[df['timestamp'] >= cutoff].copy()

def main(maestro: str, symbols: str, days: int, run_tag: str, apply_cost_model: bool):
    df_master = load_maestro(Path(maestro))
    symbols_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    ts_run = datetime.now(tz=UTC).strftime('%Y-%m-%d_%H-%M-%S')
    run_dir = RUN_BASE / ts_run
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for sym in symbols_list:
        dsi = df_master[df_master['symbol'] == sym].sort_values('timestamp')
        if dsi.empty:
            print(f"[WARN] Sin datos para {sym}, se omite")
            continue
        dsub = filter_days(dsi, days)
        dsub = limpiar_ohlcv(dsub)
        bt_res = backtracking = backtesting_legacy(dsub, config_obj=None)
        if isinstance(bt_res, tuple) and len(bt_res) == 3:
            resultados, resumen, trades_enriched = bt_res
        else:
            resultados, resumen = bt_res
            trades_enriched = []
        periodo_label = 'full' if days == 0 else f"{days}d"
        out = guardar_resultados_por_par(sym, periodo_label, resultados, resumen, run_dir=str(run_dir), trades_enriched=trades_enriched)
        resumen_line = {
            'symbol': sym,
            'trades': len(resultados),
            'winrate': resumen.get('winrate'),
            'profit_factor': resumen.get('profit_factor'),
            'expectancy': resumen.get('expectancy'),
            'max_drawdown': resumen.get('max_drawdown'),
            'results_path': out.get('resultados_file')
        }
        summary_rows.append(resumen_line)

    # Generar summary.csv
    if summary_rows:
        df_summary = pd.DataFrame(summary_rows)
        df_summary.to_csv(run_dir / 'summary.csv', index=False)

    # Crear estado_resumido.md base
    estado_path = run_dir / 'estado_resumido.md'
    with open(estado_path, 'w', encoding='utf-8') as fh:
        fh.write(f"# Estado Resumido Run {ts_run}\n\n")
        fh.write(f"Símbolos: {', '.join([r['symbol'] for r in summary_rows])}\n\n")
        for r in summary_rows:
            fh.write(f"- {r['symbol']}: PF={r['profit_factor']} Winrate={r['winrate']} Trades={r['trades']}\n")

    # Aplicar modelo de costos si se solicita
    if apply_cost_model and summary_rows:
        import subprocess, sys as _sys
        analisis_dir = RUN_BASE / 'ANALISIS'
        analisis_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            _sys.executable,
            'scripts/aplicar_modelo_costos.py',
            '--run-dir', str(run_dir),
            '--analisis-dir', str(analisis_dir),
            '--fee-pct', '0.001',
            '--slippage-pct', '0.0005'
        ]
        print('Ejecutando modelo de costos:', ' '.join(cmd))
        try:
            subprocess.run(cmd, check=True)
            print("Modelo de costos aplicado.")
        except subprocess.CalledProcessError as e:
            print(f"[WARN] Falló modelo de costos: {e}")

    print(f"Run completo en {run_dir}")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--maestro', type=str, default='data/historiales/historial_trading_maestro_15m.csv')
    p.add_argument('--symbols', type=str, default='BTCUSDT,ETHUSDT,BNBUSDT,WLDUSDT')
    p.add_argument('--days', type=int, default=5, help='Número de días recientes a usar (0 = todo)')
    p.add_argument('--run-tag', type=str, default='15m_batch')
    p.add_argument('--apply-cost-model', action='store_true')
    args = p.parse_args()
    main(args.maestro, args.symbols, args.days, args.run_tag, args.apply_cost_model)
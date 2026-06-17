"""verificar_maestro_15m.py
Genera un reporte de consistencia sobre un maestro OHLCV 15m.
Checks:
 1) Conteo por símbolo y cobertura
 2) Timestamps (unicidad, rango global, alineación grid 15m)
 3) Gaps > 2 intervalos (delta > 30m) por símbolo
 4) Calidad OHLCV (NaNs, high<low, valores negativos / volumen negativo)
 5) Resumen final con OK/FAIL y recomendación

Uso:
  python scripts/verificar_maestro_15m.py --file data/historiales/historial_trading_maestro_15m.csv --out data/historiales/validacion_maestro_15m.md
"""
from __future__ import annotations
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
from datetime import timezone

DEF_INTERVAL_SECONDS = 900  # 15m


def leer(file: Path) -> pd.DataFrame:
    df = pd.read_csv(file)
    if 'timestamp' not in df.columns:
        raise ValueError("Archivo sin columna timestamp")
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
    df = df.dropna(subset=['timestamp'])
    # normalizar columnas esperadas
    for c in ['open','high','low','close','volume']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def conteo_y_cobertura(df: pd.DataFrame):
    global_min = df['timestamp'].min()
    global_max = df['timestamp'].max()
    span_global = (global_max - global_min).total_seconds()
    rows = []
    for sym, g in df.groupby('symbol'):
        min_s = g['timestamp'].min()
        max_s = g['timestamp'].max()
        span_sym = (max_s - min_s).total_seconds()
        cobertura = (span_sym / span_global * 100) if span_global > 0 else 0
        rows.append({
            'symbol': sym,
            'rows': len(g),
            'min': min_s,
            'max': max_s,
            'cobertura_pct': cobertura
        })
    return rows, global_min, global_max


def verificar_timestamps(df: pd.DataFrame):
    dup_counts = {sym: int(g.duplicated(subset=['timestamp']).sum()) for sym, g in df.groupby('symbol')}
    # alineación grid
    minutes_ok = df['timestamp'].dt.minute % 15 == 0
    seconds_ok = df['timestamp'].dt.second.eq(0) & df['timestamp'].dt.microsecond.eq(0)
    grid_ok = bool((minutes_ok & seconds_ok).all())
    return dup_counts, grid_ok


def detectar_gaps(df: pd.DataFrame, threshold_intervals: int = 2):
    gaps_info = {}
    critical = False
    for sym, g in df.groupby('symbol'):
        g = g.sort_values('timestamp')
        deltas = g['timestamp'].diff().dt.total_seconds().dropna()
        # gaps donde faltan al menos 1 vela
        symbol_gaps = []
        for idx, delta in enumerate(deltas, start=1):
            if delta > DEF_INTERVAL_SECONDS:  # missing at least one
                missing = int(delta / DEF_INTERVAL_SECONDS) - 1
                start_ts = g['timestamp'].iloc[idx-1]
                end_ts = g['timestamp'].iloc[idx]
                record = {
                    'start': start_ts,
                    'end': end_ts,
                    'missing_candles': missing,
                    'duration_min': delta/60
                }
                symbol_gaps.append(record)
        # filtrar gaps críticos > threshold_intervals (ej >30m)
        critical_gaps = [gap for gap in symbol_gaps if gap['missing_candles'] >= threshold_intervals]
        if critical_gaps:
            critical = True
        gaps_info[sym] = {
            'all_gaps': symbol_gaps,
            'critical_gaps': critical_gaps
        }
    return gaps_info, critical


def calidad_ohlcv(df: pd.DataFrame):
    res = {}
    for sym, g in df.groupby('symbol'):
        stats = {}
        for col in ['open','high','low','close','volume']:
            if col in g.columns:
                stats[f'nan_{col}'] = int(g[col].isna().sum())
        # high < low inconsistencias
        if {'high','low'}.issubset(g.columns):
            stats['high_lt_low'] = int((g['high'] < g['low']).sum())
        # valores no válidos
        for col in ['open','high','low','close']:
            if col in g.columns:
                stats[f'{col}_le_0'] = int((g[col] <= 0).sum())
        if 'volume' in g.columns:
            stats['volume_neg'] = int((g['volume'] < 0).sum())
        res[sym] = stats
    return res


def resumen_final(conteo_rows, dup_counts, grid_ok, gaps_info, gaps_critical, calidad_stats):
    checks = {}
    # Conteo: fail si algún símbolo tiene 0 filas
    checks['conteo'] = all(r['rows'] > 0 for r in conteo_rows)
    # Duplicados: OK si todos 0
    checks['duplicados'] = all(v == 0 for v in dup_counts.values())
    # Grid alineado
    checks['grid_15m'] = grid_ok
    # Gaps críticos
    checks['gaps_criticos'] = not gaps_critical
    # Calidad OHLCV: no NaNs en precios y no high<low
    def ok_calidad():
        for sym, st in calidad_stats.items():
            if st.get('high_lt_low',0) > 0:
                return False
            if any(st.get(f'nan_{c}',0) > 0 for c in ['open','high','low','close']):
                return False
        return True
    checks['calidad_ohlcv'] = ok_calidad()
    overall = all(checks.values())
    return checks, overall


def generar_markdown(out_path: Path, conteo_rows, global_min, global_max, dup_counts, grid_ok, gaps_info, gaps_critical, calidad_stats, checks, overall):
    lines = []
    lines.append('# Verificación Maestro 15m')
    lines.append('')
    lines.append(f'Rango global: {global_min} → {global_max} ({(global_max-global_min)})')
    lines.append('')
    lines.append('## 1) Conteo por símbolo y cobertura')
    lines.append('| Símbolo | Filas | Inicio | Fin | Cobertura % |')
    lines.append('|---------|------:|--------|-----|------------:|')
    for r in conteo_rows:
        lines.append(f"| {r['symbol']} | {r['rows']} | {r['min']} | {r['max']} | {r['cobertura_pct']:.2f} |")
    lines.append('')
    lines.append('## 2) Timestamps')
    lines.append(f"Duplicados por símbolo: {dup_counts}")
    lines.append(f"Alineación grid 15m: {'OK' if grid_ok else 'FAIL'}")
    lines.append('')
    lines.append('## 3) Gaps (>30m)')
    any_gap = False
    for sym, info in gaps_info.items():
        crit = info['critical_gaps']
        if crit:
            any_gap = True
            lines.append(f"### {sym} gaps críticos")
            lines.append('| Inicio | Fin | Velas faltantes | Duración (min) |')
            lines.append('|--------|-----|----------------:|---------------:|')
            for g in crit:
                lines.append(f"| {g['start']} | {g['end']} | {g['missing_candles']} | {g['duration_min']:.1f} |")
    if not any_gap:
        lines.append('Sin gaps críticos (>30m).')
    lines.append('')
    lines.append('## 4) Calidad OHLCV')
    lines.append('| Símbolo | nan_open | nan_high | nan_low | nan_close | nan_volume | high<low | open<=0 | high<=0 | low<=0 | close<=0 | volume_neg |')
    lines.append('|---------|---------:|---------:|--------:|----------:|-----------:|---------:|--------:|--------:|-------:|---------:|-----------:|')
    for sym, st in calidad_stats.items():
        line = [sym,
                st.get('nan_open',0), st.get('nan_high',0), st.get('nan_low',0), st.get('nan_close',0), st.get('nan_volume',0),
                st.get('high_lt_low',0), st.get('open_le_0',0), st.get('high_le_0',0), st.get('low_le_0',0), st.get('close_le_0',0), st.get('volume_neg',0)]
        lines.append('| ' + ' | '.join(str(x) for x in line) + ' |')
    lines.append('')
    lines.append('## 5) Resumen Final')
    for k, v in checks.items():
        lines.append(f"- {k}: {'OK' if v else 'FAIL'}")
    lines.append('')
    lines.append(f"Recomendación: {'APTO para smoke test' if overall else 'NO APTO (corregir antes de continuar)'}")
    if not overall:
        lines.append('### Correcciones mínimas sugeridas:')
        if not checks['gaps_criticos']:
            lines.append('- Excluir tramos con gaps críticos o rellenar con forward-fill limitado (1 vela máximo).')
        if not checks['calidad_ohlcv']:
            lines.append('- Eliminar o imputar filas con NaNs en OHLC y corregir inconsistencias high<low.')
        if not checks['duplicados']:
            lines.append('- Remover duplicados por símbolo/timestamp antes del backtest.')
    out_path.write_text('\n'.join(lines), encoding='utf8')
    return out_path


def main(file: str, out: str):
    file_p = Path(file)
    out_p = Path(out)
    df = leer(file_p)
    conteo_rows, gmin, gmax = conteo_y_cobertura(df)
    dup_counts, grid_ok = verificar_timestamps(df)
    gaps_info, gaps_critical = detectar_gaps(df)
    calidad_stats = calidad_ohlcv(df)
    checks, overall = resumen_final(conteo_rows, dup_counts, grid_ok, gaps_info, gaps_critical, calidad_stats)
    md = generar_markdown(out_p, conteo_rows, gmin, gmax, dup_counts, grid_ok, gaps_info, gaps_critical, calidad_stats, checks, overall)
    print(f"Reporte generado en {md}")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--file', required=True)
    p.add_argument('--out', default='data/historiales/validacion_maestro_15m.md')
    args = p.parse_args()
    main(args.file, args.out)

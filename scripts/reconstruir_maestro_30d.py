"""reconstruir_maestro_30d.py
Genera un nuevo maestro 15m usando los últimos 30 días de datos de los CSV en data/historiales/raw.

Acciones:
 1. Lee todos los *_raw.csv en raw-dir
 2. Parsea timestamp (auto-detección de unidad s/ms/us) a UTC
 3. Filtra a ventana rolling de 30 días (respecto al último timestamp disponible por símbolo)
 4. Resamplea a 15m si la frecuencia original es más fina (<15m). No hace upsampling.
 5. Concatena símbolos, elimina duplicados, ordena y persiste maestro nuevo
 6. Hace backup del maestro anterior si existe
 7. Genera reporte de inspección maestro_30d_report.md con métricas por símbolo:
    - start, end
    - days_covered
    - bars
    - expected_bars (teórico 30d * 24*4 = 2880)
    - coverage_pct (bars/expected)
    - median_delta_sec original

Uso:
  python scripts/reconstruir_maestro_30d.py \
      --raw-dir data/historiales/raw \
      --out data/historiales/historial_trading_maestro_15m.csv \
      --freq 15min --days 30
"""
from __future__ import annotations
import os
import argparse
from pathlib import Path
from datetime import timedelta
import pandas as pd
import numpy as np
from typing import List, Dict

TARGET_FREQ = '15min'
EXPECTED_INTERVAL_SEC = 15*60


def parse_timestamp_series(s: pd.Series) -> pd.Series:
    s_clean = pd.to_numeric(s, errors='coerce')
    # Heurística por magnitud
    med = s_clean.dropna().median()
    if pd.isna(med):
        return pd.to_datetime(s, errors='coerce', utc=True)
    if 1e14 < med < 1e17:  # microsegundos
        return pd.to_datetime(s_clean, unit='us', errors='coerce', utc=True)
    if 1e12 < med < 1e14:  # milisegundos
        return pd.to_datetime(s_clean, unit='ms', errors='coerce', utc=True)
    if 1e9 < med < 1e11:   # segundos (posible)
        return pd.to_datetime(s_clean, unit='s', errors='coerce', utc=True)
    # fallback: intentar directo
    return pd.to_datetime(s, errors='coerce', utc=True)


def detect_original_freq(ts: pd.Series) -> float | None:
    ts = ts.sort_values()
    deltas = ts.diff().dt.total_seconds().dropna()
    if deltas.empty:
        return None
    return float(np.median(deltas))


def resample_15m(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.sort_values('timestamp').set_index('timestamp')
    agg = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    df_res = df.resample(TARGET_FREQ).agg(agg)
    df_res = df_res.dropna(subset=['open']).reset_index()
    return df_res


def process_symbol(raw_file: Path, days: int) -> dict:
    symbol = raw_file.stem.replace('_raw','').upper()
    try:
        df = pd.read_csv(raw_file)
    except Exception as e:
        return {'symbol': symbol, 'error': f'read_error:{e}'}
    if 'timestamp' not in df.columns:
        return {'symbol': symbol, 'error': 'no_timestamp_column'}
    df['timestamp'] = parse_timestamp_series(df['timestamp'])
    df = df.dropna(subset=['timestamp']).sort_values('timestamp')
    if df.empty:
        return {'symbol': symbol, 'error': 'no_valid_rows'}
    last_ts = df['timestamp'].max()
    cutoff = last_ts - timedelta(days=days)
    df_30 = df[df['timestamp'] >= cutoff].copy()
    orig_med = detect_original_freq(df_30['timestamp'])
    # resample si frecuencia original < 15m
    if orig_med is not None and orig_med < EXPECTED_INTERVAL_SEC:  # más fina
        df_30 = resample_15m(df_30)
    else:
        # normalizar columnas si ya está en 15m
        keep = [c for c in ['timestamp','open','high','low','close','volume'] if c in df_30.columns]
        df_30 = df_30[keep]
    df_30['symbol'] = symbol
    days_cov = (df_30['timestamp'].max() - df_30['timestamp'].min()).total_seconds() / 86400 if len(df_30)>1 else 0
    expected_bars = int(days * 24 * 60 / 15)
    coverage_pct = (len(df_30) / expected_bars * 100) if expected_bars else 0
    return {
        'symbol': symbol,
        'df': df_30,
        'start': df_30['timestamp'].min(),
        'end': df_30['timestamp'].max(),
        'days_covered': days_cov,
        'bars': len(df_30),
        'expected_bars': expected_bars,
        'coverage_pct': coverage_pct,
        'median_delta_sec': orig_med,
        'cutoff': cutoff,
    }


def main(raw_dir: str, out: str, days: int, overwrite: bool):
    raw_path = Path(raw_dir)
    if not raw_path.exists():
        raise SystemExit(f'Raw dir no existe: {raw_path}')

    results: List[dict] = []
    frames = []
    for f in sorted(raw_path.glob('*_raw.csv')):
        r = process_symbol(f, days)
        results.append(r)
        if 'df' in r:
            frames.append(r['df'])

    if not frames:
        raise SystemExit('No se generaron frames válidos')

    maestro = pd.concat(frames, ignore_index=True)
    maestro = maestro.drop_duplicates(subset=['symbol','timestamp']).sort_values(['symbol','timestamp'])

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not overwrite:
        backup = out_path.with_suffix(out_path.suffix + f'.bak_{pd.Timestamp.utcnow().strftime("%Y%m%d%H%M%S")}')
        out_path.rename(backup)
        print(f'Backup maestro previo: {backup.name}')

    maestro.to_csv(out_path, index=False)
    print(f'Maestro 30d escrito: {out_path} ({len(maestro)} filas, {maestro.symbol.nunique()} símbolos)')

    # Reporte
    report_path = out_path.parent / 'maestro_30d_report.md'
    with open(report_path,'w',encoding='utf-8') as fh:
        fh.write('# Reporte Maestro 30d\n\n')
        fh.write(f'Generado: {pd.Timestamp.utcnow().isoformat()}Z\n\n')
        fh.write('| symbol | start | end | days_covered | bars | expected_bars | coverage_% | median_delta_sec |\n')
        fh.write('|---|---|---|---|---|---|---|---|\n')
        for r in results:
            fh.write('|{symbol}|{start}|{end}|{days:.2f}|{bars}|{exp}|{cov:.2f}|{med}|\n'.format(
                symbol=r.get('symbol'),
                start=r.get('start'),
                end=r.get('end'),
                days=r.get('days_covered',0),
                bars=r.get('bars'),
                exp=r.get('expected_bars'),
                cov=r.get('coverage_pct',0),
                med=r.get('median_delta_sec')
            ))
        fh.write('\nNotas:\n- coverage_% < 100 puede deberse a huecos reales en datos o a que todavía no se completan 30 días completos.\n')
    print(f'Reporte: {report_path}')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--raw-dir', default='data/historiales/raw')
    p.add_argument('--out', default='data/historiales/historial_trading_maestro_15m.csv')
    p.add_argument('--days', type=int, default=30)
    p.add_argument('--overwrite', action='store_true', help='No crear backup si existe')
    args = p.parse_args()
    main(args.raw_dir, args.out, args.days, args.overwrite)

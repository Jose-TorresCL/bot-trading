"""sincronizar_historicos_a_raw.py
Copía los archivos fuente de historicos completos (`src/data/historicos/historial_*.csv`) hacia
`data/historiales/raw/*_raw.csv` estandarizando columnas y orden temporal.

Motivación:
- Los archivos en `data/historiales/raw` actuales sólo cubren ~5-6 días.
- Existen historicos mensuales completos en `src/data/historicos` que deben alimentar el maestro.

Acciones por símbolo:
1. Leer `historial_<SYMBOL>.csv`
2. Validar columnas mínimas: timestamp, open, high, low, close, volume
3. Parsear timestamp (soporta ISO o epoch numérico) y ordenar
4. Eliminar duplicados exactos por timestamp
5. (Opcional) Filtrar por ventana rolling de N días si se pasa --days > 0 (por defecto 0 = todo)
6. Persistir como `data/historiales/raw/<SYMBOL>_raw.csv`
7. Reportar filas escritas y rango temporal

Uso:
  python scripts/sincronizar_historicos_a_raw.py --days 0 --overwrite

Luego ejecutar:
  python scripts/reconstruir_maestro_30d.py --raw-dir data/historiales/raw --out data/historiales/historial_trading_maestro_15m.csv --days 30 --overwrite
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from datetime import timedelta

MIN_COLS = ["timestamp","open","high","low","close","volume"]


def parse_ts(s: pd.Series) -> pd.Series:
    # Intenta numérico (epoch) y luego ISO
    s_num = pd.to_numeric(s, errors='coerce')
    med = s_num.dropna().median()
    if pd.isna(med):
        return pd.to_datetime(s, errors='coerce', utc=True)
    if 1e14 < med < 1e17:
        return pd.to_datetime(s_num, unit='us', errors='coerce', utc=True)
    if 1e12 < med < 1e14:
        return pd.to_datetime(s_num, unit='ms', errors='coerce', utc=True)
    if 1e9 < med < 1e11:
        return pd.to_datetime(s_num, unit='s', errors='coerce', utc=True)
    return pd.to_datetime(s, errors='coerce', utc=True)


def process_file(src_file: Path, out_dir: Path, days: int, overwrite: bool) -> dict:
    symbol = src_file.stem.replace('historial_','').upper()
    try:
        df = pd.read_csv(src_file)
    except Exception as e:
        return {"symbol": symbol, "error": f"read_error:{e}"}

    missing = [c for c in MIN_COLS if c not in df.columns]
    if missing:
        return {"symbol": symbol, "error": f"missing_cols:{missing}"}

    df['timestamp'] = parse_ts(df['timestamp'])
    df = df.dropna(subset=['timestamp']).sort_values('timestamp')
    df = df.drop_duplicates(subset=['timestamp'])
    if days > 0 and not df.empty:
        last_ts = df['timestamp'].max()
        cutoff = last_ts - timedelta(days=days)
        df = df[df['timestamp'] >= cutoff].copy()
    # Normalizar mayúsculas del símbolo
    if 'symbol' in df.columns:
        df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
    else:
        df['symbol'] = symbol

    out_file = out_dir / f"{symbol}_raw.csv"
    if out_file.exists() and not overwrite:
        # Evitar sobrescribir accidentalmente sin flag
        return {"symbol": symbol, "error": "exists_use_overwrite", "rows": len(df)}
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_file, index=False)
    return {
        "symbol": symbol,
        "rows": len(df),
        "start": df['timestamp'].min() if not df.empty else None,
        "end": df['timestamp'].max() if not df.empty else None,
        "out_file": str(out_file)
    }


def main(hist_dir: str, raw_dir: str, days: int, overwrite: bool):
    hist_path = Path(hist_dir)
    if not hist_path.exists():
        raise SystemExit(f"Directorio historicos no existe: {hist_path}")
    out_path = Path(raw_dir)

    files = sorted(hist_path.glob('historial_*.csv'))
    if not files:
        raise SystemExit("No se encontraron archivos historial_*.csv")

    results = []
    for f in files:
        r = process_file(f, out_path, days, overwrite)
        results.append(r)
        if 'error' in r:
            print(f"[WARN] {r['symbol']}: {r['error']}")
        else:
            print(f"[OK] {r['symbol']} -> {r['rows']} filas ({r['start']} -> {r['end']})")

    # Reporte simple
    report = out_path / 'sync_historicos_report.md'
    with open(report, 'w', encoding='utf-8') as fh:
        fh.write('# Sync Historicos -> Raw\n\n')
        fh.write('|symbol|rows|start|end|status|\n')
        fh.write('|---|---|---|---|---|\n')
        for r in results:
            status = r.get('error','ok')
            fh.write(f"|{r.get('symbol')}|{r.get('rows','')}|{r.get('start','')}|{r.get('end','')}|{status}|\n")
    print(f"Reporte: {report}")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--hist-dir', default='src/data/historicos', help='Directorio fuente historicos completos')
    p.add_argument('--raw-dir', default='data/historiales/raw', help='Destino estandarizado para maestro')
    p.add_argument('--days', type=int, default=0, help='Window rolling; 0 = todo el histórico disponible')
    p.add_argument('--overwrite', action='store_true')
    args = p.parse_args()
    main(args.hist_dir, args.raw_dir, args.days, args.overwrite)

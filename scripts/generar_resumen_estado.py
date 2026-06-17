"""Generador/actualizador de resumen corto (estado_resumido.md) y archivo archivado en RESÚMENES.

Uso básico (PowerShell):
  python scripts/generar_resumen_estado.py --run-dir data/backtesting/2025-09-07_00-53 \
      --analisis-dir data/backtesting/ANALISIS

Asunciones:
 - El run seleccionado contiene un summary.csv con métricas por símbolo o agregado.
 - Se derivan métricas globales simples (winrate, PF, ganancia media) desde trades/resultados si están disponibles.
 - Si faltan datos, se colocan marcadores 'N/A'.

El script es idempotente: reescribe `estado_resumido.md` y genera copia archivada con timestamp del run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import csv
import math

def leer_summary(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open('r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows

def infer_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Intentar mapear nombres de columnas flexibles.
    # Profit Factor
    pf_keys = [k for k in rows[0].keys()] if rows else []
    def pick(keys, *candidates):
        for c in candidates:
            if c in keys:
                return c
        return None
    metrics = {}
    if not rows:
        metrics.update({
            'profit_factor': 'N/A',
            'winrate': 'N/A',
            'avg_gain': 'N/A',
            'median_gain': 'N/A',
            'std_gain': 'N/A',
            'total_trades': 'N/A',
        })
        return metrics

    # Intentar agregación básica suponiendo filas por símbolo
    total_trades_key = pick(pf_keys, 'trades', 'num_trades', 'total_trades')
    winrate_key = pick(pf_keys, 'winrate', 'win_rate')
    pf_key = pick(pf_keys, 'profit_factor', 'pf', 'profitFactor')
    avg_key = pick(pf_keys, 'avg_trade', 'avg_gain', 'avg_profit')
    median_key = pick(pf_keys, 'median_trade', 'median_gain')
    std_key = pick(pf_keys, 'std_trade', 'std_gain', 'std_profit')

    def to_float(v):
        try:
            return float(v)
        except Exception:
            return None

    # Agregación simple (media) para métricas ratio y suma para trades
    trades_vals = [to_float(r.get(total_trades_key)) for r in rows if total_trades_key and r.get(total_trades_key)]
    win_vals = [to_float(r.get(winrate_key)) for r in rows if winrate_key and r.get(winrate_key)]
    pf_vals = [to_float(r.get(pf_key)) for r in rows if pf_key and r.get(pf_key)]
    avg_vals = [to_float(r.get(avg_key)) for r in rows if avg_key and r.get(avg_key)]
    median_vals = [to_float(r.get(median_key)) for r in rows if median_key and r.get(median_key)]
    std_vals = [to_float(r.get(std_key)) for r in rows if std_key and r.get(std_key)]

    metrics['total_trades'] = sum(v for v in trades_vals if v is not None) if trades_vals else 'N/A'
    metrics['winrate'] = round(sum(v for v in win_vals if v is not None)/len(win_vals), 4) if win_vals else 'N/A'
    metrics['profit_factor'] = round(sum(v for v in pf_vals if v is not None)/len(pf_vals), 4) if pf_vals else 'N/A'
    metrics['avg_gain'] = round(sum(v for v in avg_vals if v is not None)/len(avg_vals), 4) if avg_vals else 'N/A'
    metrics['median_gain'] = round(sum(v for v in median_vals if v is not None)/len(median_vals), 4) if median_vals else 'N/A'
    metrics['std_gain'] = round(sum(v for v in std_vals if v is not None)/len(std_vals), 4) if std_vals else 'N/A'
    return metrics

TEMPLATE = """# 🟨 Estado Resumido — Run {run_date_short}

## 📅 Fecha del análisis  
{run_date_human}

## 📈 Métricas globales  
- Operaciones totales: {total_trades}  
- Winrate: {winrate}  
- Profit Factor: {profit_factor}  
- Ganancia media: {avg_gain} USDT  
- Mediana: {median_gain} USDT  
- Desviación estándar: {std_gain} USDT  
- Max Drawdown: {max_drawdown}  

## 📊 Símbolos procesados  
{symbols_line}  
{variants_line}

## 🔍 Observaciones clave  
- (Auto) Max Drawdown calculado: {max_drawdown}  
- (Completar manualmente: outliers, estabilidad de equity, concentración de ganancias)  

## ✅ Decisiones tomadas  
{decisiones_tomadas}

## 🧠 Decisiones pendientes  
{decisiones_pendientes}

## 📁 Artefactos generados  
- (Ajustar: lista breve de nuevos outputs relevantes)  

## 🔜 Próximo paso sugerido  
{next_step}
"""

def extraer_bloque_estado_actual(contenido: str, titulo: str) -> List[str]:
    """Extrae hasta 10 bullets de la sección solicitada en estado_actual.md.
    Acepta encabezados que contengan el título (case-insensitive).
    """
    pattern = re.compile(r'^## .*?'+re.escape(titulo)+r'.*$', re.IGNORECASE | re.MULTILINE)
    match = pattern.search(contenido)
    if not match:
        return []
    start = match.end()
    rest = contenido[start:]
    next_match = re.search(r'^## ', rest, re.MULTILINE)
    block = rest[:next_match.start()] if next_match else rest
    lines = [l.strip() for l in block.splitlines() if l.strip().startswith('-')]
    return lines[:10]

def formatear_bullets(lines: List[str]) -> str:
    if not lines:
        return '- (Sin datos)'
    return '\n'.join(lines)

def detectar_equity_files(run_dir: Path) -> List[Path]:
    candidates = []
    # Patron principal
    eq_path = run_dir / 'equity_acumulada.csv'
    if eq_path.exists():
        candidates.append(eq_path)
    # Otros CSV que contengan 'equity' en el nombre
    for p in run_dir.glob('**/*equity*.csv'):
        if p not in candidates:
            candidates.append(p)
    return candidates

def leer_equity_series(path: Path) -> Optional[List[float]]:
    try:
        with path.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # Buscar columna equity
            equity_col = None
            if reader.fieldnames:
                for c in reader.fieldnames:
                    lc = c.lower()
                    if lc in ('equity','equity_total','balance','capital'):
                        equity_col = c
                        break
            if not equity_col:
                return None
            series = []
            for row in reader:
                v = row.get(equity_col)
                if v is None or v == '':
                    continue
                try:
                    series.append(float(v))
                except (TypeError, ValueError):
                    continue
            return series if series else None
    except Exception:
        return None

def calcular_max_drawdown(equity: List[float]) -> Optional[float]:
    if not equity:
        return None
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak != 0 else 0
        if dd < max_dd:
            max_dd = dd
    return max_dd  # negativo

def obtener_drawdown(run_dir: Path, rows: List[Dict[str, Any]]) -> str:
    # 1) Intentar desde summary.csv si hay columna que suene a drawdown
    dd_keys = []
    if rows:
        keys = rows[0].keys()
        dd_keys = [k for k in keys if re.search(r'drawdown|max_dd|maxdrawdown', k, re.IGNORECASE)]
        for k in dd_keys:
            vals = []
            for r in rows:
                raw = r.get(k)
                if raw is None or raw == '':
                    continue
                try:
                    vals.append(float(raw))
                except (TypeError, ValueError):
                    continue
            if vals:
                # Seleccionar peor (más negativo) o mayor magnitud
                worst = min(vals)
                return f"{worst}" if worst <= 0 else f"{worst}"
    # 2) Buscar archivos de equity y calcular
    for p in detectar_equity_files(run_dir):
        series = leer_equity_series(p)
        if series:
            dd = calcular_max_drawdown(series)
            if dd is not None:
                # Formatear como porcentaje con 2 decimales
                return f"{round(dd*100,2)}%"
    return 'N/A'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-dir', required=True, help='Carpeta del run base (summary.csv)')
    p.add_argument('--analisis-dir', required=True, help='Carpeta ANALISIS donde viven los estados')
    p.add_argument('--symbols', nargs='*', default=[], help='Lista explícita de símbolos si no se infiere')
    p.add_argument('--variants', nargs='*', default=[], help='Lista de variantes/periodos')
    p.add_argument('--next-step', default='(Definir próximo paso)')
    args = p.parse_args()

    run_dir = Path(args.run_dir)
    analisis_dir = Path(args.analisis_dir)
    if not run_dir.exists():
        print(f"Run dir no existe: {run_dir}", file=sys.stderr)
        sys.exit(1)
    analisis_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / 'summary.csv'
    rows = leer_summary(summary_path)
    metrics = infer_metrics(rows)

    # Infer symbols if possible
    symbols = set()
    symbol_keys = ['symbol', 'par', 'pair']
    for r in rows:
        for k in symbol_keys:
            if k in r and r[k]:
                symbols.add(r[k])
    if args.symbols:
        symbols.update(args.symbols)
    symbols_line = '- ' + (', '.join(sorted(symbols)) if symbols else '(No detectado)')
    variants_line = '- Variantes: ' + (', '.join(args.variants) if args.variants else '(No especificadas)')

    # Leer estado_actual.md para extraer extractos
    estado_actual_path = analisis_dir / 'estado_actual.md'
    decisiones_tomadas = []
    decisiones_pend = []
    if estado_actual_path.exists():
        contenido = estado_actual_path.read_text(encoding='utf-8')
        decisiones_tomadas = extraer_bloque_estado_actual(contenido, 'Decisiones Tomadas')
        if not decisiones_tomadas:
            decisiones_tomadas = extraer_bloque_estado_actual(contenido, 'Decisiones')  # fallback
        decisiones_pend = extraer_bloque_estado_actual(contenido, 'Decisiones Pendientes')

    decisiones_tomadas_block = formatear_bullets(decisiones_tomadas)
    decisiones_pend_block = formatear_bullets(decisiones_pend)

    # Fecha run (derivada del nombre)
    run_date_short = run_dir.name.split('_')[0]
    # Intentar parse full timestamp si existe underscore
    run_date_human = run_dir.name.replace('_', ' ')

    # Calcular / obtener drawdown
    max_drawdown = obtener_drawdown(run_dir, rows) if run_dir else 'N/A'

    content = TEMPLATE.format(
        run_date_short=run_date_short,
        run_date_human=run_date_human,
        total_trades=metrics['total_trades'],
        winrate=metrics['winrate'],
        profit_factor=metrics['profit_factor'],
        avg_gain=metrics['avg_gain'],
        median_gain=metrics['median_gain'],
        std_gain=metrics['std_gain'],
        max_drawdown=max_drawdown,
        symbols_line=symbols_line,
        variants_line=variants_line,
        decisiones_tomadas=decisiones_tomadas_block,
        decisiones_pendientes=decisiones_pend_block,
        next_step=args.next_step,
    )

    # ============ Bloque opcional: Modelo de Costos (si existe) ============
    def localizar_cost_metrics(run_dir: Path) -> Optional[Path]:
        candidates = list(run_dir.rglob('metrics_cost_adjusted.csv'))
        return candidates[0] if candidates else None

    cost_metrics_path = localizar_cost_metrics(run_dir)
    if cost_metrics_path and cost_metrics_path.exists():
        try:
            import csv as _csv
            with cost_metrics_path.open('r', encoding='utf-8') as f:
                reader = _csv.DictReader(f)
                rows_cost = list(reader)
            total_row = None
            for r in rows_cost:
                if r.get('symbol') == 'TOTAL':
                    total_row = r
                    break
            ref = total_row if total_row else (rows_cost[0] if rows_cost else None)
            if ref:
                def num(v):
                    try:
                        return float(v)
                    except Exception:
                        return None
                gross_pf = ref.get('gross_profit_factor')
                net_pf = ref.get('net_profit_factor')
                net_wr = ref.get('net_winrate')
                gross_pnl = ref.get('gross_pnl')
                net_pnl = ref.get('net_pnl')
                comm = ref.get('total_commission')
                slip = ref.get('total_slippage')
                impact = ref.get('impact_cost_pct')
                block = [
                    '## 💰 Modelo de Costos (ajustado)',
                    f"- Profit Factor neto: {net_pf} (bruto: {gross_pf})  ",
                    f"- Winrate neto: {net_wr}% (vs bruto: {metrics['winrate']})  ",
                    f"- PnL bruto total: {gross_pnl}  ",
                    f"- PnL neto total: {net_pnl}  ",
                    f"- Comisión total estimada: {comm}  ",
                    f"- Slippage total estimado: {slip}  ",
                    f"- Impacto costos: {impact}% sobre PnL bruto  ",
                    '',
                ]
                content += '\n' + '\n'.join(block) + '\n'
        except Exception:
            pass

    # ================== Sección: ¿Listo para producción? ==================
    def detectar_modelo_costos(run_dir: Path, analisis_dir: Path) -> bool:
        patterns = [
            'metrics_cost_adjusted.csv',
            'summary_cost_model.md'
        ]
        # Buscar en run_dir y analisis_dir (1 nivel) y subcarpetas claves
        search_roots = [run_dir, analisis_dir]
        for root in search_roots:
            if not root.exists():
                continue
            for pat in patterns:
                for p in root.rglob(pat):
                    return True
        # Heurística: carpeta modelo_costos
        for root in search_roots:
            mc = root / 'modelo_costos'
            if mc.exists() and any(mc.iterdir()):
                return True
        return False

    def parse_float(val) -> Optional[float]:
        if val in (None, 'N/A'):
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            s = str(val).strip().replace('%','')
            return float(s)
        except Exception:
            return None

    pf_val = parse_float(metrics.get('profit_factor'))
    win_val = parse_float(metrics.get('winrate'))
    dd_val_raw = max_drawdown
    dd_val = None
    if isinstance(dd_val_raw, (int,float)):
        # could be negative; use absolute percentage
        dd_val = abs(float(dd_val_raw))* (100.0 if abs(dd_val_raw) < 1 else 1)
    else:
        dd_val = parse_float(dd_val_raw)
    # If drawdown expressed as negative percent like -12, convert to positive magnitude
    if dd_val is not None and dd_val < 0:
        dd_val = abs(dd_val)

    # Normalize winrate if between 0 and 1 -> convert to percentage
    if win_val is not None and win_val <= 1:
        win_val *= 100

    modelo_costos_ok = detectar_modelo_costos(run_dir, analisis_dir)
    metrics_ok = (pf_val is not None and win_val is not None and dd_val is not None and pf_val > 1.5 and win_val > 55 and dd_val < 20)

    # Walk-forward detection heuristics: look for directories or files indicating segmentation
    def detectar_walkforward(root_list: List[Path]) -> bool:
        tokens = ['walkforward','walk_forward','walk-forward','out_of_sample','oos']
        for root in root_list:
            if not root.exists():
                continue
            for p in root.rglob('*'):
                name = p.name.lower()
                if any(tok in name for tok in tokens):
                    return True
        return False

    walkforward_ok = detectar_walkforward([run_dir, analisis_dir])

    # Entorno ejecución definido: presence of config.env OR logs/bot.log
    entorno_ok = False
    project_root = analisis_dir.parent.parent  # data/
    config_env = project_root / 'config.env'
    logs_dir = project_root / 'logs'
    if config_env.exists():
        entorno_ok = True
    if logs_dir.exists() and any((logs_dir / f).exists() for f in ['bot.log','backtesting.log']):
        entorno_ok = True

    # Evaluación de activos: threshold tests con BNB y WLD
    threshold_dir = analisis_dir / 'threshold_tests'
    activos_ok = False
    if threshold_dir.exists():
        # buscar archivos csv que contengan BNBUSDT y WLDUSDT
        bnb = list(threshold_dir.rglob('*BNBUSDT*'))
        wld = list(threshold_dir.rglob('*WLDUSDT*'))
        if bnb and wld:
            activos_ok = True

    # Estado global
    if all([modelo_costos_ok, metrics_ok, walkforward_ok, entorno_ok, activos_ok]):
        estado_global = 'Listo para producción'
    elif all([modelo_costos_ok, metrics_ok, entorno_ok, activos_ok]):
        estado_global = 'Apto para paper trading. No apto aún para live.'
    else:
        estado_global = 'No apto aún (faltan criterios clave).'

    def flag(b: bool) -> str:
        return '✅' if b else '❌'

    produccion_section = [
        '## ✅ ¿Listo para producción?',
        f'- Modelo de costos aplicado: {flag(modelo_costos_ok)}  ',
        f'- Métricas mínimas cumplidas: {flag(metrics_ok)}  ',
        f'- Validación robusta (walk-forward): {flag(walkforward_ok)}  ',
        f'- Entorno de ejecución definido: {flag(entorno_ok)}  ',
        f'- Evaluación de activos completada: {flag(activos_ok)}  ',
        '',
        f'🔔 Estado: {estado_global}',
    ]

    content = content + '\n---\n\n' + '\n'.join(produccion_section) + '\n\n---\n'

    resumen_path = analisis_dir / 'estado_resumido.md'
    resumen_path.write_text(content, encoding='utf-8')

    # Archivo archivado
    archivo_archivo = analisis_dir / 'RESÚMENES' / f'estado_resumido_{run_dir.name}.md'
    archivo_archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo_archivo.write_text(content, encoding='utf-8')

    print(f"Resumen actualizado: {resumen_path}")
    print(f"Resumen archivado: {archivo_archivo}")

if __name__ == '__main__':
    main()

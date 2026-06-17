"""Optimización simple de parámetros para el motor de backtesting.

Objetivo: explorar una rejilla pequeña de parámetros clave y evaluar
robustez (train vs validation) por símbolo usando el maestro 15m.

Salida: carpeta data/backtesting/ANALISIS/optimizacion/<timestamp>/ con:
- resultados_grid.csv : todas las combinaciones evaluadas (train + val)
- top_k_validacion.csv : top K por score validación
- recomendacion_resumen.md : resumen corto

Score (heurístico): profit_factor_val * winrate_val * (1 - max_dd_val)
(Se ignoran combinaciones con trades < min_trades o profit_factor <= 0)

Ejecutar:
  python scripts/optimizar_parametros.py
Opcional env vars:
  OPT_DIAS=30 (ventana en días)
  OPT_MIN_TRADES=5 (mínimo de trades para considerar válido)
  OPT_TOP_K=10
"""
from __future__ import annotations
import os, sys, math, json, itertools, datetime as dt
from dataclasses import dataclass
import pandas as pd
from typing import List, Dict, Any

# Asegurar raíz proyecto en sys.path
ROOT = os.path.dirname(os.path.abspath(__file__)) + "/.."
ROOT = os.path.normpath(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.backtesting import backtesting as motor_backtesting  # type: ignore

#############################################################
# Utilidades
#############################################################

def timestamp_now() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

@dataclass
class ParamOverride:
    RSI_LIMIT_COMPRA: float
    RSI_LIMIT_VENTA: float
    MIN_VOTES_COMPRA: int
    MIN_VOTES_VENTA: int
    SL_MULT: float
    TP_MULT: float
    starting_capital: float = 100.0
    rsi_dynamic_buy: float | None = None
    rsi_dynamic_sell: float | None = None
    atr_min: float | None = None
    bb_width_min: float | None = None

# Reconstrucción local de trades (por si _build_trades no devuelve nada)

def build_trades(resultados: List[Dict[str, Any]]) -> pd.DataFrame:
    trades = []
    open_side = None
    entry_price = None
    entry_ts = None
    for r in resultados:
        t = r.get("tipo")
        if t in ("compra", "venta") and r.get("ganancia") is None and open_side is None:
            # apertura
            open_side = t
            entry_price = r.get("precio")
            entry_ts = r.get("timestamp")
        elif t == "venta" and r.get("ganancia") is not None and open_side is not None:
            exit_price = r.get("precio")
            pnl = r.get("ganancia")
            trades.append({
                "side": open_side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "entry_ts": entry_ts,
                "exit_ts": r.get("timestamp"),
            })
            open_side = None
            entry_price = None
            entry_ts = None
    return pd.DataFrame(trades)


def compute_metrics(trades: pd.DataFrame) -> Dict[str, float]:
    if trades.empty:
        return {k: 0.0 for k in ["num_trades","winrate","profit_factor","expectancy","avg_win","avg_loss","max_consec_losses","median_pnl","std_pnl"]}
    pnl = trades["pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    profit_factor = (wins.sum() / abs(losses.sum())) if not losses.empty else float('inf')
    winrate = (len(wins) / len(pnl))*100 if len(pnl) else 0
    expectancy = pnl.mean()
    avg_win = wins.mean() if not wins.empty else 0.0
    avg_loss = losses.mean() if not losses.empty else 0.0
    # max consecutive losses
    max_consec_losses = 0
    current = 0
    for v in pnl:
        if v <= 0:
            current += 1
            max_consec_losses = max(max_consec_losses, current)
        else:
            current = 0
    return {
        "num_trades": float(len(pnl)),
        "winrate": float(winrate),
        "profit_factor": float(profit_factor if math.isfinite(profit_factor) else 0),
        "expectancy": float(expectancy),
        "avg_win": float(avg_win if not math.isnan(avg_win) else 0),
        "avg_loss": float(avg_loss if not math.isnan(avg_loss) else 0),
        "max_consec_losses": float(max_consec_losses),
        "median_pnl": float(pnl.median()),
        "std_pnl": float(pnl.std(ddof=0) if len(pnl)>1 else 0.0)
    }

#############################################################
# Carga de datos maestro 15m
#############################################################
MAESTRO_15M = os.path.join("data","historiales","historial_trading_maestro_15m.csv")
if not os.path.exists(MAESTRO_15M):
    print(f"[ERROR] No existe maestro 15m: {MAESTRO_15M}")
    sys.exit(1)

df_maestro = pd.read_csv(MAESTRO_15M)
if "timestamp" not in df_maestro.columns:
    print("[ERROR] Maestro sin columna timestamp")
    sys.exit(1)
if "symbol" not in df_maestro.columns:
    print("[ERROR] Maestro sin columna symbol")
    sys.exit(1)

# Normalizar formato
try:
    df_maestro.sort_values("timestamp", inplace=True)
except Exception:
    pass

#############################################################
# Configuración rejilla
#############################################################
DIAS = int(os.environ.get("OPT_DIAS", 45))
MIN_TRADES = int(os.environ.get("OPT_MIN_TRADES", 5))
TOP_K = int(os.environ.get("OPT_TOP_K", 10))

param_grid = {
    "RSI_LIMIT_COMPRA": [35, 40, 45],
    "RSI_LIMIT_VENTA": [55, 60, 65],
    "MIN_VOTES_COMPRA": [2, 3, 4],
    "MIN_VOTES_VENTA": [1, 2],
    "SL_MULT": [1.0, 1.5, 2.0],
    "TP_MULT": [2.0, 3.0, 4.0]
}

symbols = sorted(df_maestro['symbol'].unique().tolist())

# Limitar a ventana DIAS finales
try:
    ts_series = pd.to_datetime(df_maestro['timestamp'])
    cutoff = ts_series.max() - pd.Timedelta(days=DIAS)
    df_maestro = df_maestro.loc[ts_series >= cutoff].copy()
except Exception:
    pass

out_dir = os.path.join("data","backtesting","ANALISIS","optimizacion", timestamp_now())
os.makedirs(out_dir, exist_ok=True)

combos = list(itertools.product(*param_grid.values()))
param_names = list(param_grid.keys())

rows = []
print(f"Evaluando {len(combos)} combinaciones sobre {len(symbols)} símbolos ventana {DIAS}d...")

for combo in combos:
    combo_dict = dict(zip(param_names, combo))
    # agregados multi-símbolo (train/val promedios)
    agg_train = {"profit_factor":[],"winrate":[],"max_dd":[],"num_trades":[]}
    agg_val = {"profit_factor":[],"winrate":[],"max_dd":[],"num_trades":[]}

    for sym in symbols:
        sub = df_maestro[df_maestro['symbol'].str.upper()==sym.upper()].copy()
        if sub.empty:
            continue
        # split 70/30 temporal
        n = len(sub)
        split_idx = int(n*0.7)
        df_train = sub.iloc[:split_idx].reset_index(drop=True)
        df_val = sub.iloc[split_idx:].reset_index(drop=True)
        if len(df_train)<50 or len(df_val)<30:
            continue
        cfg = ParamOverride(
            RSI_LIMIT_COMPRA=combo_dict['RSI_LIMIT_COMPRA'],
            RSI_LIMIT_VENTA=combo_dict['RSI_LIMIT_VENTA'],
            MIN_VOTES_COMPRA=combo_dict['MIN_VOTES_COMPRA'],
            MIN_VOTES_VENTA=combo_dict['MIN_VOTES_VENTA'],
            SL_MULT=combo_dict['SL_MULT'],
            TP_MULT=combo_dict['TP_MULT']
        )
        # train
        try:
            res_train = motor_backtesting(df_train, config_obj=cfg, writer=None)
        except Exception:
            continue
        if not res_train or len(res_train)<2:
            continue
        resultados_train, resumen_train = res_train
        trades_train = build_trades(resultados_train)
        m_train = compute_metrics(trades_train)
        if m_train['num_trades'] < MIN_TRADES:
            continue
        # derive max_dd from resumen if exists else 0
        max_dd_train = float(resumen_train.get('max_drawdown', 0)) if isinstance(resumen_train, dict) else 0
        agg_train['profit_factor'].append(m_train['profit_factor'])
        agg_train['winrate'].append(m_train['winrate']/100.0)
        agg_train['max_dd'].append(max_dd_train)
        agg_train['num_trades'].append(m_train['num_trades'])
        # validation
        try:
            res_val = motor_backtesting(df_val, config_obj=cfg, writer=None)
        except Exception:
            continue
        if not res_val or len(res_val)<2:
            continue
        resultados_val, resumen_val = res_val
        trades_val = build_trades(resultados_val)
        m_val = compute_metrics(trades_val)
        if m_val['num_trades'] < MIN_TRADES:
            continue
        max_dd_val = float(resumen_val.get('max_drawdown', 0)) if isinstance(resumen_val, dict) else 0
        agg_val['profit_factor'].append(m_val['profit_factor'])
        agg_val['winrate'].append(m_val['winrate']/100.0)
        agg_val['max_dd'].append(max_dd_val)
        agg_val['num_trades'].append(m_val['num_trades'])

    # Agregar fila agregada si hay símbolos válidos
    if agg_val['profit_factor']:
        pf_train = sum(agg_train['profit_factor'])/len(agg_train['profit_factor']) if agg_train['profit_factor'] else 0
        wr_train = sum(agg_train['winrate'])/len(agg_train['winrate']) if agg_train['winrate'] else 0
        dd_train = sum(agg_train['max_dd'])/len(agg_train['max_dd']) if agg_train['max_dd'] else 0
        trades_train_avg = sum(agg_train['num_trades'])/len(agg_train['num_trades']) if agg_train['num_trades'] else 0
        pf_val = sum(agg_val['profit_factor'])/len(agg_val['profit_factor'])
        wr_val = sum(agg_val['winrate'])/len(agg_val['winrate'])
        dd_val = sum(agg_val['max_dd'])/len(agg_val['max_dd'])
        trades_val_avg = sum(agg_val['num_trades'])/len(agg_val['num_trades'])
        # score validación simple
        score = (pf_val if pf_val>0 else 0) * wr_val * (1 - min(dd_val,1))
        rows.append({
            **combo_dict,
            "pf_train": pf_train,
            "wr_train": wr_train,
            "dd_train": dd_train,
            "trades_train_avg": trades_train_avg,
            "pf_val": pf_val,
            "wr_val": wr_val,
            "dd_val": dd_val,
            "trades_val_avg": trades_val_avg,
            "score": score,
            "symbols_validos": len(agg_val['profit_factor'])
        })

# Exportar
if not rows:
    print("[WARN] No se obtuvieron combinaciones válidas. Ajustar rejilla o datos.")
    sys.exit(0)

df_out = pd.DataFrame(rows).sort_values("score", ascending=False)
res_csv = os.path.join(out_dir, "resultados_grid.csv")
df_out.to_csv(res_csv, index=False)
print(f"[OK] Guardado grid en {res_csv} ({len(df_out)} filas)")

top_k = df_out.head(TOP_K)
top_csv = os.path.join(out_dir, "top_k_validacion.csv")
top_k.to_csv(top_csv, index=False)

recom = top_k.iloc[0].to_dict()
with open(os.path.join(out_dir, "recomendacion_resumen.md"), "w", encoding="utf-8") as f:
    f.write("# Recomendación de Parámetros (Validación)\n\n")
    f.write(json.dumps(recom, indent=2, ensure_ascii=False))
    f.write("\n\nTop K (ordenados por score) en top_k_validacion.csv\n")

print("[DONE] Optimización finalizada. Revisa carpeta de salida.")

import os
import sys
import argparse
import subprocess
import json
from typing import Any, Dict, List, Tuple
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# Habilitar imports relativos al repo
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Motor y utilidades del proyecto
from src.core.backtesting import backtesting, BTConfig
from src.core.utilidades import ParamConfig
from src.pipeline.conexion_api import connect_to_binance
from src.pipeline.carga_datos import cargar_y_combinar_datos

# Umbrales
ROLL_WIN = 20
MAE_EFF_THRESHOLD = 0.8
SKEW_THRESHOLD = 1.0
MIN_TRADES_REQUIRED = 60

# Near-miss (gating relajado)
NEAR_MIN_TRADES = 40
NEAR_SKEW_THRESHOLD = 1.5
NEAR_WINRATE_MIN = 40.0
NEAR_FEES_MAX = 50.0
NEAR_TRADES_PER_DAY_MAX = 8.0
NEAR_RECOVERY_MIN = -1.0
NEAR_PF_MIN = 0.90  # o expectancy > -5
NEAR_EXPECTANCY_FLOOR = -5.0

# ---------------------
# Utilidades de métricas (centralizadas)
# ---------------------
try:
    from src.reporting.metrics import (
        profit_factor as _profit_factor_c,
        max_drawdown as _max_drawdown_c,
        recovery_ratio as _recovery_ratio_c,
        compute_advanced_metrics as _compute_advanced_metrics_c,
        winrate_rolling as _winrate_rolling_c,
        mae_eff_ok as _mae_eff_ok_c,
        fragility_flag as _fragility_flag_c,
        pf_window_degradation as _pf_window_degradation_c,
        skew_r_multiple as _skew_r_multiple_c,
    )
except Exception:
    _profit_factor_c = _max_drawdown_c = _recovery_ratio_c = None
    _compute_advanced_metrics_c = None
    _winrate_rolling_c = _mae_eff_ok_c = _fragility_flag_c = None
    _pf_window_degradation_c = _skew_r_multiple_c = None

def _ensure_df(trades_obj: Any) -> pd.DataFrame:
    if trades_obj is None:
        return pd.DataFrame()
    if isinstance(trades_obj, pd.DataFrame):
        df = trades_obj.copy()
    elif isinstance(trades_obj, list):
        df = pd.DataFrame(trades_obj)
    else:
        try:
            df = pd.DataFrame(trades_obj)
        except Exception:
            return pd.DataFrame()

    # Normalizar tiempos
    tcol = "exit_time" if "exit_time" in df.columns else ("timestamp" if "timestamp" in df.columns else None)
    if tcol:
        df[tcol] = pd.to_datetime(df[tcol], errors="coerce")

    # net_pnl fallback
    if "net_pnl" not in df.columns:
        for alias in ("ganancia", "pnl", "profit"):
            if alias in df.columns:
                df["net_pnl"] = pd.to_numeric(df[alias], errors="coerce")
                break
        else:
            df["net_pnl"] = np.nan

    # r_multiple_net fallback
    if "r_multiple_net" not in df.columns and "r_multiple" in df.columns:
        df["r_multiple_net"] = pd.to_numeric(df["r_multiple"], errors="coerce")

    return df


def _as_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
        return s if isinstance(s, pd.Series) else pd.Series(s, index=df.index)
    return pd.Series(index=df.index, dtype=float)


def profit_factor(series: pd.Series) -> float:
    """Compatibilidad: delega en src.reporting.metrics.profit_factor"""
    if _profit_factor_c is not None:
        return float(_profit_factor_c(series))
    pos = series[series > 0].sum()
    neg = series[series < 0].sum()
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return float(pos / abs(neg))


def max_drawdown(pnl_series: pd.Series) -> float:
    """Compatibilidad: delega en src.reporting.metrics.max_drawdown (devuelve negativo)."""
    if _max_drawdown_c is not None:
        return float(_max_drawdown_c(pnl_series))
    eq = pnl_series.cumsum()
    roll_max = eq.cummax()
    dd = eq - roll_max
    return float(dd.min()) if not dd.empty else 0.0


def recovery_ratio(pnl_series: pd.Series) -> float:
    if _recovery_ratio_c is not None:
        return float(_recovery_ratio_c(pnl_series))
    if pnl_series.empty:
        return np.nan
    final_eq = float(pnl_series.cumsum().iloc[-1])
    mdd = max_drawdown(pnl_series)
    return (final_eq / -mdd) if mdd < 0 else float("inf")


def winrate_rolling(series: pd.Series, window: int = ROLL_WIN) -> float:
    if series.empty:
        return np.nan
    wins = (series > 0).astype(float)
    roll = wins.rolling(window, min_periods=max(5, window // 2)).mean() * 100
    return float(roll.median())


def mae_eff_ok(df: pd.DataFrame, threshold: float = MAE_EFF_THRESHOLD) -> bool:
    if "mae" not in df.columns or "mfe" not in df.columns:
        return False
    mae = pd.to_numeric(df["mae"], errors="coerce").abs()
    mfe = pd.to_numeric(df["mfe"], errors="coerce").abs().replace(0, np.nan)
    ratio = (mae / mfe).dropna()
    if ratio.empty:
        return False
    return float(ratio.median()) < threshold


def fragility_flag(trades: pd.DataFrame) -> bool:
    if trades.empty or "symbol" not in trades.columns:
        return False
    base = _as_series(trades, "net_pnl").fillna(0.0)
    base_pf = profit_factor(base)
    base_dd = max_drawdown(base)
    for sym, _g in trades.groupby("symbol"):
        rest = trades.loc[trades["symbol"] != sym]
        s = _as_series(rest, "net_pnl").fillna(0.0)
        if profit_factor(s) > base_pf or max_drawdown(s) < base_dd:
            return True
    return False


def pf_window_degradation(series: pd.Series, window: int = ROLL_WIN) -> Tuple[float, float]:
    if series.empty:
        return (np.nan, np.nan)
    pfs = []
    for i in range(0, len(series), window):
        blk = series.iloc[i:i+window]
        if not blk.empty:
            pfs.append(profit_factor(blk))
    if not pfs:
        return (np.nan, np.nan)
    ratios = []
    for i, pf in enumerate(pfs):
        prev = pfs[:i]
        if not prev:
            ratios.append(np.nan)
        else:
            med_prev = float(np.median(prev))
            ratios.append(pf / med_prev if med_prev != 0 else np.nan)
    ratios = pd.Series(ratios)
    return (float(ratios.min(skipna=True)), float(ratios.dropna().iloc[-1]) if ratios.dropna().size else np.nan)


def skew_r_multiple(df: pd.DataFrame) -> float:
    if "r_multiple_net" not in df.columns:
        return np.nan
    vals = pd.to_numeric(df["r_multiple_net"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if vals.empty:
        return np.nan
    sk = vals.skew()
    return float(sk) if isinstance(sk, (int, float, np.floating)) else np.nan


def compute_advanced_metrics(trades_df: pd.DataFrame) -> Dict[str, Any]:
    """Compatibilidad: usa implementación centralizada."""
    if _compute_advanced_metrics_c is not None:
        return _compute_advanced_metrics_c(trades_df)
    # Fallback mínimo si el import falla
    df = trades_df.copy()
    pnl = _as_series(df, "net_pnl").fillna(0.0)
    return {
        "trades": int(len(df)),
        "pf_net": float(profit_factor(pnl)),
        "expectancy": float(pnl.mean()) if len(pnl) else np.nan,
        "max_dd": float(max_drawdown(pnl)),
        "recovery_ratio": float(recovery_ratio(pnl)),
    }

# ---------------------
# Helpers de ejecución
# ---------------------

def _is_ohlc(df: pd.DataFrame) -> bool:
    return {"timestamp", "open", "high", "low", "close"}.issubset(df.columns)

def _list_symbols_in_csv(csv_path: str) -> List[str]:
    try:
        df = pd.read_csv(csv_path, usecols=["symbol"])  # rápido
        if "symbol" in df.columns:
            return sorted(df["symbol"].dropna().astype(str).unique().tolist())
    except Exception:
        return []
    return []

def _choose_symbol(csv_path: str, requested: str | None) -> str | None:
    symbols = _list_symbols_in_csv(csv_path)
    if not symbols:
        return requested
    if requested and requested in symbols:
        return requested
    # tomar el primero por orden alfabético si no se pidió o es inválido
    return symbols[0]


def _autodetect_latest_trades(base_dir: Path) -> Path | None:
    analisis = base_dir / "data" / "backtesting" / "ANALISIS"
    if not analisis.exists():
        return None
    candidates = []
    for d in analisis.iterdir():
        if not d.is_dir():
            continue
        try:
            _ = pd.to_datetime(d.name, format="%Y-%m-%d_%H-%M")
            candidates.append(d)
        except Exception:
            continue
    if not candidates:
        return None
    latest = sorted(candidates)[-1]
    p = latest / "modelo_costos" / "trades_enriched_global.csv"
    return p if p.exists() else None


def _apply_params_to_config(cfg: Any, params: Dict[str, Any]) -> Any:
    """Sobrescribe en cfg los parámetros clave del grid si existen como atributos."""
    try:
        mapping = [
            ("RSI_LIMIT_COMPRA", "RSI_BUY"),
            ("RSI_LIMIT_VENTA", "RSI_SELL"),
            ("ADX_LIMIT", "ADX_LIMIT"),
            ("SL_MULT", "SL_MULT"),
            ("TP_MULT", "TP_MULT"),
        ]
        for attr, key in mapping:
            if hasattr(cfg, attr) and key in params and params[key] is not None:
                setattr(cfg, attr, params[key])
        # votos, si existen ambos lados
        mv = params.get("MIN_VOTES")
        if mv is not None:
            if hasattr(cfg, "MIN_VOTES_COMPRA"):
                setattr(cfg, "MIN_VOTES_COMPRA", mv)
            if hasattr(cfg, "MIN_VOTES_VENTA"):
                setattr(cfg, "MIN_VOTES_VENTA", mv)
    except Exception:
        # si ParamConfig no tiene estos atributos, continuar sin bloquear
        pass
    return cfg


def _run_one_combo(rsi_buy:int, rsi_sell:int, adx:int, votes:int, sl:float, tp:float, atr_mul:float, df_base: pd.DataFrame, base_dir: Path) -> tuple[pd.DataFrame, dict]:
    params = {"RSI_BUY": rsi_buy, "RSI_SELL": rsi_sell, "ADX_LIMIT": adx, "SL_MULT": sl, "TP_MULT": tp, "MIN_VOTES": votes, "ATR_MULT": atr_mul}
    trades_df = pd.DataFrame(); resumen = {}
    try:
        datos = df_base if _is_ohlc(df_base) else pd.DataFrame()
        # construir config de filtros (BTConfig) + overrides de parámetros para legacy via params
        bt_cfg = BTConfig()
        _ = _apply_params_to_config(ParamConfig(), params)  # noop aquí, manteniendo compatibilidad
        ret = backtesting(datos, bt_cfg, params)
        if isinstance(ret, tuple):
            if len(ret) == 3:
                resultados_trades = ret[0]
                resumen = ret[1]
                enriched_trades = ret[2]
                src = enriched_trades if enriched_trades is not None and not pd.DataFrame(enriched_trades).empty else resultados_trades
            elif len(ret) == 2:
                resultados_trades = ret[0]
                resumen = ret[1]
                src = resultados_trades
            else:
                resultados_trades = ret[0]
                resumen = ret[1] if len(ret) > 1 else {}
                src = resultados_trades
        else:
            src, resumen = ret, {}
        trades_df = _ensure_df(src)
    except Exception:
        trades_df = pd.DataFrame()

    return trades_df, (resumen or {})


def _build_grid(quick: bool) -> Tuple[List[int], List[int], List[int], List[int], List[float], List[float], List[float]]:
    if quick:
        return [30], [65, 70], [23], [3, 4], [1.0], [2.5, 3.0], [1.0]
    return (
        [20, 25, 30, 35, 40],
        [60, 65, 70, 75, 80],
        [20, 23, 25],
        [3, 4, 5],
        [1.0, 1.5, 2.0],
        [2.0, 2.5, 3.0, 3.5],
        [1.0, 1.5, 2.0, 2.5],
    )


def _eligible(row: pd.Series) -> bool:
    if pd.isna(row.get("expectancy")) or pd.isna(row.get("recovery_ratio")):
        return False
    if row["expectancy"] <= 0: return False
    if row["recovery_ratio"] < -0.5: return False
    if row.get("r_multiple_median_net", -1) <= 0: return False
    if row.get("winrate_rolling", 0) <= 45: return False
    if not row.get("mae_eff_ok", False): return False
    if row.get("skew_extreme", False): return False
    if row.get("few_trades", False): return False
    if row.get("fees_share_pct", np.nan) and row["fees_share_pct"] > 40: return False
    if row.get("trades_per_day", np.nan) and row["trades_per_day"] > 6: return False
    return True


def _near_miss(row: pd.Series) -> bool:
    """Criterios más relajados para listar candidatos 'near-miss'.
    No reemplaza al gating estricto; sirve para explorar setups prometedores.
    """
    # métricas base disponibles
    pf_net = row.get("pf_net", np.nan)
    exp = row.get("expectancy", np.nan)
    rec = row.get("recovery_ratio", np.nan)
    trades = row.get("trades", 0)
    winr = row.get("winrate_rolling", 0.0)
    skew = row.get("skew_r_multiple", np.nan)
    fees = row.get("fees_share_pct", np.nan)
    tpd = row.get("trades_per_day", np.nan)
    r_median = row.get("r_multiple_median_net", np.nan)

    # filtros relajados
    if trades < NEAR_MIN_TRADES:
        return False
    if not pd.isna(skew) and abs(skew) > NEAR_SKEW_THRESHOLD:
        return False
    if winr <= NEAR_WINRATE_MIN:
        return False
    if not pd.isna(fees) and fees > NEAR_FEES_MAX:
        return False
    if not pd.isna(tpd) and tpd > NEAR_TRADES_PER_DAY_MAX:
        return False
    if not pd.isna(rec) and rec < NEAR_RECOVERY_MIN:
        return False
    if not pd.isna(r_median) and r_median <= -0.05:
        return False
    # al menos una de las dos
    pf_ok = (not pd.isna(pf_net)) and (pf_net >= NEAR_PF_MIN)
    exp_ok = (not pd.isna(exp)) and (exp > NEAR_EXPECTANCY_FLOOR)
    if not (pf_ok or exp_ok):
        return False
    return True


# ---------------------
# main
# ---------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Grid pequeño (8 combos)")
    ap.add_argument("--data", type=str, default="data/historiales/historial_trading_maestro_15m.csv", help="Ruta a maestro OHLC (CSV)")
    ap.add_argument("--symbol", type=str, default=None, help="Símbolo a evaluar (ej: BTCUSDT)")
    ap.add_argument("--months", type=int, default=1, help="Meses de histórico a cargar (usa lo disponible si hay menos)")
    ap.add_argument("--allow-fallback", action="store_true", help="Permitir fallback a último trades_enriched_global si no hay trades")
    ap.add_argument("--list-symbols", action="store_true", help="Listar símbolos disponibles en el maestro y salir")
    ap.add_argument("--near-miss", action="store_true", help="Generar listado de candidatos con gating relajado (near-miss)")
    ap.add_argument("--near-top", type=int, default=10, help="Cantidad de near-miss a listar (default: 10)")
    # Fase 1 — Orquestador de variantes Beta B
    ap.add_argument("--fase1-betaB", action="store_true", help="Orquestar Fase 1 (B1–B4) usando ab_sesgo_fix.py")
    ap.add_argument("--symbols", type=str, default="BTCUSDT ETHUSDT BNBUSDT WLDUSDT", help="(Fase 1) Lista de símbolos separados por espacio")
    ap.add_argument("--out-root", type=str, default="data/backtesting/ANALISIS/Fase1", help="(Fase 1) Carpeta raíz de salida")
    # Fase 1_ext — Orquestador de interacciones acotadas
    ap.add_argument("--fase1-ext", action="store_true", help="Orquestar Fase 1_ext (A1–A4, B1–B4 [+opcionales]) usando ab_sesgo_fix.py")
    ap.add_argument("--include-optional-b56", action="store_true", help="Incluir B5 y B6 para llegar a 10 combinaciones (default: excluido)")
    ap.add_argument("--out-root-ext", type=str, default="data/backtesting/ANALISIS/Fase1_ext", help="(Fase 1_ext) Carpeta raíz de salida")
    # (las opciones de Fase 1_ext ya fueron declaradas arriba)
    args = ap.parse_args()

    if args.allow_fallback:
        os.environ["GRID_ALLOW_FALLBACK"] = "1"

    base_dir = Path(__file__).resolve().parents[2]

    # Modo orquestador Fase 1 (salir tras ejecutar variantes)
    if args.fase1_betaB:
        return _run_fase1_orchestrator(base_dir=base_dir, months=int(args.months), symbols=args.symbols, out_root=args.out_root, data_path=args.data)
    # Modo orquestador Fase 1_ext (salir tras ejecutar variantes + resumen)
    if args.fase1_ext:
        return _run_fase1_ext_orchestrator(
            base_dir=base_dir,
            months=int(args.months if args.months else 12),
            symbols=args.symbols,
            out_root=args.out_root_ext,
            data_path=args.data,
            include_optional=bool(args.include_optional_b56),
        )

    # Listar símbolos si se solicita
    if args.list_symbols:
        syms = _list_symbols_in_csv(args.data)
        print("Símbolos disponibles:")
        for s in syms:
            print(f"- {s}")
        return

    # Carga de datos: preferir maestro y recortar manualmente por meses relativo al dataset
    df_base = pd.DataFrame()
    client = None
    try:
        client = connect_to_binance()
    except Exception:
        client = None
    # Elegir símbolo válido si no se indicó o es inválido
    chosen_symbol = _choose_symbol(args.data, args.symbol)
    if args.symbol and chosen_symbol != args.symbol:
        print(f"Aviso: símbolo '{args.symbol}' no encontrado en maestro. Usando '{chosen_symbol}'.")

    # Intentar vía cargador unificado sin filtrar por meses (lo recortamos luego)
    try:
        df_base = cargar_y_combinar_datos(
            args.data,
            client=client,
            symbol=chosen_symbol or (args.symbol or ""),
            meses=0,
            acum_file="",
            api_fetch=False,
        )
    except Exception:
        df_base = pd.DataFrame()
    # Fallback: leer CSV directo
    if df_base.empty and os.path.exists(args.data):
        try:
            tmp = pd.read_csv(args.data)
            if "symbol" in tmp.columns and chosen_symbol:
                tmp = tmp.loc[tmp["symbol"] == chosen_symbol]
            df_base = tmp if _is_ohlc(tmp) else pd.DataFrame()
        except Exception:
            df_base = pd.DataFrame()
    # Si cargamos CSV plano, recortar por months si corresponde
    try:
        if not df_base.empty and "timestamp" in df_base.columns and int(args.months) > 0:
            ts = pd.to_datetime(df_base["timestamp"], utc=True, errors="coerce")
            if ts.notna().any():
                end = ts.max()
                cutoff = end - pd.DateOffset(months=int(args.months))
                before = len(df_base)
                df_base = df_base.loc[ts >= cutoff].reset_index(drop=True)
                after = len(df_base)
                if after < before:
                    print(f"Info: usando ventana de ~{args.months} meses: {after} filas (de {before}).")
    except Exception:
        pass

    # Reducir tamaño en modo quick para acelerar rolling y pruebas
    if args.quick and not df_base.empty:
        try:
            if "timestamp" in df_base.columns:
                ts = pd.to_datetime(df_base["timestamp"], errors="coerce", utc=True)
                cutoff = ts.max() - pd.Timedelta(days=30)
                df_base = df_base.loc[ts >= cutoff].reset_index(drop=True)
            # fallback por filas
            if len(df_base) > 6000:
                df_base = df_base.tail(6000).reset_index(drop=True)
        except Exception:
            try:
                df_base = df_base.tail(5000).reset_index(drop=True)
            except Exception:
                pass

    # Grid
    rsi_buy_values, rsi_sell_values, adx_limits, min_votes, sl_mults, tp_mults, atr_multipliers = _build_grid(args.quick)
    comb_total = len(rsi_buy_values) * len(rsi_sell_values) * len(adx_limits) * len(min_votes) * len(sl_mults) * len(tp_mults) * len(atr_multipliers)
    comb_num = 1

    resultados: List[Dict[str, Any]] = []
    fallos: List[Dict[str, Any]] = []

    for rsi_buy in rsi_buy_values:
        for rsi_sell in rsi_sell_values:
            if rsi_sell <= rsi_buy:
                continue
            for adx in adx_limits:
                for votes in min_votes:
                    for sl in sl_mults:
                        for tp in tp_mults:
                            for atr_mul in atr_multipliers:
                                print(f"\n=== Probando combinación {comb_num}/{comb_total} ===")
                                print(f"Parámetros: RSI_BUY={rsi_buy}, RSI_SELL={rsi_sell}, ADX={adx}, VOTES={votes}, SL={sl}, TP={tp}, ATR_MULT={atr_mul}")
                                try:
                                    trades_df, resumen = _run_one_combo(rsi_buy, rsi_sell, adx, votes, sl, tp, atr_mul, df_base, base_dir)
                                    adv = compute_advanced_metrics(trades_df)
                                    skew_flag = (not np.isnan(adv["skew_r_multiple"])) and (abs(adv["skew_r_multiple"]) > SKEW_THRESHOLD)
                                    few_trades_flag = adv["trades"] < MIN_TRADES_REQUIRED
                                    resumen_num = {k: v for k, v in (resumen or {}).items() if isinstance(v, (int, float, str))}
                                    row = {
                                        "RSI_BUY": rsi_buy, "RSI_SELL": rsi_sell, "ADX_LIMIT": adx, "MIN_VOTES": votes,
                                        "SL_MULT": sl, "TP_MULT": tp, "ATR_MULT": atr_mul,
                                        **resumen_num, **adv,
                                        "skew_extreme": bool(skew_flag), "few_trades": bool(few_trades_flag),
                                    }
                                    resultados.append(row)
                                    print(f"OK: trades={adv['trades']} pf={adv['pf_net']:.3f} exp={adv['expectancy']:.4f} skew={adv['skew_r_multiple']:.2f}")
                                except Exception as e:
                                    fallos.append({"params": [rsi_buy, rsi_sell, adx, votes, sl, tp, atr_mul], "error": str(e)})
                                    print(f"❌ Error en combinación {comb_num}: {e}")
                                finally:
                                    comb_num += 1

    results_df = pd.DataFrame(resultados)
    results_df.to_csv("grid_results.csv", index=False)
    print(f"Guardado: grid_results.csv ({len(results_df)} filas)")

    # Resumen
    md = ["# Grid Search — Resumen de Setups Elegibles", ""]
    if results_df.empty:
        md.append("No hay resultados exitosos.")
    else:
        elig = results_df[results_df.apply(_eligible, axis=1)].copy()
        if elig.empty:
            md.append("No se encontraron setups que cumplan todos los criterios.")
        else:
            elig = elig.sort_values(["expectancy", "pf_net"], ascending=[False, False]).head(5)
            md += ["## Top 5 setups", "", "| RSI_BUY | RSI_SELL | ADX | VOTES | SL | TP | ATR | trades | pf_net | expectancy | rec_ratio | winrate_roll | r_med_net | pf_ratio_min | skew_r | fees% | tpd |",
                   "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for _, r in elig.iterrows():
                md.append(f"| {r['RSI_BUY']} | {r['RSI_SELL']} | {r['ADX_LIMIT']} | {r['MIN_VOTES']} | {r['SL_MULT']:.2f} | {r['TP_MULT']:.2f} | {r['ATR_MULT']:.2f} | {int(r['trades'])} | {r['pf_net']:.3f} | {r['expectancy']:.4f} | {r['recovery_ratio']:.3f} | {r['winrate_rolling']:.1f}% | {r['r_multiple_median_net']:.3f} | {r.get('pf_ratio_min', np.nan):.3f} | {r.get('skew_r_multiple', np.nan):.2f} | {r.get('fees_share_pct', np.nan):.1f} | {r.get('trades_per_day', np.nan):.2f} |")
    md += ["", "## Criterios de exclusión aplicados",
           "- Expectancy <= 0",
           "- Recovery ratio < -0.5",
           "- r_multiple_median_net <= 0",
           "- Winrate rolling <= 45%",
           f"- Skew extremo |skew| > {SKEW_THRESHOLD}",
           f"- Menos de {MIN_TRADES_REQUIRED} trades",
           "- fees_share_pct > 40%",
           "- trades_per_day > 6"]
    Path("grid_summary.md").write_text("\n".join(md), encoding="utf-8")
    print("Guardado: grid_summary.md")

    # Near-miss opcional
    if args.near_miss and not results_df.empty:
        near_df = results_df[~results_df.apply(_eligible, axis=1)]
        near_df = near_df[near_df.apply(_near_miss, axis=1)].copy()
        if near_df.empty:
            Path("grid_nearmiss.md").write_text("# Near-miss — No se hallaron candidatos con gating relajado\n", encoding="utf-8")
            print("Guardado: grid_nearmiss.md (vacío)")
        else:
            # ordenar por pf_net desc, luego expectancy desc, luego trades desc
            near_df = near_df.sort_values(["pf_net", "expectancy", "trades"], ascending=[False, False, False]).head(int(args.near_top))
            lines = ["# Near-miss — Candidatos bajo gating relajado", "",
                     f"Criterios: trades≥{NEAR_MIN_TRADES}, winrate_roll>{NEAR_WINRATE_MIN}%, |skew|≤{NEAR_SKEW_THRESHOLD}, fees%≤{NEAR_FEES_MAX}, tpd≤{NEAR_TRADES_PER_DAY_MAX}, recovery≥{NEAR_RECOVERY_MIN}, pf_net≥{NEAR_PF_MIN} o expectancy>{NEAR_EXPECTANCY_FLOOR}",
                     "", "| RSI_BUY | RSI_SELL | ADX | VOTES | SL | TP | ATR | trades | pf_net | expectancy | rec_ratio | winrate_roll | r_med_net | skew_r | fees% | tpd |",
                     "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for _, r in near_df.iterrows():
                lines.append(
                    f"| {r['RSI_BUY']} | {r['RSI_SELL']} | {r['ADX_LIMIT']} | {r['MIN_VOTES']} | {r['SL_MULT']:.2f} | {r['TP_MULT']:.2f} | {r['ATR_MULT']:.2f} | {int(r['trades'])} | {r['pf_net']:.3f} | {r['expectancy']:.4f} | {r['recovery_ratio']:.3f} | {r['winrate_rolling']:.1f}% | {r.get('r_multiple_median_net', np.nan):.3f} | {r.get('skew_r_multiple', np.nan):.2f} | {r.get('fees_share_pct', np.nan):.1f} | {r.get('trades_per_day', np.nan):.2f} |"
                )
            Path("grid_nearmiss.md").write_text("\n".join(lines), encoding="utf-8")
            print(f"Guardado: grid_nearmiss.md ({len(near_df)} filas)")
    print("\n=== Grid search completado ===")
    print(f"Total combinaciones exitosas: {len(resultados)}")
    print(f"Total combinaciones con error: {len(fallos)}")


 

# ---------------------
# Orquestador Fase 1 — Variantes Beta B (B1–B4)
# ---------------------

def _git_commit_or_none(cwd: Path) -> str | None:
    try:
        res = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=str(cwd), capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_csv_cols(csv_path: Path) -> List[str]:
    try:
        df = pd.read_csv(csv_path, nrows=5)
        return df.columns.tolist()
    except Exception:
        return []


def _non_empty_file(p: Path) -> bool:
    try:
        return p.exists() and p.stat().st_size > 0
    except Exception:
        return False


def _run_variant(base_dir: Path, variant: str, base_params: Dict[str, Any], overrides: Dict[str, Any], out_root: Path, data_path: str, symbols: str, baseline_grid: Path | None) -> Dict[str, Any]:
    start_ts = datetime.now(timezone.utc)
    out_dir = out_root / variant
    _ensure_dir(out_dir)

    # Salidas por variante
    out_csv = out_dir / f"grid_results_beta_{variant}.csv"
    out_md = out_dir / f"delta_beta_{variant}.md"
    out_tr = out_dir / f"trades_enriched_beta_{variant}.csv"
    out_dbg = out_dir / f"debug_counters_beta_{variant}.csv"

    # Construir args CLI del harness
    script = base_dir / "scripts" / "ab_sesgo_fix.py"
    symbols_list = symbols.split()
    cmd: List[str] = [
        sys.executable,
        str(script),
        "--master", str(data_path),
        "--symbols", *symbols_list,
        "--months", str(base_params.get("months", 12)),
        "--bar-tolerance", str(base_params.get("bar_tolerance", 6)),
        "--rsi-tolerance", str(base_params.get("rsi_tolerance", 2)),
        "--admission", base_params.get("admission", "conditional"),
        "--strict-proximity", str(overrides.get("strict_proximity", base_params.get("strict_proximity", 2))),
        "--min-atr-pct", str(overrides.get("min_atr_pct", base_params.get("min_atr_pct", 0.22))),
        "--min-bbw-pct", str(overrides.get("min_bbw_pct", base_params.get("min_bbw_pct", 0.15))),
        "--exclude-hours", overrides.get("exclude_hours", base_params.get("exclude_hours", "0,1,2,3,4,5,6,12,13,14")),
        "--neutral-min-votes", str(base_params.get("neutral_min_votes", 4)),
        "--range-min-votes", str(base_params.get("range_min_votes", 3)),
        "--min-mfe-mae-ratio", str(overrides.get("min_mfe_mae_ratio", base_params.get("min_mfe_mae_ratio", 1.4))),
        "--out_csv", str(out_csv),
        "--out_md", str(out_md),
        "--out_trades", str(out_tr),
        "--debug-csv", str(out_dbg),
    ]

    # Ejecutar sin shell y capturar salida
    stdout_path = out_dir / "stdout.log"
    stderr_path = out_dir / "stderr.log"
    proc = subprocess.run(cmd, cwd=str(base_dir), capture_output=True, text=True)
    try:
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    except Exception:
        pass

    end_ts = datetime.now(timezone.utc)

    # Enriquecer delta con encabezado de paridad base + cambio de variante
    try:
        if _non_empty_file(out_md):
            original = Path(out_md).read_text(encoding="utf-8", errors="ignore")
            header_lines = [
                f"# Delta Beta {variant} — Paridad base + cambio de variante",
                "",
                "Base (parámetros fijos): " + \
                    f"months={base_params.get('months')}, strict_proximity={base_params.get('strict_proximity')}, " + \
                    f"min_mfe_mae_ratio={base_params.get('min_mfe_mae_ratio')}, min_atr_pct={base_params.get('min_atr_pct')}, min_bbw_pct={base_params.get('min_bbw_pct')}, " + \
                    f"admission={base_params.get('admission')}, neutral_min_votes={base_params.get('neutral_min_votes')}, range_min_votes={base_params.get('range_min_votes')}, " + \
                    f"exclude_hours={base_params.get('exclude_hours')}, bar_tolerance={base_params.get('bar_tolerance')}, rsi_tolerance={base_params.get('rsi_tolerance')}",
                "Cambio aplicado (overrides): " + json.dumps(overrides, ensure_ascii=False),
                "",
            ]
            Path(out_md).write_text("\n".join(header_lines) + original if original.startswith("#") else "\n".join(header_lines + [original]), encoding="utf-8")
    except Exception:
        pass

    # Validaciones
    validations: Dict[str, Any] = {}
    files = {
        "grid": str(out_csv),
        "delta": str(out_md),
        "trades": str(out_tr),
        "debug": str(out_dbg),
    }
    validations["files_exist"] = {k: _non_empty_file(Path(v)) for k, v in files.items()}
    validations["all_exist_non_empty"] = all(validations["files_exist"].values())

    # Paridad de columnas con baseline en grid
    grid_cols = _read_csv_cols(out_csv)
    baseline_cols: List[str] = []
    if baseline_grid and baseline_grid.exists():
        baseline_cols = _read_csv_cols(baseline_grid)
    validations["grid_columns_match_baseline"] = (grid_cols == baseline_cols) if baseline_cols else True

    # Chequeo de columnas esperadas en debug counters
    dbg_cols = _read_csv_cols(out_dbg)
    expected_dbg = {"dbg_alignment_fail", "dbg_dist_too_far", "dbg_no_trades_in_window", "candidates", "admitted"}
    validations["debug_has_expected_columns"] = expected_dbg.issubset(set(dbg_cols)) if dbg_cols else False

    # Manifest
    manifest = {
        "variant": variant,
        "timestamp_start_utc": start_ts.isoformat(),
        "timestamp_end_utc": end_ts.isoformat(),
        "duration_seconds": (end_ts - start_ts).total_seconds(),
        "commit": _git_commit_or_none(base_dir),
        "cmdline": cmd,
        "symbols": symbols.split(),
        "base_params": base_params,
        "overrides": overrides,
        "return_code": proc.returncode,
        "outputs": files,
        "validations": validations,
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return manifest


def _run_fase1_orchestrator(base_dir: Path, months: int, symbols: str, out_root: str, data_path: str) -> None:
    print("Iniciando Fase 1 — Variantes Beta B (B1–B4)")
    out_root_path = base_dir / out_root
    _ensure_dir(out_root_path)

    # Parámetros base (fijos)
    base_params: Dict[str, Any] = {
        "months": months,
        "strict_proximity": 2,
        "min_mfe_mae_ratio": 1.4,
        "min_atr_pct": 0.22,
        "min_bbw_pct": 0.15,
        "admission": "conditional",
        "neutral_min_votes": 4,
        "range_min_votes": 3,
        "exclude_hours": "0,1,2,3,4,5,6,12,13,14",
        "bar_tolerance": 6,
        "rsi_tolerance": 2.0,
    }

    # Baseline de columnas para paridad (si existe)
    baseline_grid = base_dir / "grid_results_beta_B.csv"

    variants: Dict[str, Dict[str, Any]] = {
        "B1": {"strict_proximity": 1},
        "B2": {"min_mfe_mae_ratio": 1.6},
        "B3": {"min_atr_pct": 0.25, "min_bbw_pct": 0.18},
        # Si base ya excluye esas horas, ampliar restricción a 0–8 y 12–14
        "B4": {"exclude_hours": "0,1,2,3,4,5,6,7,8,12,13,14"},
    }

    manifests: Dict[str, Any] = {}
    for v, ov in variants.items():
        print(f"\n>> Ejecutando variante {v} …")
        m = _run_variant(
            base_dir=base_dir,
            variant=v,
            base_params=base_params,
            overrides=ov,
            out_root=out_root_path,
            data_path=str(base_dir / data_path),
            symbols=symbols,
            baseline_grid=baseline_grid,
        )
        status = "OK" if (m.get("return_code", 1) == 0 and m.get("validations", {}).get("all_exist_non_empty", False)) else "FAIL"
        print(f"Variante {v} finalizada con estado: {status}")

    # Resumen rápido
    print("\nFase 1 completada. Artefactos en:")
    for v in variants.keys():
        print(f"- {out_root_path / v}")


# (def _run_fase1_ext_orchestrator consolidado más abajo)


# ---------------------
# Orquestador Fase 1_ext — Interacciones acotadas (A1–A4, B1–B4 [+B5–B6])
# ---------------------

def _load_grid_safe(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def _extract_symbol_rows(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df.empty:
        return df
    col = None
    for c in ("symbol", "Symbol", "SYMBOL"):
        if c in df.columns:
            col = c
            break
    if not col:
        return df
    return df.loc[df[col] == symbol].copy()


def _run_fase1_ext_orchestrator(base_dir: Path, months: int, symbols: str, out_root: str, data_path: str, include_optional: bool = True) -> None:
    print("Iniciando Fase 1_ext — Interacciones acotadas (A1–A4 y B1–B4 [+B5–B6])")
    out_root_path = base_dir / out_root
    _ensure_dir(out_root_path)

    # Parámetros base (idénticos a Fase 1)
    base_params: Dict[str, Any] = {
        "months": int(months or 12),
        "strict_proximity": 2,
        "min_mfe_mae_ratio": 1.4,
        "min_atr_pct": 0.22,
        "min_bbw_pct": 0.15,
        "admission": "conditional",
        "neutral_min_votes": 4,
        "range_min_votes": 3,
        "exclude_hours": "0,1,2,3,4,5,6,12,13,14",
        "bar_tolerance": 6,
        "rsi_tolerance": 2.0,
    }

    # Definición de combos
    # Bloque A — matching × guardrail
    combos: Dict[str, Dict[str, Any]] = {
        "A1": {"strict_proximity": 1, "min_mfe_mae_ratio": 1.4},
        "A2": {"strict_proximity": 1, "min_mfe_mae_ratio": 1.6},
        "A3": {"strict_proximity": 2, "min_mfe_mae_ratio": 1.4},  # base de Fase 1
        "A4": {"strict_proximity": 2, "min_mfe_mae_ratio": 1.6},
    }
    # Bloque B — pisos × horario
    combos.update({
        "B1": {"min_atr_pct": 0.22, "min_bbw_pct": 0.15, "exclude_hours": "0,1,2,3,4,5,6,12,13,14"},
        "B2": {"min_atr_pct": 0.22, "min_bbw_pct": 0.15, "exclude_hours": "0,1,2,3,4,5,6,7,8,12,13,14"},
        "B3": {"min_atr_pct": 0.25, "min_bbw_pct": 0.18, "exclude_hours": "0,1,2,3,4,5,6,12,13,14"},
        "B4": {"min_atr_pct": 0.25, "min_bbw_pct": 0.18, "exclude_hours": "0,1,2,3,4,5,6,7,8,12,13,14"},
    })
    if include_optional:
        combos.update({
            "B5": {"min_atr_pct": 0.24, "min_bbw_pct": 0.17, "exclude_hours": base_params["exclude_hours"]},
            "B6": {"min_atr_pct": 0.24, "min_bbw_pct": 0.17, "exclude_hours": "0,1,2,3,4,5,6,7,8,12,13,14"},
        })

    # Baseline de columnas para paridad (usa grid_results_beta_B.csv si existe)
    baseline_grid = base_dir / "grid_results_beta_B.csv"

    manifests: Dict[str, Any] = {}
    for variant, overrides in combos.items():
        print(f"\n>> Ejecutando combo {variant} …")
        m = _run_variant(
            base_dir=base_dir,
            variant=variant,
            base_params=base_params,
            overrides=overrides,
            out_root=out_root_path,
            data_path=str(base_dir / data_path),
            symbols=symbols,
            baseline_grid=baseline_grid,
        )
        manifests[variant] = m
        status = "OK" if (m.get("return_code", 1) == 0 and m.get("validations", {}).get("all_exist_non_empty", False)) else "FAIL"
        print(f"Combo {variant} finalizado con estado: {status}")

    # Generar resumen consolidado
    syms = symbols.split()
    lines: List[str] = ["# Fase 1_ext — Resumen de interacciones (A y B)", "", f"Ventana: {base_params['months']} meses; Costos/slippage fijos; Counters habilitados.", "", "## Combos ejecutados", ""]
    lines += ["- " + v for v in sorted(combos.keys())]
    lines += ["", "## Resultados por símbolo", ""]

    # Para robustez se tomará A3 como base (strict=2, ratio=1.4) y, si existe en Fase1/B2, comparar también contra B2 de Fase 1
    # Intentar cargar Fase1/B2 grid para referencia
    fase1_b2_grid = base_dir / "data" / "backtesting" / "ANALISIS" / "Fase1" / "B2" / "grid_results_beta_B2.csv"
    df_b2 = _load_grid_safe(fase1_b2_grid)

    # Agregar tablas por símbolo
    def _metric_or_nan(df: pd.DataFrame, sym: str, col: str) -> float:
        d = _extract_symbol_rows(df, sym)
        if d.empty or col not in d.columns:
            return np.nan
        v = pd.to_numeric(d[col], errors="coerce")
        return float(v.iloc[0]) if len(v) else np.nan

    # Cargar todos los grids
    grid_by_variant: Dict[str, pd.DataFrame] = {}
    for v in combos.keys():
        p = out_root_path / v / f"grid_results_beta_{v}.csv"
        grid_by_variant[v] = _load_grid_safe(p)

    # Construir tablas
    for sym in syms:
        lines += [f"### {sym}", "", "| Variant | pf_net | expectancy | max_dd | trades/día | fees% | top_regime_share |", "|---|---:|---:|---:|---:|---:|---:|"]
        for v in sorted(combos.keys()):
            dfv = grid_by_variant.get(v, pd.DataFrame())
            pf = _metric_or_nan(dfv, sym, "pf_net")
            ex = _metric_or_nan(dfv, sym, "expectancy")
            dd = _metric_or_nan(dfv, sym, "max_dd")
            tpd = _metric_or_nan(dfv, sym, "trades_per_day")
            fees = _metric_or_nan(dfv, sym, "fees_share_pct")
            trs = _metric_or_nan(dfv, sym, "top_regime_share")
            lines.append(f"| {v} | {pf:.3f} | {ex:.4f} | {dd:.0f} | {tpd:.3f} | {fees:.2f} | {trs:.2f} |")
        lines.append("")

    # Mejor por símbolo con criterio compuesto 60/30/10 (pf_net↑, -|max_dd|↑, expectancy↑) y guardrail fees/trades/top_regime
    lines += ["## Mejor por símbolo (composite 60/30/10 con guardrails)", ""]
    lines += ["| Symbol | Winner | Score | pf_net | expectancy | max_dd | fees% | tpd | top_regime_share |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    def _to_float(x: Any) -> float:
        try:
            return float(x)
        except Exception:
            return np.nan

    for sym in syms:
        rows = []
        for v, dfv in grid_by_variant.items():
            if dfv.empty:
                continue
            pf = _metric_or_nan(dfv, sym, "pf_net")
            ex = _metric_or_nan(dfv, sym, "expectancy")
            dd = _metric_or_nan(dfv, sym, "max_dd")
            tpd = _metric_or_nan(dfv, sym, "trades_per_day")
            fees = _metric_or_nan(dfv, sym, "fees_share_pct")
            trs = _metric_or_nan(dfv, sym, "top_regime_share")
            rows.append({"v": v, "pf": pf, "ex": ex, "dd": dd, "tpd": tpd, "fees": fees, "trs": trs})
        if not rows:
            continue
        dfm = pd.DataFrame(rows)
        # normalización simple por z-score recortado
        def _z(x: pd.Series) -> pd.Series:
            mu, sd = x.mean(), x.std()
            if sd == 0 or np.isnan(sd):
                return pd.Series(np.zeros(len(x)))
            z = (x - mu) / sd
            return z.clip(-3, 3)
        s_pf = _z(dfm["pf"]).fillna(0).to_numpy()
        s_dd = _z(-dfm["dd"].abs()).fillna(0).to_numpy()
        s_ex = _z(dfm["ex"]).fillna(0).to_numpy()
        score = 0.6 * s_pf + 0.3 * s_dd + 0.1 * s_ex

        # guardrails: fees <= min(b2_fase1_fees + 0.5, 50), tpd dentro ±15% vs B2 Fase1 si existe; trs <= 0.45
        fees_b2 = _metric_or_nan(df_b2, sym, "fees_share_pct") if not df_b2.empty else np.nan
        tpd_b2 = _metric_or_nan(df_b2, sym, "trades_per_day") if not df_b2.empty else np.nan
        fees_cap = (fees_b2 + 0.5) if not np.isnan(fees_b2) else np.inf
        fees_arr = dfm["fees"].apply(_to_float).to_numpy()
        trs_arr = dfm["trs"].apply(_to_float).to_numpy()
        tpd_arr = dfm["tpd"].apply(_to_float).to_numpy()
        mask = np.ones(len(score), dtype=bool)
        mask &= ~(~np.isnan(fees_arr) & (fees_arr > np.minimum(fees_cap, 50.0)))
        mask &= ~(~np.isnan(trs_arr) & (trs_arr > 0.45))
        if not np.isnan(tpd_b2):
            mask &= ~(~np.isnan(tpd_arr) & (np.abs(tpd_arr - tpd_b2) > (0.15 * tpd_b2)))
        # Aplicar máscara: asignar -inf a descalificados
        score_masked = np.where(mask, score, -np.inf)
        j = int(np.argmax(score_masked))
        w = dfm.iloc[j]
    lines.append(f"| {sym} | {w['v']} | {float(score_masked[j]):.3f} | {w['pf']:.3f} | {w['ex']:.4f} | {w['dd']:.0f} | {w['fees']:.2f} | {w['tpd']:.3f} | {w['trs']:.2f} |")

    # Robustez vs base A3 y vs B2 Fase1
    lines += ["", "## Robustez por símbolo (majors)", ""]
    majors = [s for s in syms if s in ("BTCUSDT", "ETHUSDT", "BNBUSDT")]
    for sym in majors:
        df_base_a3 = grid_by_variant.get("A3", pd.DataFrame())
        pf_base = _metric_or_nan(df_base_a3, sym, "pf_net")
        ex_base = _metric_or_nan(df_base_a3, sym, "expectancy")
        dd_base = _metric_or_nan(df_base_a3, sym, "max_dd")
        fees_base = _metric_or_nan(df_base_a3, sym, "fees_share_pct")
        tpd_base = _metric_or_nan(df_base_a3, sym, "trades_per_day")

        pf_b2 = _metric_or_nan(df_b2, sym, "pf_net") if not df_b2.empty else np.nan
        ex_b2 = _metric_or_nan(df_b2, sym, "expectancy") if not df_b2.empty else np.nan
        dd_b2 = _metric_or_nan(df_b2, sym, "max_dd") if not df_b2.empty else np.nan
        fees_b2 = _metric_or_nan(df_b2, sym, "fees_share_pct") if not df_b2.empty else np.nan
        tpd_b2 = _metric_or_nan(df_b2, sym, "trades_per_day") if not df_b2.empty else np.nan

        lines += [f"### {sym} — Criterios", "", "- pf_net ≥ max(base, 1.8) o dentro de ±5% vs B2 (Fase 1)", "- expectancy ≥ base", "- max_dd ≤ base × 0.95 (o compensado por pf_net)", "- trades/día dentro de ±15% vs B2; fees ≤ B2 + 0.5 p.p.", "- top_regime_share ≤ 0.45", "- Counters sanos: alignment_fail=0; dist_too_far / no_trades_in_window no suben >30% vs F1"]
        # Evaluar cada combo
        lines += ["", "| Variant | pf_net | Δpf vs B2 | expectancy | max_dd | trades/día | fees% | OK? |", "|---|---:|---:|---:|---:|---:|---:|---|"]
        for v, dfv in grid_by_variant.items():
            if dfv.empty:
                continue
            pf = _metric_or_nan(dfv, sym, "pf_net")
            ex = _metric_or_nan(dfv, sym, "expectancy")
            dd = _metric_or_nan(dfv, sym, "max_dd")
            fees = _metric_or_nan(dfv, sym, "fees_share_pct")
            tpd = _metric_or_nan(dfv, sym, "trades_per_day")
            # checks
            ok_pf = (not np.isnan(pf)) and (pf >= max(pf_base if not np.isnan(pf_base) else 0, 1.8) or (not np.isnan(pf_b2) and pf >= 0.95 * pf_b2))
            ok_ex = (not np.isnan(ex)) and (np.isnan(ex_base) or ex >= ex_base)
            ok_dd = (not np.isnan(dd)) and (np.isnan(dd_base) or dd <= 0.95 * dd_base or (not np.isnan(pf) and not np.isnan(pf_base) and pf > pf_base))
            ok_tpd = (np.isnan(tpd_b2) or (not np.isnan(tpd) and abs(tpd - tpd_b2) <= 0.15 * tpd_b2))
            ok_fees = (np.isnan(fees_b2) or (not np.isnan(fees) and fees <= fees_b2 + 0.5))
            ok = all([ok_pf, ok_ex, ok_dd, ok_tpd, ok_fees])
            dpf = (pf - pf_b2) if (not np.isnan(pf) and not np.isnan(pf_b2)) else np.nan
            lines.append(f"| {v} | {pf:.3f} | {dpf:+.3f} | {ex:.4f} | {dd:.0f} | {tpd:.3f} | {fees:.2f} | {'OK' if ok else 'NO'} |")
        lines.append("")

    # Guardar resumen
    (out_root_path / "grid_summary_fase1_ext.md").write_text("\n".join(lines), encoding="utf-8")
    print("Guardado: grid_summary_fase1_ext.md")

    # Pistas de dónde están artefactos
    print("\nFase 1_ext completada. Artefactos en:")
    for v in combos.keys():
        print(f"- {out_root_path / v}")


if __name__ == "__main__":
    main()
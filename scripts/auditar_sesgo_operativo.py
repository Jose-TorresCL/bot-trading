import os
import argparse
from typing import List, Dict, Any, Tuple
import sys
import pandas as pd
import numpy as np

# Importar utilidades del proyecto sin ejecutar el motor/trades
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.gestor_indicadores import calcular_todos_los_indicadores


def _ensure_pct_cols(df_ind: pd.DataFrame, window: int = 200) -> pd.DataFrame:
    df = df_ind.copy()
    # ATR_pct: percentil rolling de la última barra
    if "ATR" in df.columns and "ATR_pct" not in df.columns:
        def _pct_rank_last(x):
            s = pd.Series(x).dropna()
            if s.empty:
                return np.nan
            return float(s.rank(pct=True).iloc[-1])
        df["ATR_pct"] = df["ATR"].rolling(window, min_periods=10).apply(_pct_rank_last, raw=False)
    if "BB_Width" in df.columns and "BBW_pct" not in df.columns:
        def _pct_rank_last(x):
            s = pd.Series(x).dropna()
            if s.empty:
                return np.nan
            return float(s.rank(pct=True).iloc[-1])
        df["BBW_pct"] = df["BB_Width"].rolling(window, min_periods=10).apply(_pct_rank_last, raw=False)
    return df


def _classify_regime_row(row: pd.Series) -> str:
    try:
        adx = float(row.get("ADX", np.nan)) if row.get("ADX") is not None else np.nan
        atrp = float(row.get("ATR_pct", 0.5) or 0.5)
        bbwp = float(row.get("BBW_pct", 0.5) or 0.5)
        if adx >= 25 and bbwp >= 0.5:
            return "trend"
        if adx < 18 and bbwp < 0.4:
            return "range"
        if atrp > 0.7:
            return "high_vol"
        if atrp < 0.3:
            return "low_vol"
        return "neutral"
    except Exception:
        return "neutral"


def _compute_votes_long(row: pd.Series, rsi_buy: float, adx_limit: float) -> int:
    v = 0
    rsi = row.get("RSI")
    adx = row.get("ADX")
    atrp = row.get("ATR_pct", 0.5)
    bbwp = row.get("BBW_pct", 0.5)
    macd_h = row.get("hist")
    try:
        if rsi is not None and rsi < rsi_buy:
            v += 1
        if adx is not None and adx >= adx_limit:
            v += 1
        if 0.3 <= (atrp if atrp is not None else 0.5) <= 0.85:
            v += 1
        if macd_h is not None and macd_h > 0:
            v += 1
        if bbwp is not None and bbwp < 0.45:
            v += 1
    except Exception:
        pass
    return v


def audit_symbol(df_sym: pd.DataFrame, symbol: str,
                 rsi_buys: List[int], adx_limits: List[int], min_votes_list: List[int],
                 min_atr_pct: float = 0.30, min_bbw_pct: float = 0.15) -> Dict[str, Any]:
    # Calcular indicadores sin ejecutar estrategias ni trades
    ind_list = calcular_todos_los_indicadores(df_sym, export_snapshot=False)
    if not ind_list:
        return {"symbol": symbol, "empty": True}
    di = pd.DataFrame(ind_list)
    di = _ensure_pct_cols(di)
    # anexar tiempo y hora para cortes
    ts = pd.to_datetime(df_sym["timestamp"], utc=True, errors="coerce") if "timestamp" in df_sym.columns else pd.date_range(periods=len(di), freq="15min")
    di["timestamp"] = ts
    di["hour"] = di["timestamp"].dt.hour
    # régimen
    di["market_regime"] = di.apply(_classify_regime_row, axis=1)

    # Result containers
    filter_counters: Dict[str, Dict[str, int]] = {}
    regime_block: Dict[str, Dict[str, Dict[str, int]]] = {}
    hours_block: Dict[str, Dict[str, Dict[str, int]]] = {}
    pass_count_total = 0
    base_count_total = 0

    for rsi_buy in rsi_buys:
        for adx_lim in adx_limits:
            for mv in min_votes_list:
                key = f"RSI{rsi_buy}_ADX{adx_lim}_V{mv}"
                counts = {"base": 0, "pass": 0, "blocked_RSI": 0, "blocked_ADX": 0, "blocked_ATR": 0, "blocked_BBW": 0, "blocked_VOTES": 0}
                reg_counts: Dict[str, Dict[str, int]] = {}
                hour_counts: Dict[str, Dict[str, int]] = {}
                for i, row in di.iterrows():
                    rsi = row.get("RSI")
                    adx = row.get("ADX")
                    atrp = row.get("ATR_pct")
                    bbwp = row.get("BBW_pct")
                    regime = row.get("market_regime", "neutral")
                    hval = row.get("hour", 0)
                    try:
                        hour = int(hval) if not (pd.isna(hval)) else 0
                    except Exception:
                        hour = 0
                    # base (RSI)
                    if rsi is None or np.isnan(rsi) or rsi >= rsi_buy:
                        counts["blocked_RSI"] += 1
                        continue
                    counts["base"] += 1
                    # ADX
                    if adx is None or np.isnan(adx) or adx < adx_lim:
                        counts["blocked_ADX"] += 1
                        reg_counts.setdefault(regime, {}).setdefault("blocked_ADX", 0)
                        reg_counts[regime]["blocked_ADX"] += 1
                        hour_bucket = f"{(hour//4)*4:02d}-{(hour//4)*4+3:02d}"
                        hour_counts.setdefault(hour_bucket, {}).setdefault("blocked_ADX", 0)
                        hour_counts[hour_bucket]["blocked_ADX"] += 1
                        continue
                    # ATR_pct min
                    if atrp is None or np.isnan(atrp) or atrp < min_atr_pct:
                        counts["blocked_ATR"] += 1
                        reg_counts.setdefault(regime, {}).setdefault("blocked_ATR", 0)
                        reg_counts[regime]["blocked_ATR"] += 1
                        hour_bucket = f"{(hour//4)*4:02d}-{(hour//4)*4+3:02d}"
                        hour_counts.setdefault(hour_bucket, {}).setdefault("blocked_ATR", 0)
                        hour_counts[hour_bucket]["blocked_ATR"] += 1
                        continue
                    # BBW_pct min
                    if bbwp is None or np.isnan(bbwp) or bbwp < min_bbw_pct:
                        counts["blocked_BBW"] += 1
                        reg_counts.setdefault(regime, {}).setdefault("blocked_BBW", 0)
                        reg_counts[regime]["blocked_BBW"] += 1
                        hour_bucket = f"{(hour//4)*4:02d}-{(hour//4)*4+3:02d}"
                        hour_counts.setdefault(hour_bucket, {}).setdefault("blocked_BBW", 0)
                        hour_counts[hour_bucket]["blocked_BBW"] += 1
                        continue
                    # Votes
                    votes = _compute_votes_long(row, rsi_buy=rsi_buy, adx_limit=adx_lim)
                    if votes < mv:
                        counts["blocked_VOTES"] += 1
                        reg_counts.setdefault(regime, {}).setdefault("blocked_VOTES", 0)
                        reg_counts[regime]["blocked_VOTES"] += 1
                        hour_bucket = f"{(hour//4)*4:02d}-{(hour//4)*4+3:02d}"
                        hour_counts.setdefault(hour_bucket, {}).setdefault("blocked_VOTES", 0)
                        hour_counts[hour_bucket]["blocked_VOTES"] += 1
                        continue
                    # pasa todos
                    counts["pass"] += 1
                    reg_counts.setdefault(regime, {}).setdefault("pass", 0)
                    reg_counts[regime]["pass"] += 1
                    hour_bucket = f"{(hour//4)*4:02d}-{(hour//4)*4+3:02d}"
                    hour_counts.setdefault(hour_bucket, {}).setdefault("pass", 0)
                    hour_counts[hour_bucket]["pass"] += 1

                filter_counters[key] = counts
                regime_block[key] = {k: {**v} for k, v in reg_counts.items()}
                hours_block[key] = {k: {**v} for k, v in hour_counts.items()}
                pass_count_total += counts["pass"]
                base_count_total += counts["base"]

    # resumen comparativo compras vs ventas (simple, sin grilla completa)
    # Ventas: usar RSIsell=70, ADX=23 como baseline
    sells = 0
    buys = pass_count_total
    try:
        rsi_sell = 70
        adx_lim = 23
        mv = 3
        s_counts = {"base": 0, "pass": 0}
        for i, row in di.iterrows():
            rsi = row.get("RSI")
            adx = row.get("ADX")
            atrp = row.get("ATR_pct")
            bbwp = row.get("BBW_pct")
            if rsi is None or np.isnan(rsi) or rsi <= rsi_sell:
                continue
            s_counts["base"] += 1
            if adx is None or np.isnan(adx) or adx < adx_lim:
                continue
            if atrp is None or np.isnan(atrp) or atrp < 0.30:
                continue
            if bbwp is None or np.isnan(bbwp) or bbwp < 0.15:
                continue
            votes = 0
            try:
                # votos para short (simétrico)
                if rsi is not None and rsi > rsi_sell:
                    votes += 1
                if adx is not None and adx >= adx_lim:
                    votes += 1
                if 0.3 <= (atrp if atrp is not None else 0.5) <= 0.85:
                    votes += 1
                hist = row.get("hist")
                if hist is not None and hist < 0:
                    votes += 1
                if bbwp is not None and bbwp < 0.45:
                    votes += 1
            except Exception:
                pass
            if votes >= mv:
                s_counts["pass"] += 1
        sells = s_counts["pass"]
    except Exception:
        sells = 0

    return {
        "symbol": symbol,
        "filter_counters": filter_counters,
        "regime_block": regime_block,
        "hours_block": hours_block,
        "buys_pass": buys,
        "base_candidates": base_count_total,
        "sells_pass": sells,
    }


def write_markdown(report: Dict[str, Any], out_path: str = "auditoria_sesgo_operativo.md"):
    md: List[str] = []
    md.append("# Auditoría de sesgo operativo — 15m\n")
    # Tabla por símbolo
    for sym, res in report.items():
        if res.get("empty"):
            md.append(f"## {sym}\n\nSin datos o indicadores.\n")
            continue
        md.append(f"## {sym}\n")
        fc = res["filter_counters"]
        # Agregado: promedios relativos de bloqueo por filtro
        agg = {"base": 0, "pass": 0, "blocked_RSI": 0, "blocked_ADX": 0, "blocked_ATR": 0, "blocked_BBW": 0, "blocked_VOTES": 0}
        for k, v in fc.items():
            for kk in agg.keys():
                agg[kk] += int(v.get(kk, 0))
        combos = max(len(fc), 1)
        base = max(agg["base"], 1)
        md.append("### Tasa de bloqueo por filtro (agregado de combos RSI_BUY≤40, ADX≥20)\n")
        md.append("| Filtro | Bloqueos | % sobre base |")
        md.append("|---|---:|---:|")
        for name in ["blocked_ADX", "blocked_ATR", "blocked_BBW", "blocked_VOTES"]:
            md.append(f"| {name.replace('blocked_','')} | {agg[name]} | {100.0*agg[name]/base:.1f}% |")
        md.append("")
        # Regímenes más afectados
        rb = res["regime_block"]
        impact: Dict[str, int] = {}
        for combo, blocks in rb.items():
            for regime, cnts in blocks.items():
                impact[regime] = impact.get(regime, 0) + int(cnts.get("blocked_ADX", 0) + cnts.get("blocked_ATR", 0) + cnts.get("blocked_BBW", 0) + cnts.get("blocked_VOTES", 0))
        if impact:
            md.append("### Regímenes más afectados (bloqueos)\n")
            md.append("| Régimen | Bloqueos |")
            md.append("|---|---:|")
            for r, val in sorted(impact.items(), key=lambda x: x[1], reverse=True)[:5]:
                md.append(f"| {r} | {val} |")
            md.append("")
        # Comparativa volumen compras vs ventas
        md.append("### Volumen de señales que pasan\n")
        md.append("| Tipo | Count |")
        md.append("|---|---:|")
        md.append(f"| Compras | {res['buys_pass']} |")
        md.append(f"| Ventas | {res['sells_pass']} |\n")

        # Recomendaciones
        md.append("### Recomendaciones\n")
        recs: List[str] = []
        # Heurísticas: si un filtro explica ≥80% de bloqueos sobre base
        for name in ["blocked_ADX", "blocked_ATR", "blocked_BBW", "blocked_VOTES"]:
            pct = (100.0 * agg[name] / base) if base > 0 else 0.0
            if pct >= 80.0:
                if name == "blocked_ADX":
                    recs.append("Reducir ADX_LIMIT 2–5 pts en regímenes neutral/range; mantener ≥25 en trend.")
                elif name == "blocked_ATR":
                    recs.append("Bajar MIN_ATR_pct a 0.20 en low_vol/neutral; sostener 0.30 en trend/high_vol.")
                elif name == "blocked_BBW":
                    recs.append("Bajar MIN_BBW_pct a 0.10 fuera de trend; mantener 0.15 en trend.")
                elif name == "blocked_VOTES":
                    recs.append("Reducir MIN_VOTES en 1 punto o ponderar votos por régimen (MACD opcional).")
        if not recs:
            recs.append("Mantener filtros; modular por régimen (horas pico de señales: extender cobertura en esas franjas).")
        for r in recs:
            md.append(f"- {r}")
        md.append("")

    # Guardar
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return out_path


def load_master_15m(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df


def main():
    parser = argparse.ArgumentParser(description="Auditar sesgo operativo sin ejecutar trades")
    parser.add_argument("--master", default=os.path.join("data", "historiales", "historial_trading_maestro_15m.csv"))
    parser.add_argument("--symbols", nargs="*", default=["BTCUSDT", "ETHUSDT", "BNBUSDT", "WLDUSDT"])
    parser.add_argument("--out", default="auditoria_sesgo_operativo.md")
    args = parser.parse_args()

    dfm = load_master_15m(args.master)
    if dfm.empty or "symbol" not in dfm.columns:
        raise RuntimeError("No se pudo cargar el maestro 15m con columna 'symbol'.")

    rsi_buys = [30, 35, 40]
    adx_limits = [20, 23, 25]
    min_votes_list = [2, 3, 4]

    report: Dict[str, Any] = {}
    for sym in args.symbols:
        part = dfm.loc[dfm["symbol"] == sym].copy()
        if part.empty:
            report[sym] = {"symbol": sym, "empty": True}
            continue
        res = audit_symbol(part, sym, rsi_buys, adx_limits, min_votes_list)
        report[sym] = res

    out_path = write_markdown(report, args.out)
    print(f"Generado {out_path}")


if __name__ == "__main__":
    main()

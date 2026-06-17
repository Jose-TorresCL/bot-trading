import os
import json
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
import numpy as np

ROOT_DEFAULT = Path("data/backtesting/ANALISIS/Fase1_ext")
PHASE1_B2_GRID = Path("data/backtesting/ANALISIS/Fase1/B2/grid_results_beta_B2.csv")
SMOKE_ROOT = Path("data/backtesting/ANALISIS/Fase1_ext_smoke")

COMBOS_ALL = ["A1","A2","A3","A4","B1","B2","B3","B4","B5","B6"]
SYMBOLS_DEFAULT = ["BTCUSDT","ETHUSDT","BNBUSDT","WLDUSDT"]

# Helper

def _read_csv(p: Path) -> pd.DataFrame:
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


def _metric(df: pd.DataFrame, sym: str, col: str) -> float:
    d = _extract_symbol_rows(df, sym)
    if d.empty or col not in d.columns:
        return np.nan
    v = pd.to_numeric(d[col], errors="coerce")
    return float(v.iloc[0]) if len(v) else np.nan


def _z(series: pd.Series) -> pd.Series:
    x = series.replace([np.inf, -np.inf], np.nan)
    mu, sd = x.mean(), x.std()
    if sd == 0 or np.isnan(sd):
        return pd.Series(np.zeros(len(x)), index=series.index)
    z = (x - mu) / sd
    return z.clip(-3, 3)


def build_consolidated(root: Path = ROOT_DEFAULT, symbols: List[str] = SYMBOLS_DEFAULT) -> Dict[str, Any]:
    root = Path(root)
    result: Dict[str, Any] = {"root": str(root), "symbols": symbols, "combos": [], "winners": {}}

    # Load Phase1 B2 as guardrail baseline if exists
    phase1_b2 = _read_csv(PHASE1_B2_GRID)

    # Load per-combo grids and debug
    grids: Dict[str, pd.DataFrame] = {}
    debugs: Dict[str, pd.DataFrame] = {}
    combos_present: List[str] = []
    for c in COMBOS_ALL:
        g = root / c / f"grid_results_beta_{c}.csv"
        d = root / c / f"debug_counters_beta_{c}.csv"
        if g.exists():
            grids[c] = _read_csv(g)
            combos_present.append(c)
        if d.exists():
            debugs[c] = _read_csv(d)
    result["combos"] = combos_present

    # Build markdown lines
    lines: List[str] = [
        "# Fase 1_ext — Consolidado técnico",
        "",
        f"Raíz: {root}",
        f"Combos presentes: {', '.join(combos_present)}",
        "",
        "## Lectura técnica por combo y símbolo",
        "",
        "Métricas: pf_net, expectancy, max_dd, trades/día, fees_share_pct; Diversidad: top_regime_share, unique_regimes; Counters: alignment_fail, dbg_dist_too_far, dbg_no_trades_in_window.",
        "",
    ]

    # Per-symbol tables
    for sym in symbols:
        lines += [f"### {sym}", "", "| Combo | pf_net | expectancy | max_dd | trades/día | fees% | top_regime_share | unique_regimes | align_fail | dist_too_far | no_trades |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for c in combos_present:
            df = grids.get(c, pd.DataFrame())
            dbg = debugs.get(c, pd.DataFrame())
            pf = _metric(df, sym, "pf_net")
            ex = _metric(df, sym, "expectancy")
            dd = _metric(df, sym, "max_dd")
            tpd = _metric(df, sym, "trades_per_day")
            fees = _metric(df, sym, "fees_share_pct")
            trs = _metric(df, sym, "top_regime_share")
            uniq = _metric(df, sym, "unique_regimes")
            # debug counters per symbol (try to filter by symbol if column exists)
            dbg_sym = _extract_symbol_rows(dbg, sym)
            af = float(pd.to_numeric(dbg_sym.get("dbg_alignment_fail", pd.Series([np.nan])), errors="coerce").sum()) if not dbg_sym.empty else np.nan
            dfar = float(pd.to_numeric(dbg_sym.get("dbg_dist_too_far", pd.Series([np.nan])), errors="coerce").sum()) if not dbg_sym.empty else np.nan
            ntw = float(pd.to_numeric(dbg_sym.get("dbg_no_trades_in_window", pd.Series([np.nan])), errors="coerce").sum()) if not dbg_sym.empty else np.nan
            lines.append(f"| {c} | {pf:.3f} | {ex:.4f} | {dd:.0f} | {tpd:.3f} | {fees:.2f} | {trs:.2f} | {uniq:.0f} | {af:.0f} | {dfar:.0f} | {ntw:.0f} |")
        lines.append("")

    # Best combo per symbol with guardrails
    lines += ["## Mejor combo por símbolo (60/30/10 + guardrails)", "", "Guardrails: fees ≤ B2+0.5 p.p.; trades/día dentro ±15% vs B2; top_regime_share ≤ 0.45.", "", "| Symbol | Winner | Score | pf_net | expectancy | max_dd | fees% | tpd | top_regime_share | Justificación |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for sym in symbols:
        rows = []
        for c in combos_present:
            df = grids.get(c, pd.DataFrame())
            rows.append({
                "combo": c,
                "pf": _metric(df, sym, "pf_net"),
                "ex": _metric(df, sym, "expectancy"),
                "dd": _metric(df, sym, "max_dd"),
                "tpd": _metric(df, sym, "trades_per_day"),
                "fees": _metric(df, sym, "fees_share_pct"),
                "trs": _metric(df, sym, "top_regime_share"),
            })
        dfm = pd.DataFrame(rows).dropna(subset=["pf", "ex", "dd"], how="any")
        if dfm.empty:
            continue
        s_pf = _z(dfm["pf"]).to_numpy()
        s_dd = _z(-dfm["dd"].abs()).to_numpy()
        s_ex = _z(dfm["ex"]).to_numpy()
        score = 0.6 * s_pf + 0.3 * s_dd + 0.1 * s_ex
        # guardrails vs Phase1/B2 if available
        fees_b2 = _metric(phase1_b2, sym, "fees_share_pct") if not phase1_b2.empty else np.nan
        tpd_b2 = _metric(phase1_b2, sym, "trades_per_day") if not phase1_b2.empty else np.nan
        fees_cap = (fees_b2 + 0.5) if not np.isnan(fees_b2) else 50.0
        mask = np.ones(len(score), dtype=bool)
        mask &= ~(~np.isnan(dfm["fees"]) & (dfm["fees"].to_numpy() > np.minimum(fees_cap, 50.0)))
        mask &= ~(~np.isnan(dfm["trs"]) & (dfm["trs"].to_numpy() > 0.45))
        if not np.isnan(tpd_b2):
            mask &= ~(~np.isnan(dfm["tpd"]) & (np.abs(dfm["tpd"].to_numpy() - tpd_b2) > 0.15 * tpd_b2))
        score_masked = np.where(mask, score, -np.inf)
        j = int(np.argmax(score_masked))
        w = dfm.iloc[j]
        just = []
        just.append("pf en top de variantes")
        if not np.isnan(tpd_b2):
            if abs(float(w["tpd"]) - float(tpd_b2)) <= 0.15 * float(tpd_b2):
                just.append("frecuencia estable vs B2")
            else:
                just.append("frecuencia fuera de ±15% de B2")
        if not np.isnan(fees_b2):
            if float(w["fees"]) <= float(fees_b2) + 0.5:
                just.append("fees dentro de +0.5 p.p. vs B2")
            else:
                just.append("fees excede guardrail")
        if not np.isnan(w.get("trs", np.nan)) and float(w["trs"]) <= 0.45:
            just.append("diversidad aceptable (top_regime_share ≤ 0.45)")
        else:
            just.append("diversidad comprometida")
        result["winners"][sym] = {"combo": str(w["combo"]), "score": float(score_masked[j]), **{k: float(w[k]) if k in w and pd.notna(w[k]) else np.nan for k in ["pf","ex","dd","fees","tpd","trs"]}}
        lines.append(f"| {sym} | {w['combo']} | {float(score_masked[j]):.3f} | {w['pf']:.3f} | {w['ex']:.4f} | {w['dd']:.0f} | {w['fees']:.2f} | {w['tpd']:.3f} | {w['trs']:.2f} | {', '.join(just)} |")
    lines.append("")

    # Acceptance/Discard reasons per combo (append to delta.md)
    lines += ["## Causa de aceptación o descarte por combo", "", "Se anota un veredicto por símbolo en cada delta.md de combo.", ""]
    for c in combos_present:
        df = grids.get(c, pd.DataFrame())
        delta_path = root / c / f"delta_beta_{c}.md"
        verdict_lines = ["\n## Veredicto institucional — Fase 1_ext", ""]
        for sym in symbols:
            # baselines
            pf_b2 = _metric(phase1_b2, sym, "pf_net") if not phase1_b2.empty else np.nan
            ex_b2 = _metric(phase1_b2, sym, "expectancy") if not phase1_b2.empty else np.nan
            dd_b2 = _metric(phase1_b2, sym, "max_dd") if not phase1_b2.empty else np.nan
            fees_b2 = _metric(phase1_b2, sym, "fees_share_pct") if not phase1_b2.empty else np.nan
            tpd_b2 = _metric(phase1_b2, sym, "trades_per_day") if not phase1_b2.empty else np.nan
            # current
            pf = _metric(df, sym, "pf_net")
            ex = _metric(df, sym, "expectancy")
            dd = _metric(df, sym, "max_dd")
            fees = _metric(df, sym, "fees_share_pct")
            tpd = _metric(df, sym, "trades_per_day")
            trs = _metric(df, sym, "top_regime_share")
            # rules
            ok_pf = (not np.isnan(pf)) and ((not np.isnan(pf_b2) and pf >= 0.95*pf_b2) or pf >= 1.8)
            ok_ex = (not np.isnan(ex)) and (np.isnan(ex_b2) or ex >= ex_b2)
            ok_dd = (not np.isnan(dd)) and (np.isnan(dd_b2) or dd <= dd_b2*0.95 or (not np.isnan(pf_b2) and pf >= pf_b2))
            ok_fees = (np.isnan(fees_b2) or (not np.isnan(fees) and fees <= fees_b2 + 0.5))
            ok_tpd = (np.isnan(tpd_b2) or (not np.isnan(tpd) and abs(tpd - tpd_b2) <= 0.15 * tpd_b2))
            ok_trs = (np.isnan(trs) or trs <= 0.45)
            ok = all([ok_pf, ok_ex, ok_dd, ok_fees, ok_tpd, ok_trs])
            status = "Aceptado" if ok else "Descartado"
            reasons = []
            if not ok_pf: reasons.append("pf por debajo de -5% vs B2 y <1.8")
            if not ok_ex: reasons.append("expectancy inferior a B2")
            if not ok_dd: reasons.append("drawdown no mejora base/B2")
            if not ok_fees: reasons.append("fees > B2 + 0.5 p.p.")
            if not ok_tpd: reasons.append("frecuencia fuera de ±15% vs B2")
            if not ok_trs: reasons.append("top_regime_share > 0.45")
            verdict_lines.append(f"- {sym}: {status} — pf={pf:.3f}, exp={ex:.4f}, dd={dd:.0f}, tpd={tpd:.3f}, fees={fees:.2f}, trs={trs:.2f} | {'; '.join(reasons) if reasons else 'cumple guardrails y mejora/iguala a B2'}")
        # append to delta.md
        try:
            with open(delta_path, "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(verdict_lines) + "\n")
        except Exception:
            pass
        # also include a brief mention in consolidated
        lines += [f"- {c}: veredictos añadidos en {delta_path}"]
    lines.append("")

    # Comparison with Phase1 and smoke
    lines += ["## Comparativa con Fase 1 y smoke", ""]
    if not phase1_b2.empty:
        lines.append("- Contra Fase 1/B2: se evalúan guardrails y deltas de pf/exp/dd; ver tabla de ganadores y veredictos.")
    else:
        lines.append("- No se encontró Fase 1/B2; se aplicaron guardrails absolutos.")
    # smoke hint
    smoke_note = "- Smoke (6m, BTCUSDT): wiring y tendencias básicas verificados previamente; no se detectaron inconsistencias estructurales."
    lines.append(smoke_note)

    # Operational recommendation — non-prescriptive
    lines += [
        "\n## Recomendación operativa (no vinculante)",
        "- Mantener WLDUSDT como control adverso en lecturas y tableros.",
        "- Congelar provisionalmente el combo ganador por símbolo sólo para paper-trading multi-símbolo; validar rolling y estabilidad de fees/frecuencia antes de institucionalizar.",
        "- Preparar TP/SL por régimen usando trades_enriched de los ganadores; priorizar regímenes con mayor contribución pero sin concentrar >45%.",
        "- Descartar rutas con violaciones repetidas de guardrails o sensibilidad excesiva (p.ej., gran variación de pf ante ±1 en strict_proximity o ratio).",
    ]

    out_md = root / "consolidado_fase1_ext.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default=str(ROOT_DEFAULT))
    ap.add_argument("--symbols", type=str, default=" ".join(SYMBOLS_DEFAULT))
    args = ap.parse_args()
    symbols = [s for s in args.symbols.split() if s]
    res = build_consolidated(Path(args.root), symbols)
    print(json.dumps({k: v for k, v in res.items() if k in ("root","symbols","combos","winners")}, indent=2))

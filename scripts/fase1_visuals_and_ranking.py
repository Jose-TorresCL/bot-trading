import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_variant_df(base_dir: Path, variant: str) -> pd.DataFrame:
    p = base_dir / "data" / "backtesting" / "ANALISIS" / "Fase1" / variant / f"grid_results_beta_{variant}.csv"
    df = pd.read_csv(p)
    df["variant"] = variant
    return df


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def plot_grouped_bars(df_all: pd.DataFrame, metric: str, out_dir: Path, title: str, transform=None, fname: str | None = None) -> None:
    variants = ["B1", "B2", "B3", "B4"]
    d = df_all.copy()
    if transform is not None:
        d[metric + "__plot"] = d[metric].apply(transform)
        col = metric + "__plot"
    else:
        col = metric
    piv = d.pivot(index="symbol", columns="variant", values=col).reindex(columns=variants)
    ax = piv.plot(kind="bar", figsize=(9, 5))
    ax.set_title(title)
    ax.set_xlabel("Símbolo")
    ax.set_ylabel(metric)
    ax.legend(title="Variante")
    plt.tight_layout()
    out_path = out_dir / ((fname or metric) + ".png")
    plt.savefig(out_path, dpi=140)
    plt.close()


def normalized_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = series.astype(float)
    vmin = s.min()
    vmax = s.max()
    if np.isclose(vmax, vmin):
        return pd.Series(1.0, index=s.index)
    norm = (s - vmin) / (vmax - vmin)
    return norm if higher_is_better else (1.0 - norm)


def main():
    base_dir = Path(__file__).resolve().parents[1]
    fase1_dir = base_dir / "data" / "backtesting" / "ANALISIS" / "Fase1"
    visuals_dir = fase1_dir / "visuals"
    ensure_dir(visuals_dir)

    # Load variants
    dfs = []
    for v in ("B1", "B2", "B3", "B4"):
        dfs.append(load_variant_df(base_dir, v))
    df_all = pd.concat(dfs, ignore_index=True)

    # Ensure required cols exist
    required = [
        "symbol",
        "pf_net",
        "expectancy",
        "max_dd",
        "trades_per_day",
        "fees_share_pct",
        "top_regime_share",
        "variant",
    ]
    missing = [c for c in required if c not in df_all.columns]
    if missing:
        raise RuntimeError(f"Faltan columnas requeridas en grids: {missing}")

    # Plot metrics
    plot_grouped_bars(df_all, "pf_net", visuals_dir, "Fase 1 — pf_net por símbolo (B1–B4)")
    plot_grouped_bars(df_all, "expectancy", visuals_dir, "Fase 1 — expectancy por símbolo (B1–B4)")
    # For max_dd, plot absolute drawdown magnitude (menor es mejor)
    plot_grouped_bars(df_all, "max_dd", visuals_dir, "Fase 1 — |max_dd| por símbolo (B1–B4)", transform=lambda x: abs(float(x)), fname="max_dd_abs")
    plot_grouped_bars(df_all, "trades_per_day", visuals_dir, "Fase 1 — trades/día por símbolo (B1–B4)", fname="trades_per_day")
    plot_grouped_bars(df_all, "fees_share_pct", visuals_dir, "Fase 1 — fees_share_pct por símbolo (B1–B4)")

    # Baseline (opcional)
    baseline_path = base_dir / "grid_results_beta_B.csv"
    df_base = None
    if baseline_path.exists():
        try:
            df_base = pd.read_csv(baseline_path)
        except Exception:
            df_base = None

    # Ranking compuesto por símbolo
    rows = []
    for sym, g in df_all.groupby("symbol"):
        # normalizar por símbolo
        pf_score = normalized_score(g.set_index("variant")["pf_net"], higher_is_better=True)
        exp_score = normalized_score(g.set_index("variant")["expectancy"], higher_is_better=True)
        dd_abs = g.set_index("variant")["max_dd"].abs()
        dd_score = normalized_score(dd_abs, higher_is_better=False)
        composite = 0.6 * pf_score + 0.3 * exp_score + 0.1 * dd_score
        best_variant = composite.idxmax()
        r = g.set_index("variant").loc[best_variant]

        # deltas vs baseline
        delta_pf = np.nan
        delta_exp = np.nan
        delta_abs_dd = np.nan
        fees_note = ""
        if df_base is not None and not df_base.empty:
            rb = df_base.loc[df_base["symbol"] == sym]
            if not rb.empty:
                rb = rb.iloc[0]
                delta_pf = float(r["pf_net"]) - float(rb["pf_net"])
                delta_exp = float(r["expectancy"]) - float(rb["expectancy"])
                delta_abs_dd = abs(float(rb["max_dd"])) - abs(float(r["max_dd"]))
                fees_diff = float(r["fees_share_pct"]) - float(rb.get("fees_share_pct", np.nan))
                if np.isnan(fees_diff):
                    fees_note = "fees n/a"
                else:
                    if abs(fees_diff) <= 0.5:
                        fees_note = "fees estables"
                    elif fees_diff < -0.5:
                        fees_note = "fees ↓"
                    else:
                        fees_note = "fees ↑"

        justification = (
            f"pf_net {float(r['pf_net']):.3f}, exp {float(r['expectancy']):.3f}, |dd| {abs(float(r['max_dd'])):.3f}, "
            f"tpd {float(r['trades_per_day']):.3f}, fees {float(r['fees_share_pct']):.2f}, top_share {float(r['top_regime_share']):.3f}"
        )
        if not np.isnan(delta_pf):
            justification += (
                f"; Δpf_vs_B {delta_pf:+.3f}, Δexp_vs_B {delta_exp:+.3f}, Δ|dd|_vs_B {delta_abs_dd:+.3f}"
            )
            if fees_note:
                justification += f", {fees_note}"

        rows.append({
            "symbol": sym,
            "winner_variant": best_variant,
            "score": float(composite.loc[best_variant]),
            "pf_net": float(r["pf_net"]),
            "expectancy": float(r["expectancy"]),
            "max_dd": float(r["max_dd"]),
            "trades_per_day": float(r["trades_per_day"]),
            "fees_share_pct": float(r["fees_share_pct"]),
            "top_regime_share": float(r["top_regime_share"]),
            "delta_pf_vs_B": delta_pf,
            "delta_exp_vs_B": delta_exp,
            "delta_abs_dd_vs_B": delta_abs_dd,
            "justification": justification,
        })

    out_rank = fase1_dir / "ranking_variantes_fase1.csv"
    pd.DataFrame(rows).to_csv(out_rank, index=False)

    # Also save combined metrics for traceability
    (fase1_dir / "combined_metrics_fase1.csv").write_text(df_all.to_csv(index=False), encoding="utf-8")

    print(f"Visuals guardados en: {visuals_dir}")
    print(f"Ranking guardado en: {out_rank}")


if __name__ == "__main__":
    main()

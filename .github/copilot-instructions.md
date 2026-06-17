# Copilot Instructions for AI Agents

## Project Overview
This is a Python-based algorithmic trading bot for analyzing data, backtesting strategies, and automated trading. The codebase is organized for research, experimentation, and robust evaluation of trading ideas.

## Key Directories & Files
- `src/` — Core bot logic, strategies, and main entry points (e.g., `main.py`, `core/`, etc.)
- `scripts/` — Utility scripts for audits, data processing, and batch jobs (e.g., `auditar_sesgo_operativo.py`, `ab_sesgo_fix.py`)
- `data/` — Historical and test data (CSV, config, etc.)
- `notebooks/` — Jupyter notebooks for exploratory analysis and prototyping
- `resultados/`, `bd/` — Simulation results and database files
- `README.md` — High-level usage, workflows, and institutional notes
- `auditoria_tecnica_y_organizativa.md` — Institutional/technical audit and recommended workflows

## Developer Workflows
- **Environment setup:**
  - Use `python -m venv .venv` and `pip install -r requirements.txt`.
- **Run main bot:**
  - `python src/main.py` (see README for details)
- **Backtesting & experiments:**
  - Use scripts in `scripts/` (e.g., `ab_sesgo_fix.py`) with parameters for batch backtests. Example:
    ```
    python scripts/ab_sesgo_fix.py --master data/historiales/historial_trading_maestro_15m.csv --symbols BTCUSDT ETHUSDT --months 6 ...
    ```
  - Review generated CSV/MD files in project root for results.
- **Auditing:**
  - Run `scripts/auditar_sesgo_operativo.py` to generate operational bias audits.
- **Notebooks:**
  - Use for data exploration and result analysis. Notebooks expect pre-generated data from scripts.

## Project-Specific Conventions
- **Batch scripts** use PowerShell for multi-step experiments (see VS Code tasks for examples).
- **Results** are written as CSV/MD in the project root, named by experiment (e.g., `grid_results_beta_A.csv`).
- **Parameterization** is preferred: pass all experiment settings as CLI arguments, not hardcoded.
- **Institutional workflow**: See `auditoria_tecnica_y_organizativa.md` for the recommended data→backtest→portfolio→verdict flow.
- **No direct trading in audit scripts**: Scripts like `auditar_sesgo_operativo.py` only analyze, do not execute trades.

## Integration & Patterns
- **Data flow**: Scripts and bot read from `data/`, write results to root or `resultados/`.
- **Cross-component communication**: Prefer file-based (CSV/MD) for experiment results; avoid tight coupling.
- **Debugging**: Use generated debug CSVs (e.g., `debug_counters_beta_A.csv`) for troubleshooting.

## Examples
- To run a batch of A/B experiments:
  ```
  # See VS Code task: Run Beta A-D A/B experiments
  # Or run manually:
  python scripts/ab_sesgo_fix.py --master data/historiales/historial_trading_maestro_15m.csv --symbols BTCUSDT ETHUSDT --months 6 ...
  ```
- To audit operational bias:
  ```
  python scripts/auditar_sesgo_operativo.py
  ```

## References
- See `README.md` and `auditoria_tecnica_y_organizativa.md` for more details on workflows and architecture.
- Review VS Code tasks for canonical experiment commands.

"""
descarga_historicos.py
----------------------
Herramienta robusta para descargar historiales paginados desde Binance y guardar CSVs.

Características:
- usa `connect_to_binance` y `get_historical_data` del pipeline
- soporta paginación por start/end (get_klines) o por llamadas al helper
- retries + exponential backoff en errores/429
- backups timestamped antes de sobrescribir archivos locales
- genera `download_summary_{suffix}.json` con filas/primer/último/timedelta por símbolo

Este módulo puede usarse desde CLI o como función programática.
"""
from __future__ import annotations
from pathlib import Path
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd

from src.pipeline.conexion_api import connect_to_binance, get_historical_data

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

OUT_DIR = Path("data/historicos")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _backup_if_exists(path: Path) -> None:
    if not path.exists():
        return
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = path.with_suffix(f".bak.{ts}.csv")
        path.rename(bak)
        LOG.info("Backup creado: %s", bak)
    except Exception as e:
        LOG.warning("No se pudo crear backup para %s: %s", path, e)


def _save_df(path: Path, df: pd.DataFrame) -> None:
    # ensure timestamp column is timezone-aware UTC
    if "timestamp" in df.columns:
        try:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        except Exception:
            pass
    df.to_csv(path, index=False)
    LOG.info("Guardado %s filas en %s", len(df), path)


def download_symbol(symbol: str,
                    interval: str = "1m",
                    days: Optional[int] = None,
                    years: int = 0,
                    limit_per_call: int = 1000,
                    sleep_s: float = 0.5,
                    max_retries: int = 3,
                    backoff_factor: float = 1.5) -> Optional[Dict[str, Any]]:
    """Descarga histórico para un símbolo y guarda `data/historicos/historial_{symbol}.csv`.

    Devuelve un resumen con filas, first, last.
    """
    end_dt = datetime.now(timezone.utc)
    if days is not None:
        start_dt = end_dt - timedelta(days=days)
    elif years and years > 0:
        start_dt = end_dt - timedelta(days=365 * years)
    else:
        # default: 1 year
        start_dt = end_dt - timedelta(days=365)

    client = connect_to_binance()
    all_rows: List[Dict[str, Any]] = []

    # Preferir get_historical_klines si existe
    if client is not None and hasattr(client, "get_historical_klines"):
        LOG.info("Usando get_historical_klines para %s", symbol)
        curr_start = start_dt
        while curr_start < end_dt:
            start_str = curr_start.strftime("%d %b %Y %H:%M:%S")
            attempt = 0
            while attempt < max_retries:
                try:
                    klines = client.get_historical_klines(symbol, interval, start_str, limit=limit_per_call)
                    break
                except Exception as e:
                    attempt += 1
                    wait = backoff_factor ** attempt
                    LOG.warning("Error get_historical_klines (%s) intento %d: %s — esperando %.1fs", symbol, attempt, e, wait)
                    time.sleep(wait)
            else:
                LOG.warning("No se pudo obtener page para %s desde %s — abortando paginación.", symbol, curr_start)
                break

            if not klines:
                break

            for k in klines:
                try:
                    ts_ms = int(k[0])
                    ts_dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                    all_rows.append({
                        "timestamp": ts_dt,
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                        "symbol": symbol
                    })
                except Exception:
                    continue

            last_ts_ms = int(klines[-1][0])
            curr_start = datetime.fromtimestamp((last_ts_ms + 1) / 1000.0, tz=timezone.utc)
            time.sleep(sleep_s)
    else:
        # fallback: usar helper get_historical_data con paginación por endTime
        LOG.info("Usando helper get_historical_data para %s", symbol)
        page_end = int(end_dt.timestamp() * 1000)
        calls = 0
        while True:
            calls += 1
            try:
                df_page = get_historical_data(client, symbol=symbol, interval=interval, limit=limit_per_call, endTime=page_end)
            except TypeError:
                df_page = get_historical_data(client, symbol=symbol, interval=interval, limit=limit_per_call)

            if df_page is None or (isinstance(df_page, pd.DataFrame) and df_page.empty):
                LOG.info("No hay más páginas para %s (calls=%d).", symbol, calls)
                break

            df_page = pd.DataFrame(df_page)
            # normalize
            if "timestamp" not in df_page.columns:
                for c in ("open_time", "time", "date"):
                    if c in df_page.columns:
                        df_page = df_page.rename(columns={c: "timestamp"})
                        break
            df_page["timestamp"] = pd.to_datetime(df_page["timestamp"], utc=True, errors="coerce")
            df_page = df_page.dropna(subset=["timestamp"])
            for _, r in df_page.iterrows():
                try:
                    all_rows.append({
                        "timestamp": r["timestamp"],
                        "open": float(r.get("open", 0)),
                        "high": float(r.get("high", 0)),
                        "low": float(r.get("low", 0)),
                        "close": float(r.get("close", 0)),
                        "volume": float(r.get("volume", 0)),
                        "symbol": symbol
                    })
                except Exception:
                    continue

            # prepare next page end (previous earliest timestamp)
            earliest = min([r["timestamp"] for r in all_rows]) if all_rows else None
            if not earliest or earliest <= start_dt:
                break
            page_end = int((earliest.timestamp() * 1000) - 1)
            time.sleep(sleep_s)

    if not all_rows:
        LOG.warning("No se obtuvieron velas para %s", symbol)
        return None

    df = pd.DataFrame(all_rows)
    # normalize and dedupe
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", "close"]).drop_duplicates(subset=["timestamp", "symbol"]).sort_values("timestamp").reset_index(drop=True)

    out_path = OUT_DIR / f"historial_{symbol}.csv"
    _backup_if_exists(out_path)
    _save_df(out_path, df)

    summary = {
        "symbol": symbol,
        "rows": len(df),
        "first": str(df["timestamp"].min()),
        "last": str(df["timestamp"].max()),
        "span_days": (df["timestamp"].max() - df["timestamp"].min()).days
    }
    return summary


def main(symbols: Optional[List[str]] = None, interval: str = "1m", days: Optional[int] = None, years: int = 0, limit: int = 1000):
    if symbols is None:
        # detect local symbols pattern
        import glob, re
        files = sorted(glob.glob(str(OUT_DIR / "historial_*.csv")))
        symbols = [Path(f).stem.replace("historial_", "").upper() for f in files if re.match(r"^historial_[A-Z0-9]+USDT\.csv$", Path(f).name)]

    LOG.info("Descargando símbolos: %s", symbols)
    results = []
    for s in symbols:
        try:
            r = download_symbol(s, interval=interval, days=days, years=years, limit_per_call=limit)
            if r:
                results.append(r)
        except Exception as e:
            LOG.exception("Fallo descarga %s: %s", s, e)

    # write summary
    if results:
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_summary = OUT_DIR / f"download_summary_{suffix}.json"
        try:
            with out_summary.open("w", encoding="utf-8") as fh:
                json.dump(results, fh, ensure_ascii=False, indent=2)
            LOG.info("Summary guardado: %s", out_summary)
        except Exception:
            LOG.warning("No se pudo escribir summary JSON")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Descarga historiales paginados (robusto)")
    parser.add_argument("--symbols", "-s", type=str, default=None, help="Símbolos separados por coma")
    parser.add_argument("--interval", "-i", type=str, default="1m")
    parser.add_argument("--days", "-d", type=int, default=None)
    parser.add_argument("--years", "-y", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    main(symbols=syms, interval=args.interval, days=args.days, years=args.years, limit=args.limit)

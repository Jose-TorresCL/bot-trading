"""
backfill_historicos.py
----------------------
Backfill simple de históricos por símbolo usando la función `get_historical_data` del pipeline.

Comportamiento:
- Para cada símbolo dado (o todos detectados en src/data/historicos/historial_*.csv),
  solicita hasta `limit` filas desde Binance (o genera simulados si no hay client).
- Normaliza timestamps, concatena con el CSV local `data/historicos/historial_{SYMBOL}.csv`, deduplica por timestamp
  y guarda de nuevo.

Este script no elimina archivos ni sobreescribe sin verificar. Ideal para aumentar la cantidad de datos locales.
"""
from pathlib import Path
import pandas as pd
import logging
from src.pipeline.conexion_api import connect_to_binance, get_historical_data
from src.pipeline.carga_datos import _detect_timestamp_col

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

HIST_DIR = Path("data/historicos")


def list_local_symbols(hist_dir: Path = HIST_DIR) -> list:
    import re
    files = sorted(hist_dir.glob("historial_*.csv"))
    syms = []
    for p in files:
        name = p.stem.replace("historial_", "").upper()
        # aceptar solo símbolos tipo 'XXXXUSDT' o 'BTCUSDT' (uppercase alfanum)
        if re.match(r'^[A-Z0-9]+USDT$', name):
            syms.append(name)
        else:
            LOG.info("Ignorando fichero no símbolo: %s", p.name)
    return syms


def read_local_hist(symbol: str, hist_dir: Path = HIST_DIR) -> pd.DataFrame:
    p = hist_dir / f"historial_{symbol}.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p)
        # try to detect ts col and normalize
        if "timestamp" not in df.columns:
            col = _detect_timestamp_col(df)
            if col and col in df.columns:
                df = df.rename(columns={col: "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
        return df.reset_index(drop=True)
    except Exception as e:
        LOG.warning("No se pudo leer %s: %s", p, e)
        return pd.DataFrame()


def append_and_dedupe(symbol: str, new_df: pd.DataFrame, hist_dir: Path = HIST_DIR) -> dict:
    p = hist_dir / f"historial_{symbol}.csv"
    old = read_local_hist(symbol, hist_dir)
    combined = pd.concat([old, new_df], ignore_index=True)
    # normalize timestamp
    combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True, errors="coerce")
    combined = combined.dropna(subset=["timestamp"]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    # backup original before overwriting
    try:
        if p.exists():
            # create timestamped backup if basic .bak exists
            import datetime
            backup = hist_dir / f"historial_{symbol}.bak.csv"
            if backup.exists():
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = hist_dir / f"historial_{symbol}.bak.{ts}.csv"
            p.rename(backup)
            LOG.info("Backup creado: %s", backup)
    except Exception as e:
        LOG.warning("No se pudo crear backup para %s: %s", p, e)

    # Si el merge redujo el número de filas (posible pérdida), no sobrescribir el original: escribir como .merged.csv
    old_rows = len(old)
    new_rows = len(combined)
    if old_rows > 0 and new_rows < old_rows:
        merged_path = hist_dir / f"historial_{symbol}.merged.csv"
        combined.to_csv(merged_path, index=False)
        LOG.warning("Merge redujo filas para %s: old=%d new=%d. Escrito a %s (no se sobrescribió el original).", symbol, old_rows, new_rows, merged_path)
        return {"symbol": symbol, "old_rows": old_rows, "added_rows": max(0, new_rows - old_rows), "new_total": new_rows}

    combined.to_csv(p, index=False)
    return {"symbol": symbol, "old_rows": old_rows, "added_rows": max(0, new_rows - old_rows), "new_total": new_rows}


def fetch_and_append(symbol: str, client=None, interval: str = "1m", limit: int = 1500):
    LOG.info("Fetch para %s (limit=%d)", symbol, limit)
    # direct fetch
    df_api = get_historical_data(client, symbol=symbol, interval=interval, limit=limit)
    if df_api is None or df_api.empty:
        LOG.warning("No se obtuvieron datos para %s", symbol)
        return {"symbol": symbol, "status": "no_data"}
    # ensure timestamp col exists
    if "timestamp" not in df_api.columns:
        # try to detect common names
        for c in ("open_time", "time", "date"):
            if c in df_api.columns:
                df_api = df_api.rename(columns={c: "timestamp"})
                break
    try:
        df_api["timestamp"] = pd.to_datetime(df_api["timestamp"], utc=True, errors="coerce")
    except Exception:
        pass
    res = append_and_dedupe(symbol, df_api)
    LOG.info("Backfill %s -> added %d rows (total %d)", symbol, res.get("added_rows", 0), res.get("new_total", 0))
    return {**res, "status": "ok"}


def main(symbols: list | None = None, interval: str = "1m", limit: int = 1500, use_api: bool = True):
    if symbols is None:
        symbols = list_local_symbols()
    LOG.info("Símbolos objetivo: %s", symbols)

    client = None
    if use_api:
        client = connect_to_binance()
        if client is None:
            LOG.warning("No hay credenciales/API; se usarán datos simulados donde proceda.")

    results = []
    # parámetros para backfill iterativo
    min_days = 30
    max_calls = 40  # to avoid infinite loops
    for s in symbols:
        try:
            # carga local inicial
            local = read_local_hist(s)
            start = None
            if not local.empty:
                start = local["timestamp"].min()
                span_days = (pd.Timestamp.now(tz="UTC") - start).days
            else:
                span_days = 0

            calls = 0
            acc_results = None
            while span_days < min_days and calls < max_calls:
                calls += 1
                LOG.info("Backfill iterativo %s: llamada %d (span_days=%d < min_days=%d)", s, calls, span_days, min_days)
                # calcular startTime para solicitar datos anteriores al primer timestamp local
                startTime = None
                if start is not None:
                    # pedir datos anteriores a 'start' (convertir a ms epoch menos 1)
                    startTime = int((start.value // 10**6) - 1)
                try:
                    df_chunk = get_historical_data(client, symbol=s, interval=interval, limit=limit, endTime=startTime)
                except TypeError:
                    # si la versión antigua no acepta endTime, caer al fetch simple
                    df_chunk = get_historical_data(client, symbol=s, interval=interval, limit=limit)

                if df_chunk is None or df_chunk.empty:
                    LOG.warning("No more data from API for %s on call %d; stopping iterative backfill.", s, calls)
                    break

                # append and recompute span
                res = append_and_dedupe(s, df_chunk)
                acc_results = res
                local = read_local_hist(s)
                if not local.empty:
                    start = local["timestamp"].min()
                    span_days = (pd.Timestamp.now(tz="UTC") - start).days
                else:
                    span_days = 0

            # if we didn't enter loop (already had enough days), do one normal fetch to ensure freshness
            if calls == 0:
                r = fetch_and_append(s, client=client, interval=interval, limit=limit)
                results.append(r)
            else:
                results.append(acc_results or {"symbol": s, "status": "no_data"})
        except Exception as e:
            LOG.exception("Fallo en backfill de %s: %s", s, e)
            results.append({"symbol": s, "status": "error", "error": str(e)})

    # summary
    for r in results:
        LOG.info(r)

    return results


if __name__ == "__main__":
    # usos: ejecutar con credenciales configuradas en data/config.env
    main(symbols=None, interval="1m", limit=1500, use_api=True)

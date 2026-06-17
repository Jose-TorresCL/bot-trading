"""
descarga_historicos.py
----------------------
[NO USADO EN EL FLUJO PRINCIPAL]
Script auxiliar para descargar y fusionar históricos de múltiples símbolos desde Binance.
Úsalo solo para descarga y limpieza manual de históricos.
"""

import os
import time
from datetime import datetime, timedelta, timezone
import pandas as pd
from typing import Optional, Any, Dict, List
import argparse

from src.conexion_api import get_historical_data, connect_to_binance

# Parámetros de descarga
symbols = ["WLDUSDT", "BTCUSDT", "ETHUSDT", "BNBUSDT"]
interval = "1m"
years = 1            # cuántos años descargar
per_call_limit = 1000
sleep_between_calls = 0.5

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "historicos"))
os.makedirs(OUT_DIR, exist_ok=True)

def _to_df(maybe: Any) -> Optional[pd.DataFrame]:
    if maybe is None:
        return None
    if isinstance(maybe, pd.DataFrame):
        return maybe
    try:
        return pd.DataFrame(maybe)
    except Exception:
        return None

def download_symbol(symbol: str,
                    interval: str = interval,
                    years: int = years,
                    days: Optional[int] = None,                # <-- agregado
                    limit_per_call: int = per_call_limit,
                    sleep_s: float = sleep_between_calls) -> Optional[str]:
    end_dt = datetime.now(timezone.utc)
    if days is not None:
        start_dt = end_dt - timedelta(days=days)
    else:
        start_dt = end_dt - timedelta(days=365 * years)
    client = connect_to_binance()
    all_rows: List[Dict[str, Any]] = []

    # intenta paginar usando get_historical_klines si está disponible
    if client is not None and hasattr(client, "get_historical_klines"):
        curr_start = start_dt
        while curr_start < end_dt:
            try:
                start_str = curr_start.strftime("%d %b %Y %H:%M:%S")
                klines = client.get_historical_klines(symbol, interval, start_str, limit=limit_per_call)
            except Exception:
                # fallback: intentar get_historical_data helper
                klines = None

            if not klines:
                break
            for k in klines:
                try:
                    ts = int(k[0])
                    ts_dt = datetime.fromtimestamp(ts/1000.0, tz=timezone.utc)
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
            curr_start = datetime.fromtimestamp((last_ts_ms + 1)/1000.0, tz=timezone.utc)
            time.sleep(sleep_s)
    else:
        # usa la función get_historical_data del proyecto (que puede devolver df o lista)
        client = client or connect_to_binance()
        page_start = start_dt
        while page_start < end_dt:
            try:
                page = get_historical_data(client, symbol=symbol, interval=interval, limit=limit_per_call, start_str=page_start)
            except TypeError:
                page = get_historical_data(client, symbol=symbol, interval=interval, limit=limit_per_call)
            df_page = _to_df(page)
            if df_page is None or df_page.empty:
                break
            # normalizar filas
            for _, r in df_page.iterrows():
                try:
                    ts = r.get("timestamp") if "timestamp" in r else r.get("open_time", None)
                    ts_dt = pd.to_datetime(ts, utc=True, errors="coerce")
                    if pd.isna(ts_dt):
                        continue
                    all_rows.append({
                        "timestamp": ts_dt,
                        "open": float(r.get("open")),
                        "high": float(r.get("high")),
                        "low": float(r.get("low")),
                        "close": float(r.get("close")),
                        "volume": float(r.get("volume")),
                        "symbol": symbol
                    })
                except Exception:
                    continue
            last_ts = all_rows[-1]["timestamp"]
            page_start = last_ts + timedelta(milliseconds=1)
            time.sleep(sleep_s)

    if not all_rows:
        print(f"No se obtuvieron velas para {symbol}")
        return None

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["timestamp", "symbol"]).sort_values("timestamp").reset_index(drop=True)
    # asegurar tipos
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp","close"])
    out_path = os.path.join(OUT_DIR, f"historial_{symbol}.csv")
    df.to_csv(out_path, index=False)
    print("✅ Datos guardados en", out_path, "filas:", len(df))
    return out_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descargar históricos (paginado) por símbolo")
    parser.add_argument("--symbols", "-s", type=str, default=",".join(symbols),
                        help="Lista de símbolos separados por coma (ej: BTCUSDT,ETHUSDT)")
    parser.add_argument("--interval", "-i", type=str, default=interval, help="Intervalo (1m,5m,15m...)")
    parser.add_argument("--days", "-d", type=int, default=None, help="Descargar últimos N días (si se pasa, ignora --years)")
    parser.add_argument("--years", "-y", type=int, default=years, help="Años a descargar (si no se usa --days)")
    args = parser.parse_args()

    req_symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    saved = []
    for s in req_symbols:
        try:
            p = download_symbol(s, interval=args.interval, years=args.years, days=args.days)
            if p:
                saved.append(p)
        except Exception as e:
            print("Fallo descarga", s, e)

    # fusión igual que antes
    if saved:
        dfs = []
        for p in saved:
            try:
                d = pd.read_csv(p, parse_dates=["timestamp"], dtype={"symbol":str})
                dfs.append(d)
            except Exception:
                continue
        if dfs:
            df_final = pd.concat(dfs, ignore_index=True)
            df_final = df_final.drop_duplicates(subset=["timestamp","symbol"]).sort_values(["symbol","timestamp"])
            out_master = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "historiales", "historial_trading_limpio.csv"))
            os.makedirs(os.path.dirname(out_master), exist_ok=True)
            df_final.to_csv(out_master, index=False)
            print("✅ Archivo fusionado guardado en", out_master)
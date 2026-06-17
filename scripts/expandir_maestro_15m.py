"""
expandir_maestro_15m.py
-----------------------
Descarga y anexa ~60 días adicionales (configurable) de velas 15m por símbolo
al maestro `historial_trading_maestro_15m.csv`, evitando duplicados y
validando integridad básica.

Uso:
  python scripts/expandir_maestro_15m.py \
      --maestro data/historiales/historial_trading_maestro_15m.csv \
      --out data/historiales/historial_trading_maestro_15m.csv \
      --days-back 60

Artefactos:
 - Maestro actualizado (backup si existe)
 - data/historiales/log_expansion_maestro.md
"""
from __future__ import annotations
import os
import sys
import argparse
from pathlib import Path
from datetime import timedelta
import time
from typing import List, Dict, Tuple

import pandas as pd
import numpy as np

# Asegurar path del repo
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.pipeline.conexion_api import connect_to_binance  # type: ignore

FREQ_SEC = 15 * 60
BINANCE_LIMIT = 1000  # máximo por página


def _read_maestro(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume","symbol"])  # vacío
    df = pd.read_csv(path)
    # normalizar
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for c in ("open","high","low","close","volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df = df.dropna(subset=["timestamp"]).sort_values(["symbol","timestamp"]).drop_duplicates(["symbol","timestamp"])
    return df


def _symbols_in_maestro(df: pd.DataFrame) -> List[str]:
    return sorted(df["symbol"].dropna().astype(str).unique().tolist()) if "symbol" in df.columns else []


def _paginate_klines(client, symbol: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame:
    """Paginación hacia adelante entre start_ts y end_ts (UTC)."""
    out_frames: List[pd.DataFrame] = []
    start_ms = int(start_ts.timestamp() * 1000)
    end_ms_target = int(end_ts.timestamp() * 1000)
    page_span_ms = BINANCE_LIMIT * FREQ_SEC * 1000
    cur_start = start_ms
    while cur_start <= end_ms_target:
        cur_end = min(end_ms_target, cur_start + page_span_ms - 1)
        try:
            # Llamada directa al cliente para evitar simulados
            rows = client.get_klines(symbol=symbol, interval="15m", limit=BINANCE_LIMIT, startTime=cur_start, endTime=cur_end)
        except Exception as e:
            time.sleep(0.8)
            # reintentar una vez sin endTime (Binance a veces ignora)
            try:
                rows = client.get_klines(symbol=symbol, interval="15m", limit=BINANCE_LIMIT, startTime=cur_start)
            except Exception:
                rows = []
        if not rows:
            # avanzar de todas maneras para evitar bucles infinitos
            cur_start = cur_end + 1
            continue
        # Normalizar lista de listas -> DataFrame
        # Esquema Binance: [ openTime, open, high, low, close, volume, closeTime, ... ]
        cols = [
            "open_time","open","high","low","close","volume","close_time",
            "qav","num_trades","taker_base_vol","taker_quote_vol","ignore"
        ]
        df = pd.DataFrame(rows, columns=cols[:len(rows[0])])
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        for c in ("open","high","low","close","volume"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df[["timestamp","open","high","low","close","volume"]]
        df["symbol"] = symbol
        out_frames.append(df)
        # avanzar al siguiente bloque
        last_open = int(pd.to_datetime(rows[-1][0], unit="ms", utc=True).timestamp() * 1000)
        cur_start = last_open + FREQ_SEC * 1000
    if not out_frames:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume","symbol"])
    out = pd.concat(out_frames, ignore_index=True)
    out = out.dropna(subset=["timestamp"]).drop_duplicates(["symbol","timestamp"]).sort_values("timestamp")
    return out


def _validate_chunk(df: pd.DataFrame) -> Tuple[bool, Dict[str, int]]:
    """Validaciones básicas: sin NaN OHLCV, sin gaps > 1 vela (diagnóstico rápido)."""
    stats = {
        "nan_open": int(df["open"].isna().sum() if "open" in df.columns else 0),
        "nan_high": int(df["high"].isna().sum() if "high" in df.columns else 0),
        "nan_low": int(df["low"].isna().sum() if "low" in df.columns else 0),
        "nan_close": int(df["close"].isna().sum() if "close" in df.columns else 0),
        "nan_volume": int(df["volume"].isna().sum() if "volume" in df.columns else 0),
        "high_lt_low": int((df["high"] < df["low"]).sum()) if {"high","low"}.issubset(df.columns) else 0,
        "gaps_gt1": 0,
    }
    if not df.empty:
        deltas = df.sort_values("timestamp")["timestamp"].diff().dt.total_seconds().dropna().astype(int)
        stats["gaps_gt1"] = int((deltas != FREQ_SEC).sum())
    ok = all(v == 0 for k, v in stats.items() if k != "gaps_gt1") and stats["gaps_gt1"] == 0
    return ok, stats


def expandir_maestro(maestro_path: Path, out_path: Path, days_back: int) -> Path:
    maestro = _read_maestro(maestro_path)
    if maestro.empty:
        raise SystemExit(f"Maestro base vacío o no existe: {maestro_path}")
    symbols = _symbols_in_maestro(maestro)
    if not symbols:
        raise SystemExit("Maestro sin columna symbol o sin símbolos válidos")

    client = connect_to_binance()
    if client is None:
        raise SystemExit("No hay conexión a Binance. Configura API keys en data/config.env")

    log_lines = ["# Log de expansión maestro 15m", ""]
    total_appended = 0

    for sym in symbols:
        cur = maestro[maestro["symbol"] == sym]
        earliest = cur["timestamp"].min()
        target_start = earliest - pd.Timedelta(days=days_back)
        log_lines.append(f"## {sym}")
        log_lines.append(f"Rango actual: {cur['timestamp'].min()} → {cur['timestamp'].max()} ({len(cur)} filas)")
        log_lines.append(f"Objetivo de expansión: agregar desde {target_start} hasta < {earliest}")
        # Paginación
        df_new = _paginate_klines(client, sym, target_start, earliest - pd.Timedelta(seconds=1))
        if df_new.empty:
            log_lines.append("- Sin datos nuevos obtenidos (API)\n")
            continue
        # Validar chunk
        ok, stats = _validate_chunk(df_new)
        excl = []
        if stats["nan_open"] or stats["nan_high"] or stats["nan_low"] or stats["nan_close"]:
            excl.append("NaN en OHLC")
        if stats["high_lt_low"]:
            excl.append("high<low")
        if stats["gaps_gt1"]:
            excl.append(">1 gap de 15m")
        if excl:
            log_lines.append(f"- Advertencia: inconsistencias detectadas: {', '.join(excl)}. Se filtrará y continuará.")
            # Filtrar NaN y high<low
            if {"high","low"}.issubset(df_new.columns):
                df_new = df_new[df_new["high"] >= df_new["low"]]
            for c in ("open","high","low","close","volume"):
                if c in df_new.columns:
                    df_new = df_new[df_new[c].notna()]
            # Sobre gaps: no reparamos, sólo advertimos. Binance 15m no debería tener gaps en ese tramo.
        pre_len = len(maestro)
        maestro = pd.concat([maestro, df_new], ignore_index=True)
        maestro = maestro.drop_duplicates(["symbol","timestamp"]).sort_values(["symbol","timestamp"]).reset_index(drop=True)
        added = len(maestro) - pre_len
        total_appended += max(0, added)
        new_min = maestro.loc[maestro["symbol"] == sym, "timestamp"].min()
        days_cov = (maestro.loc[maestro["symbol"] == sym, "timestamp"].max() - new_min).total_seconds() / 86400
        log_lines.append(f"- Velas nuevas añadidas: {added}")
        log_lines.append(f"- Nuevo inicio para {sym}: {new_min} (cobertura ~{days_cov:.1f} días)\n")

    # Persistir maestro (backup previo)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        backup = out_path.with_suffix(out_path.suffix + f".bak_{pd.Timestamp.utcnow().strftime('%Y%m%d%H%M%S')}")
        out_path.rename(backup)
        print(f"Backup maestro previo: {backup.name}")
    maestro.to_csv(out_path, index=False)

    # Escribir log
    log_path = out_path.parent / "log_expansion_maestro.md"
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(log_lines))
        fh.write("\n\n---\n")
        fh.write(f"Total velas nuevas agregadas: {total_appended}\n")
        fh.write(f"Generado: {pd.Timestamp.utcnow().isoformat()}Z\n")
    print(f"Log: {log_path}")
    return out_path


def main(maestro: str, out: str, days_back: int):
    expandir_maestro(Path(maestro), Path(out), days_back)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--maestro", default="data/historiales/historial_trading_maestro_15m.csv")
    p.add_argument("--out", default="data/historiales/historial_trading_maestro_15m.csv")
    p.add_argument("--days-back", type=int, default=60)
    args = p.parse_args()
    main(args.maestro, args.out, args.days_back)

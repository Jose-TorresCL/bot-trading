"""
incorporar_simbolo.py
---------------------
Extrae un símbolo desde un maestro grande, lo resamplea a la frecuencia objetivo (default 15min)
y reconstruye el maestro procesado uniforme.

Uso:
  python scripts/incorporar_simbolo.py \
      --symbol WLDUSDT \
      --maestro data/historiales/historial_trading_acum.csv \
      --raw-dir data/historiales/raw \
      --processed-dir data/historiales/processed \
      --out-maestro data/historiales/historial_trading_maestro_15m.csv \
      --freq 15min
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

try:
    from src.pipeline.frecuencia_datos import incorporar_nuevo_simbolo  # type: ignore
except ModuleNotFoundError:
    from pipeline.frecuencia_datos import incorporar_nuevo_simbolo  # type: ignore


def main(symbol: str, maestro: str, raw_dir: str, processed_dir: str, out_maestro: str, freq: str):
    result = incorporar_nuevo_simbolo(Path(maestro), symbol, Path(raw_dir), Path(processed_dir), Path(out_maestro), target_freq=freq)
    if result:
        print(f"Maestro actualizado en {result}")
    else:
        print("No se pudo actualizar maestro para el símbolo.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True, help="Símbolo a incorporar (ej: WLDUSDT)")
    p.add_argument("--maestro", default="data/historiales/historial_trading_acum.csv", help="Maestro grande de origen")
    p.add_argument("--raw-dir", default="data/historiales/raw", help="Directorio para guardar raw extraído")
    p.add_argument("--processed-dir", default="data/historiales/processed", help="Directorio para guardados en frecuencia objetivo")
    p.add_argument("--out-maestro", default="data/historiales/historial_trading_maestro_15m.csv", help="Archivo maestro final uniforme")
    p.add_argument("--freq", default="15min", help="Frecuencia objetivo (default 15min)")
    args = p.parse_args()
    main(args.symbol, args.maestro, args.raw_dir, args.processed_dir, args.out_maestro, args.freq)

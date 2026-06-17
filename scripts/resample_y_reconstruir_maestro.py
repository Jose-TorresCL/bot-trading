"""
resample_y_reconstruir_maestro.py
---------------------------------
Automatiza:
 1. Resampleo de todos los símbolos crudos a la frecuencia estándar (15min)
 2. Construcción del maestro uniforme `historial_trading_maestro_15m.csv`

Uso:
  python scripts/resample_y_reconstruir_maestro.py \
      --raw-dir data/historiales/raw \
      --processed-dir data/historiales/processed \
      --out data/historiales/historial_trading_maestro_15m.csv \
      --freq 15min

Notas:
 - Sólo se resamplea si la serie es más granular que la frecuencia objetivo.
 - Archivos ya en 15m se copian normalizados a processed.
 - Se omiten archivos más gruesos (ej: 1h) para evitar upsampling artificial.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import sys
from pathlib import Path as _P

# Soporte ejecución directa añadiendo raíz del repo al sys.path si no se instaló como paquete
_ROOT = _P(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

try:
    from src.pipeline.frecuencia_datos import asegurar_y_construir  # type: ignore
except ModuleNotFoundError:
    # fallback intento directo (si estructura distinta)
    from pipeline.frecuencia_datos import asegurar_y_construir  # type: ignore


def main(raw_dir: str, processed_dir: str, out: str, freq: str = "15min"):
    asegurar_y_construir(Path(raw_dir), Path(processed_dir), Path(out), target_freq=freq)
    print(f"Maestro generado en {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", type=str, default="data/historiales/raw", help="Directorio con CSV crudos (1m, etc.)")
    p.add_argument("--processed-dir", type=str, default="data/historiales/processed", help="Salida para CSV ya en freq objetivo")
    p.add_argument("--out", type=str, default="data/historiales/historial_trading_maestro_15m.csv", help="Archivo maestro final")
    p.add_argument("--freq", type=str, default="15min", help="Frecuencia objetivo (default 15min)")
    args = p.parse_args()
    main(args.raw_dir, args.processed_dir, args.out, args.freq)

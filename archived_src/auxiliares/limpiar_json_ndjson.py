"""
limpiar_json_ndjson.py
----------------------
Limpia archivos NDJSON/JSONL eliminando líneas corruptas y sobrescribe el archivo original.
Útil para limpiar registros de operaciones y decisiones del bot.
"""

import json
import os

def limpiar_json_lines(path):
    tmp_path = path + ".tmp"
    with open(path, encoding="utf-8") as fin, open(tmp_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                fout.write(json.dumps(obj) + "\n")
            except Exception as e:
                print(f"Línea corrupta ignorada: {line}")
    os.replace(tmp_path, path)  # Sobrescribe el archivo original

if __name__ == "__main__":
    limpiar_json_lines("c:/Users/lenovo/bot_trading/semana_5/data/papertrading/registro_operaciones.json")
    limpiar_json_lines("c:/Users/lenovo/bot_trading/semana_5/data/papertrading/registro_decisiones.json")
    print("✅ Archivos NDJSON limpios y listos para análisis.")
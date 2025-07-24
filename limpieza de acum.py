import csv

input_file = "historial_trading_acum.csv"
output_file = "historial_trading_acum_limpio.csv"

with open(input_file, newline='', encoding='utf-8') as infile:
    reader = csv.reader(infile)
    rows = list(reader)

# Detecta el número de columnas correcto usando la cabecera
header = rows[0]
expected_columns = len(header)

with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
    writer = csv.writer(outfile)
    count_total = 0
    count_ok = 0
    count_bad = 0
    for i, row in enumerate(rows):
        count_total += 1
        if len(row) == expected_columns:
            writer.writerow(row)
            count_ok += 1
        else:
            count_bad += 1

print(f"Filas totales: {count_total}")
print(f"Filas válidas: {count_ok}")
print(f"Filas corruptas eliminadas: {count_bad}")
print(f"Archivo limpio guardado como: {output_file}")
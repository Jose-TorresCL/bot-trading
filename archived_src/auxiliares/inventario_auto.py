import os

IGNORAR = {'.venv', '.git', '__pycache__'}

inventario = []
for root, dirs, files in os.walk("."):
    # Filtra carpetas ignoradas
    dirs[:] = [d for d in dirs if d not in IGNORAR]
    for file in files:
        # Ignora archivos dentro de carpetas ignoradas
        if any(ignorar in root for ignorar in IGNORAR):
            continue
        filepath = os.path.join(root, file)
        inventario.append(filepath.replace(".\\", ""))

with open("inventario_auto.md", "w", encoding="utf-8") as f:
    f.write("| Archivo | Tipo | Función/Descripción | Usabilidad |\n")
    f.write("|---------|------|--------------------|------------|\n")
    for archivo in inventario:
        f.write(f"| {archivo} |  |  |  |\n")

print("✅ Inventario generado en inventario_auto.md (sin .venv, .git, __pycache__)")
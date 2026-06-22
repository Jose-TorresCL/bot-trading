"""
fix_requirements_encoding.py
----------------------------
Convierte requirements.txt de UTF-16 a UTF-8 (LF) y agrega las dependencias
necesarias para la integracion con Lautaro (LangChain + Ollama).

Es idempotente: si requirements.txt ya esta en UTF-8 lo deja igual, y no
duplica dependencias que ya existan (compara por nombre de paquete).

Uso:
    python scripts/fix_requirements_encoding.py
"""
from __future__ import annotations

from pathlib import Path

# Raiz del proyecto = carpeta padre de scripts/
ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "requirements.txt"

# Dependencias para la capa de integracion con Lautaro.
LAUTARO_DEPS = [
    "langchain==0.2.16",
    "langchain-community==0.2.16",
    "ollama==0.3.3",
]


def _read_any_encoding(path: Path) -> str:
    """Lee el archivo probando UTF-16 primero y cae a UTF-8."""
    raw = path.read_bytes()
    # BOM UTF-16 LE (ff fe) o BE (fe ff)
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # ultimo recurso: utf-16 sin BOM
        return raw.decode("utf-16")


def _package_name(line: str) -> str:
    """Extrae el nombre normalizado del paquete de una linea de requirement."""
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    for sep in ("==", ">=", "<=", "~=", ">", "<", "!=", "==="):
        if sep in line:
            line = line.split(sep, 1)[0]
            break
    return line.strip().lower().replace("_", "-")


def main() -> None:
    if not REQ.exists():
        raise SystemExit(f"No existe {REQ}")

    content = _read_any_encoding(REQ)
    lines = [ln.rstrip("\r\n") for ln in content.splitlines()]

    existing = {_package_name(ln) for ln in lines if _package_name(ln)}

    added = []
    for dep in LAUTARO_DEPS:
        name = _package_name(dep)
        if name not in existing:
            lines.append(dep)
            existing.add(name)
            added.append(dep)

    # Reescribir en UTF-8 con LF, sin BOM
    out = "\n".join(ln for ln in lines if ln is not None) + "\n"
    REQ.write_text(out, encoding="utf-8", newline="\n")

    print(f"requirements.txt reescrito en UTF-8 (LF): {REQ}")
    if added:
        print("Dependencias agregadas:")
        for dep in added:
            print(f"  + {dep}")
    else:
        print("No se agregaron dependencias nuevas (ya estaban presentes).")


if __name__ == "__main__":
    main()

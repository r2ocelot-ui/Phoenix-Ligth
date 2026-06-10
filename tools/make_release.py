"""Generador del paquete de cliente (release limpia) — espejo de cómo
Hydra distribuye su `cliente-rXX-compilado`.

Toma el árbol de desarrollo y produce un directorio + un .zip listos para
entregar, dejando FUERA lo que un cliente no debe ver:

- ``.git/`` (historial completo del repo)
- ``backend/.venv/``, ``backend/venv/`` (entornos virtuales)
- ``backend/phoenix.db`` y cualquier ``*.db`` (usuarios, hashes, auditoría)
- ``__pycache__/``, ``*.pyc`` (bytecode)
- ``backend/tests/`` (vector de información sobre internals)
- ``backend/.pytest_cache/``
- ``.env`` real (sí incluimos ``.env.example``)
- ``docs/DECISIONS.md`` y ``docs/VERSIONS.md`` (notas internas);
  ``docs/ROADMAP.md`` sí se incluye (es público).

Diseño: lista BLANCA explícita. Cualquier carpeta nueva del repo NO se
copia hasta que se añada aquí — esto evita filtraciones por descuido.

Uso:
    python tools/make_release.py                  # genera dist/phoenix-cliente-<fecha>
    python tools/make_release.py --name foo       # nombre custom
    python tools/make_release.py --no-zip         # solo carpeta, sin zip
    python tools/make_release.py --include-sim    # incluye simulator/ y edge/
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Patrones que NUNCA copiamos, aunque alguien los meta dentro de las
# carpetas permitidas (defensa en profundidad).
EXCLUDE_NAMES = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "node_modules", ".DS_Store",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3"}

# Lista blanca: ruta relativa (dir o fichero) → ruta destino (None = misma).
# Si la fuente no existe, se avisa y se sigue.
ALLOWLIST: list[tuple[str, str | None]] = [
    # Backend (solo el paquete app + dependencias declaradas).
    ("backend/app",              None),
    ("backend/requirements.txt", None),
    ("backend/README.md",        None),
    # Frontend (HTML estático, no hay build paso).
    ("frontend",                 None),
    # Infra: docker-compose y mosquitto.conf de ejemplo.
    ("docker-compose.yml",       None),
    ("infra",                    None),
    # Lanzadores y configuración de entorno (.env.example, NO el .env real).
    ("start.bat",                None),
    ("start.sh",                 None),
    (".env.example",             None),
    # Docs públicas. ROADMAP queda; DECISIONS/VERSIONS no (notas internas).
    ("docs/ROADMAP.md",          "docs/ROADMAP.md"),
    ("README.md",                None),
    ("LICENSE",                  None),  # avisa si falta
]

# Opcional (--include-sim): añadir simulador y firmware ESP32 para
# clientes que vayan a probar sin hardware real / quieran flashear.
ALLOWLIST_SIM: list[tuple[str, str | None]] = [
    ("simulator", None),
    ("edge",      None),
]


def _skip(path: Path) -> bool:
    """¿Hay que excluir este fichero/carpeta?"""
    if path.name in EXCLUDE_NAMES:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    return False


def _copy_tree(src: Path, dst: Path) -> int:
    """Copia ``src`` (dir o fichero) en ``dst`` saltando lo excluido.
    Devuelve cuántos ficheros se copiaron."""
    copied = 0
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    for item in src.rglob("*"):
        # Si CUALQUIER componente del path está excluido → fuera. Esto
        # captura ``backend/app/__pycache__/foo.pyc`` aunque el padre
        # esté permitido.
        if any(part in EXCLUDE_NAMES for part in item.parts):
            continue
        if _skip(item):
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied += 1
    return copied


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    """Empaqueta ``src_dir`` en ``zip_path`` (rutas relativas a su padre)."""
    base = src_dir.parent
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in src_dir.rglob("*"):
            zf.write(item, item.relative_to(base))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", help="Nombre del paquete (por defecto: phoenix-cliente-YYYY-MM-DD)")
    p.add_argument("--out", default="dist", help="Carpeta de salida (default: dist/)")
    p.add_argument("--no-zip", action="store_true", help="No empaquetar en .zip")
    p.add_argument("--include-sim", action="store_true",
                   help="Incluir simulator/ y edge/ (firmware ESP32)")
    args = p.parse_args()

    name = args.name or f"phoenix-cliente-{_dt.date.today().isoformat()}"
    out_dir = ROOT / args.out / name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    rules = list(ALLOWLIST)
    if args.include_sim:
        rules += ALLOWLIST_SIM

    total = 0
    missing: list[str] = []
    for src_rel, dst_rel in rules:
        src = ROOT / src_rel
        dst = out_dir / (dst_rel or src_rel)
        if not src.exists():
            missing.append(src_rel)
            continue
        n = _copy_tree(src, dst)
        total += n
        print(f"  + {src_rel}{n} fichero(s)")

    # Aviso si falta LICENSE — fundamental para entrega a cliente.
    if "LICENSE" in missing:
        print("  ⚠ FALTA LICENSE en la raíz. Crea uno antes de entregar a un cliente.")

    if args.no_zip:
        print(f"\n✔ Carpeta lista: {out_dir} ({total} ficheros)")
    else:
        zip_path = out_dir.with_suffix(".zip")
        _zip_dir(out_dir, zip_path)
        size_kb = zip_path.stat().st_size // 1024
        print(f"\n✔ Carpeta lista: {out_dir} ({total} ficheros)")
        print(f"✔ Paquete listo: {zip_path} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Identificador de versión/build del backend.

``APP_VERSION`` es la versión semántica (la subimos a mano en saltos
importantes). ``BUILD_ID`` es el hash corto del commit actual, calculado al
arrancar: así el panel puede mostrar si estás en la última o te falta
recargar/hacer pull. Si no hay git (despliegue empaquetado), cae a "dev"
o a lo que haya en el fichero ``BUILD`` opcional de la raíz.
"""
import subprocess
from pathlib import Path

APP_VERSION = "0.1.0"

_ROOT = Path(__file__).resolve().parents[3]  # raíz del repo


def _detect_build() -> str:
    # 1) Fichero BUILD en la raíz (lo puede escribir el empaquetador de release).
    build_file = _ROOT / "BUILD"
    if build_file.exists():
        txt = build_file.read_text(encoding="utf-8").strip()
        if txt:
            return txt[:32]
    # 2) Hash corto de git (entorno de desarrollo / checkout).
    try:
        out = subprocess.run(
            ["git", "-C", str(_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:  # noqa: BLE001 — sin git: caemos al fallback
        pass
    return "dev"


BUILD_ID = _detect_build()

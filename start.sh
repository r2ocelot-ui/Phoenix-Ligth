#!/usr/bin/env bash
# ===================================================================
#  Phoenix Light - arranque fácil para Linux / macOS.
#  Uso:  doble clic (o en terminal:  bash start.sh)
#  Requisito: Python 3.11+ instalado.
# ===================================================================
set -e
cd "$(dirname "$0")/backend"

if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "  [!] No se encontró Python 3. Instálalo:"
  echo "      macOS:  brew install python   (o desde https://python.org)"
  echo "      Linux:  sudo apt install python3 python3-venv"
  echo
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Primera vez: preparando el entorno (puede tardar 1-2 minutos)..."
  python3 -m venv .venv
fi
source .venv/bin/activate
echo "Instalando/comprobando dependencias..."
python -m pip install -q -r requirements.txt

echo
echo "===================================================="
echo "  PHOENIX LIGHT - arrancando..."
echo
echo "  Abre el navegador en:  http://localhost:8000/ui/"
echo "  Usuario:  admin"
echo "  Clave:    phoenix123"
echo
echo "  Para parar: pulsa Ctrl+C"
echo "===================================================="
echo

# Intentar abrir el navegador automáticamente (no crítico).
( sleep 2
  if command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8000/ui/
  elif command -v open >/dev/null 2>&1; then open http://localhost:8000/ui/
  fi ) >/dev/null 2>&1 &

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

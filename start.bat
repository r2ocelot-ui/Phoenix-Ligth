@echo off
REM ===================================================================
REM  Phoenix Light - arranque facil para Windows (doble clic).
REM  Requisito: tener Python 3.11+ instalado desde https://python.org
REM  (en el instalador, marca la casilla "Add Python to PATH").
REM ===================================================================
cd /d "%~dp0backend"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  [!] No se encontro Python. Instalalo desde https://python.org
  echo      y marca "Add Python to PATH" durante la instalacion.
  echo.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Primera vez: preparando el entorno ^(puede tardar 1-2 minutos^)...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Instalando/comprobando dependencias...
python -m pip install -q -r requirements.txt

echo.
echo ====================================================
echo   PHOENIX LIGHT - arrancando...
echo.
echo   Abre el navegador en:  http://localhost:8000/ui/
echo   Usuario:  admin
echo   Clave:    phoenix123
echo.
echo   Para parar: cierra esta ventana.
echo ====================================================
echo.
start "" http://localhost:8000/ui/
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause

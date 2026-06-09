@echo off
REM ===================================================================
REM  Phoenix Light - arranque facil para Windows (doble clic).
REM  Requisito: Python 3.11+ instalado desde https://python.org
REM  (en el instalador, marca "Add python.exe to PATH").
REM ===================================================================
cd /d "%~dp0backend"

REM Buscar un Python REAL. Se prefiere el lanzador 'py' porque el alias de
REM Microsoft Store ("python") puede enganar a 'where python'.
set "PYEXE="
py -3 --version >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE (
  python --version >nul 2>nul && set "PYEXE=python"
)

if not defined PYEXE (
  echo.
  echo  [!] No se encontro Python instalado.
  echo.
  echo  SOLUCION:
  echo   1^) Instalalo desde  https://python.org/downloads
  echo      ^>^>^> MARCA la casilla "Add python.exe to PATH" en la 1a pantalla.
  echo.
  echo   2^) Si ya lo instalaste y sigue fallando, desactiva los alias de la Store:
  echo      Configuracion ^> Aplicaciones ^> Configuracion avanzada de aplicaciones
  echo      ^> Alias de ejecucion de aplicaciones ^> apaga "python.exe" y "python3.exe".
  echo.
  echo   Despues, vuelve a hacer doble clic en start.bat
  echo.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Primera vez: preparando el entorno ^(puede tardar 1-2 minutos^)...
  %PYEXE% -m venv .venv
)
call .venv\Scripts\activate.bat
echo Instalando/comprobando dependencias...
python -m pip install -q -r requirements.txt

echo.
echo ====================================================
echo   PHOENIX LIGHT - arrancando...
echo.
echo   Abre el navegador en:  http://localhost:8000/ui/
echo   Usuario:  phoenix
echo   Clave:    phoenix123
echo.
echo   Para parar: cierra esta ventana.
echo ====================================================
echo.
start "" http://localhost:8000/ui/
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause

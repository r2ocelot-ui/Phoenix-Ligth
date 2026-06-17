@echo off
REM Atajo Windows: ejecuta el generador de release.
cd /d "%~dp0\.."
python tools\make_release.py %*

@echo off
REM One-click KidsControl server setup (Windows). Double-click this file.
cd /d "%~dp0"
if not exist .venv (
  where py >nul 2>&1 && (py -3 -m venv .venv) || (python -m venv .venv)
)
if not exist .venv\Scripts\python.exe (
  echo Python 3.10+ fehlt. Bitte von https://www.python.org/downloads/ installieren.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo KidsControl startet auf http://127.0.0.1:8000/
start "" http://127.0.0.1:8000/
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause

@echo off
setlocal
cd /d "%~dp0"
echo =======================================
echo   RiskLens AI - MRIS Dashboard
echo =======================================
if not exist ".venv\Scripts\python.exe" (
  echo Creating local virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python not found. Install Python 3.11+ and try again.
    pause
    exit /b 1
  )
)
echo Checking and installing dashboard dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements-server.txt
if errorlevel 1 (
  echo Dependency installation failed. Check the error above and your internet connection.
  pause
  exit /b 1
)
set MRIS_LLM_MODE=mock
echo.
echo Dashboard URL: http://127.0.0.1:8000/ui
echo API docs:       http://127.0.0.1:8000/docs
echo Demo mode uses a mock LLM. Scraping uses real public websites.
echo Stop with CTRL+C.
".venv\Scripts\python.exe" -m uvicorn mris.api:app --app-dir src --host 127.0.0.1 --port 8000
pause

@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo   RiskLens AI - Access Diagnostics
echo ========================================
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run run_dashboard.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\diagnose_access.py %*
echo.
echo Copy the Status and Reason lines for help. Do not share private URLs or tokens.
pause

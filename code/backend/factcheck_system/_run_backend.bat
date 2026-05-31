@echo off
title Backend FastAPI - http://localhost:8000
cd /d "%~dp0"
call venv\Scripts\activate.bat

echo Syncing packages...
pip install -r requirements.txt -q --disable-pip-version-check

:: Prevent Windows from sleeping while backend is running.
:: Uses powercfg to require system+display awake. Auto-restored on exit.
powercfg /requestsoverride PROCESS python.exe SYSTEM AWAYMODE >nul 2>&1

echo.
echo Starting FastAPI on http://localhost:8000 ...
echo (Auto-fetches trending news every 6 hours)
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo [Server stopped]
pause

@echo off
title Backend FastAPI - http://localhost:8000
cd /d "%~dp0"
:: Local development backend. The public site runs on Render, so this PC no longer has to stay awake
:: (the old "powercfg /requestsoverride" keep-awake line was removed on 2026-09-19).
:: "python -m ..." instead of activate.bat / pip.exe / uvicorn.exe: those hard-code the folder the venv
:: was created in and stop working when the project folder is moved.

echo Syncing packages...
venv\Scripts\python.exe -m pip install -r requirements.txt -q --disable-pip-version-check

echo.
echo Starting FastAPI on http://localhost:8000 ...
echo (Scheduler off by default; set ENABLE_SCHEDULER=true in .env for auto-fetch)
echo.
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo [Server stopped]
pause

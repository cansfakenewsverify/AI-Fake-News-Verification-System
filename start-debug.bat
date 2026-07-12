@echo off
title AI Fake News - Debug Mode

echo.
echo ============================================
echo  DIAGNOSTIC MODE - Running step by step
echo ============================================
echo.

set BACKEND_DIR=%~dp0code\backend
set FRONTEND_DIR=%~dp0code\frontend
set VENV=%BACKEND_DIR%\venv

echo Backend dir: %BACKEND_DIR%
echo Frontend dir: %FRONTEND_DIR%
echo VENV: %VENV%
echo.

echo --- Test 1: Does venv exist? ---
if exist "%VENV%\Scripts\python.exe" (
    echo OK: venv found
    "%VENV%\Scripts\python.exe" --version
) else (
    echo MISSING: venv not found at %VENV%
    pause & exit /b 1
)
echo.

echo --- Test 2: Is uvicorn installed? ---
"%VENV%\Scripts\python.exe" -m uvicorn --version
if errorlevel 1 (
    echo ERROR: uvicorn missing. Re-run start.bat to install.
    pause & exit /b 1
)
echo.

echo --- Test 3: Does the FastAPI app import? ---
cd /d "%BACKEND_DIR%"
"%VENV%\Scripts\python.exe" -c "from app.main import app; print('OK: app loaded')"
if errorlevel 1 (
    echo ERROR: app import failed - see error above
    pause & exit /b 1
)
echo.

echo --- Test 4: Does node_modules exist? ---
if exist "%FRONTEND_DIR%\node_modules" (
    echo OK: node_modules found
) else (
    echo MISSING: node_modules - run: cd %FRONTEND_DIR% ^&^& npm install
)
echo.

echo ============================================
echo  All checks passed. Starting backend now...
echo  Press Ctrl+C to stop.
echo ============================================
echo.

cd /d "%BACKEND_DIR%"
"%VENV%\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause

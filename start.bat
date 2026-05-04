@echo off
title AI Fake News Verification System

echo.
echo  ========================================
echo   AI Fake News System - Starting...
echo  ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+
    echo         https://www.python.org/downloads/
    pause & exit /b 1
)

:: Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 18+
    echo         https://nodejs.org/
    pause & exit /b 1
)

:: Paths
set ROOT=%~dp0
set BACKEND_DIR=%ROOT%code\backend\factcheck_system
set FRONTEND_DIR=%ROOT%code\frontend
set VENV=%BACKEND_DIR%\venv

:: Copy .env if not exists
if not exist "%BACKEND_DIR%\.env" (
    echo [Setup] Creating .env from .env.example ...
    copy "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env" >nul
    echo [Setup] Please fill in GOOGLE_API_KEY in:
    echo         %BACKEND_DIR%\.env
    echo.
)

:: Create virtualenv
if not exist "%VENV%" (
    echo [Backend] Creating Python virtual environment...
    python -m venv "%VENV%"
)

:: Install backend deps
echo [Backend] Installing/updating packages (first time may take a while)...
"%VENV%\Scripts\pip" install -r "%BACKEND_DIR%\requirements.txt" -q --disable-pip-version-check

:: Install frontend deps
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [Frontend] Installing npm packages (first time may take a while)...
    pushd "%FRONTEND_DIR%"
    npm install
    popd
)

:: Start backend in new window
echo.
echo [Backend] Starting FastAPI at http://localhost:8000 ...
start "Backend FastAPI" cmd /k "cd /d "%BACKEND_DIR%" && venv\Scripts\activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak > nul

:: Start frontend in new window
echo [Frontend] Starting React at http://localhost:5173 ...
start "Frontend React" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

timeout /t 4 /nobreak > nul

:: Open browser
start "" "http://localhost:5173"

echo.
echo  ========================================
echo   Done!
echo   Frontend : http://localhost:5173
echo   Backend  : http://localhost:8000
echo   API Docs : http://localhost:8000/docs
echo  ========================================
echo.
echo  To stop: close the "Backend FastAPI" and "Frontend React" windows.
echo.
pause

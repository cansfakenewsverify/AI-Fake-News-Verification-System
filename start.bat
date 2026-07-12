@echo off
title AI Fake News System

echo.
echo  ========================================
echo   AI Fake News System - Starting...
echo  ========================================
echo.

:: Check Python
echo [1/5] Checking Python...
python --version
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from https://www.python.org/
    pause & exit /b 1
)

:: Check Node.js (for React frontend)
echo [2/5] Checking Node.js...
node --version
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    pause & exit /b 1
)

:: Paths (backend flattened to code\backend)
:: The single-file detector (fake-news-detector.html) is an OFFLINE BACKUP:
:: double-click it directly, or run _run_detector.bat to serve it on :8090.
set ROOT=%~dp0
set BACKEND_DIR=%ROOT%code\backend
set FRONTEND_DIR=%ROOT%code\frontend
set VENV=%BACKEND_DIR%\venv

:: Copy .env
if not exist "%BACKEND_DIR%\.env" (
    echo [Setup] Creating .env from .env.example ...
    copy "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env" >nul
    echo [Setup] Edit %BACKEND_DIR%\.env and fill in API keys
    echo.
)

:: Create virtualenv
echo [3/5] Setting up Python virtual environment...
if not exist "%VENV%" (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause & exit /b 1
    )
)

:: Sync backend deps
echo [4/5] Syncing backend packages...
"%VENV%\Scripts\pip" install -r "%BACKEND_DIR%\requirements.txt" -q --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause & exit /b 1
)

:: Install frontend deps (only first time)
echo [5/5] Checking frontend packages...
if not exist "%FRONTEND_DIR%\node_modules" (
    echo Installing npm packages, this may take a few minutes...
    pushd "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 ( echo [ERROR] npm install failed & popd & pause & exit /b 1 )
    popd
) else (
    echo Frontend packages already installed.
)

echo.
echo  Launching backend + React ...
echo.

:: Start backend (helper bat lives in code\backend after flatten)
start "" "%BACKEND_DIR%\_run_backend.bat"
echo Backend     : http://localhost:8000

timeout /t 3 /nobreak > nul

:: Start React dev server (main UI)
start "" "%FRONTEND_DIR%\_run_frontend.bat"
echo React       : http://localhost:5173

timeout /t 4 /nobreak > nul

:: Open the main UI in the browser
echo Opening browser ...
start "" "http://localhost:5173"

echo.
echo  ========================================
echo   Done!
echo   Main UI (React) : http://localhost:5173
echo   Backend API     : http://localhost:8000/docs
echo   Offline backup  : double-click fake-news-detector.html
echo                     (works even without backend / network)
echo  ========================================
echo.
echo  This window can be closed.
echo  To stop, close the Backend / React windows.
echo.
pause

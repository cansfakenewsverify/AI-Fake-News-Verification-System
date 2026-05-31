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

:: Check Node.js
echo [2/5] Checking Node.js...
node --version
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    pause & exit /b 1
)

:: Paths
set BACKEND_DIR=%~dp0code\backend\factcheck_system
set FRONTEND_DIR=%~dp0code\frontend
set VENV=%BACKEND_DIR%\venv

:: Copy .env
if not exist "%BACKEND_DIR%\.env" (
    echo [Setup] Copying .env.example to .env ...
    copy "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env"
    echo [Setup] Edit %BACKEND_DIR%\.env and fill in GOOGLE_API_KEY
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

:: Always sync backend deps with requirements.txt
echo [4/5] Syncing backend packages...
"%VENV%\Scripts\pip" install -r "%BACKEND_DIR%\requirements.txt" -q --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause & exit /b 1
)

:: Install frontend deps
echo [5/5] Checking frontend packages...
if not exist "%FRONTEND_DIR%\node_modules" (
    echo Installing npm packages, this may take a few minutes...
    pushd "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed
        popd & pause & exit /b 1
    )
    popd
) else (
    echo Frontend packages already installed.
)

echo.
echo ============================================
echo  Opening backend and frontend windows...
echo ============================================
echo.

:: Start backend (uses pre-existing helper bat in same folder)
start "" "%BACKEND_DIR%\_run_backend.bat"
echo Backend window launched.

timeout /t 3 /nobreak > nul

:: Start frontend
start "" "%FRONTEND_DIR%\_run_frontend.bat"
echo Frontend window launched.

timeout /t 5 /nobreak > nul

:: Open browser
echo Opening browser at http://localhost:5173 ...
start "" "http://localhost:5173"

echo.
echo  ========================================
echo   Done!
echo   Frontend : http://localhost:5173
echo   Backend  : http://localhost:8000
echo   API Docs : http://localhost:8000/docs
echo  ========================================
echo.
echo  This window can be closed.
echo  To stop the servers, close the Backend and Frontend windows.
echo.
pause

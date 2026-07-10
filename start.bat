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

:: Paths (backend flattened to code\backend; detector is the root single-file HTML)
set ROOT=%~dp0
set BACKEND_DIR=%ROOT%code\backend
set FRONTEND_DIR=%ROOT%code\frontend
set VENV=%BACKEND_DIR%\venv
set HTML_PORT=8090

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
echo  Launching backend + detector + React ...
echo.

:: Start backend (helper bat lives in code\backend after flatten)
start "" "%BACKEND_DIR%\_run_backend.bat"
echo Backend     : http://localhost:8000

timeout /t 3 /nobreak > nul

:: Start detector frontend (static server for the single-file HTML)
start "" "%ROOT%_run_detector.bat"
echo Detector    : http://localhost:%HTML_PORT%/fake-news-detector.html

:: Start React dev server
start "" "%FRONTEND_DIR%\_run_frontend.bat"
echo React       : http://localhost:5173

timeout /t 4 /nobreak > nul

:: Open both frontends in the browser
echo Opening browsers ...
start "" "http://localhost:%HTML_PORT%/fake-news-detector.html"
start "" "http://localhost:5173"

echo.
echo  ========================================
echo   Done!
echo   Detector (single HTML) : http://localhost:%HTML_PORT%/fake-news-detector.html
echo   React (full app)       : http://localhost:5173
echo   Backend API            : http://localhost:8000/docs
echo  ========================================
echo.
echo  This window can be closed.
echo  To stop, close the Backend / Detector / React windows.
echo.
pause

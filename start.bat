@echo off
title AI Fake News System

echo.
echo  ========================================
echo   AI Fake News System - Starting...
echo  ========================================
echo.

:: Check Python
echo [1/4] Checking Python...
python --version
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from https://www.python.org/
    pause & exit /b 1
)

:: Paths (backend flattened to code\backend; detector is the root single-file HTML)
set ROOT=%~dp0
set BACKEND_DIR=%ROOT%code\backend
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
echo [2/4] Setting up Python virtual environment...
if not exist "%VENV%" (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause & exit /b 1
    )
)

:: Sync backend deps
echo [3/4] Syncing backend packages...
"%VENV%\Scripts\pip" install -r "%BACKEND_DIR%\requirements.txt" -q --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause & exit /b 1
)

echo [4/4] Launching backend + detector frontend...
echo.

:: Start backend (helper bat lives in code\backend after flatten)
start "" "%BACKEND_DIR%\_run_backend.bat"
echo Backend window launched (http://localhost:8000).

timeout /t 3 /nobreak > nul

:: Start detector frontend (static server for the single-file HTML)
start "" "%ROOT%_run_detector.bat"
echo Detector window launched (http://localhost:%HTML_PORT%).

timeout /t 2 /nobreak > nul

:: Open browser at the detector page
echo Opening browser ...
start "" "http://localhost:%HTML_PORT%/fake-news-detector.html"

echo.
echo  ========================================
echo   Done!
echo   Detector : http://localhost:%HTML_PORT%/fake-news-detector.html
echo   Backend  : http://localhost:8000
echo   API Docs : http://localhost:8000/docs
echo  ========================================
echo.
echo  This window can be closed.
echo  To stop, close the Backend and Detector windows.
echo  (React frontend still available: code\frontend\_run_frontend.bat)
echo.
pause

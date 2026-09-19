@echo off
title AI Fake News System - local development

:: Local development only. To USE the system, open the live site:
::   https://fakenewsverify.vercel.app
:: (frontend on Vercel, backend on Render, data on Supabase; see docs/rebuild/runbook_cloud_deploy.md)
:: This script starts a local backend (8000) + React dev server (5173) that use LOCAL data files.

echo.
echo  ========================================
echo   AI Fake News System - local development
echo   Live site: https://fakenewsverify.vercel.app
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
set ROOT=%~dp0
set BACKEND_DIR=%ROOT%code\backend
set FRONTEND_DIR=%ROOT%code\frontend
set VENV=%BACKEND_DIR%\venv

:: Copy .env (first run only)
:: spec 5.6: the new .env gets a random 32-char ADMIN_TOKEN if it is empty (token never printed)
if not exist "%BACKEND_DIR%\.env" (
    echo [Setup] Creating .env from .env.example ...
    copy "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env" >nul
    echo [Setup] Edit %BACKEND_DIR%\.env and fill in API keys
    echo.
)
:: Every launch: make sure ADMIN_TOKEN is set (fills an empty or missing line; token never printed)
python "%BACKEND_DIR%\scripts\ensure_admin_token.py" "%BACKEND_DIR%\.env"

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
:: "python -m pip" (not pip.exe): the .exe launchers stop working when the project folder is moved
"%VENV%\Scripts\python.exe" -m pip install -r "%BACKEND_DIR%\requirements.txt" -q --disable-pip-version-check
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
echo   Done! (local development copy, local data)
echo   Main UI (React) : http://localhost:5173
echo   Backend API     : http://localhost:8000/docs
echo   Live site       : https://fakenewsverify.vercel.app
echo  ========================================
echo.
echo  This window can be closed.
echo  To stop, close the Backend / React windows.
echo.
pause

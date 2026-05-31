@echo off
title Frontend React - http://localhost:5173
cd /d "%~dp0"
echo.
echo Starting Vite dev server on http://localhost:5173 ...
echo.
call npm run dev
echo.
echo [Server stopped]
pause

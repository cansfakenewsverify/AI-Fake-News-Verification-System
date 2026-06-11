@echo off
title Detector Frontend - http://localhost:8090
cd /d "%~dp0"

echo.
echo  Serving detector frontend (single-file HTML) on:
echo    http://localhost:8090/fake-news-detector.html
echo.
echo  Keep this window open. Close it to stop the frontend.
echo.

python -m http.server 8090

echo.
echo  [Detector server stopped]
pause

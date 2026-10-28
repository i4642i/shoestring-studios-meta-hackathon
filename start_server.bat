@echo off
REM Shoestring Studios - one-click backend start.
REM Double-click: starts the server in its own window and opens the site.
setlocal
cd /d "%~dp0"

set PY=python
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ first:
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set PY=py -3
)
if not exist "scripts\server.py" (
  echo [ERROR] scripts\server.py not found. Put this file in the project root.
  pause
  exit /b 1
)
if not exist ".env" (
  echo [WARN] .env missing. The site loads, but agent runs need MODEL_API_KEY.
  echo        Create .env with: MODEL_API_KEY=your-key-here
  echo.
)

netstat -an | findstr "LISTENING" | findstr /r ":8000[^0-9]" >nul
if errorlevel 1 (
  set BROWSER=1
) else (
  set BROWSER=0
  echo [WARN] Port 8000 is busy. The server will pick another port,
  echo        so read the URL from the server window instead of the browser.
  echo.
)

start "Shoestring Studios (server - close this window to stop)" %PY% scripts\server.py
if "%BROWSER%"=="1" (
  timeout /t 3 /nobreak >nul
  start "" "http://localhost:8000"
  echo [OK] Server starting in a new window, browser opening...
) else (
  echo [OK] Server starting in a new window.
  pause
)

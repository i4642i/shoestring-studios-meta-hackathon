@echo off
REM Shoestring Studios - one-click backend start.
REM Double-click: sets up .venv, installs deps if needed, starts the server, opens the site.
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

REM ---- Project environment (.venv lives in the project, never the system) ----
set VENVPY=.venv\Scripts\python.exe
if not exist "%VENVPY%" (
  echo [INFO] Creating project environment .venv...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create .venv with %PY%.
    pause
    exit /b 1
  )
)
"%VENVPY%" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo [INFO] Bootstrapping pip inside .venv...
  "%VENVPY%" -m ensurepip --default-pip
)

REM ---- Install requirements.txt only when it changed (hash in .venv\requirements.sha) ----
set NEWHASH=
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "requirements.txt" SHA256 2^>nul') do (
  if not defined NEWHASH set "NEWHASH=%%H"
)
set OLDHASH=
if exist ".venv\requirements.sha" set /p OLDHASH=<".venv\requirements.sha"
if "%NEWHASH%"=="" (
  echo [WARN] Could not hash requirements.txt; installing to be safe.
  set OLDHASH=FORCE-INSTALL
)
if "%NEWHASH%"=="%OLDHASH%" (
  echo [INFO] Dependencies unchanged, skipping install.
) else (
  echo [INFO] Installing requirements into .venv - LightRAG stays in .venv-lightrag...
  "%VENVPY%" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Install failed - no internet? Checking what is already there...
    "%VENVPY%" scripts\check_deps.py
    if errorlevel 1 (
      echo [ERROR] Required packages are missing and install failed. Start aborted.
      pause
      exit /b 1
    )
    echo [WARN] Continuing with already-installed packages; changed requirements are NOT applied.
  ) else (
    >".venv\requirements.sha" echo %NEWHASH%
  )
)

REM Stop any previous Shoestring server first (ours only: python running scripts/server.py).
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and ($_.CommandLine -like '*scripts/server.py*' -or $_.CommandLine -like '*scripts\server.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Output ('[INFO] Stopped previous server (PID ' + $_.ProcessId + ').') }"
timeout /t 2 /nobreak >nul

netstat -an | findstr "LISTENING" | findstr /r ":8000[^0-9]" >nul
if errorlevel 1 (
  set BROWSER=1
) else (
  set BROWSER=0
  echo [WARN] Port 8000 is busy. The server will pick another port,
  echo        so read the URL from the server window instead of the browser.
  echo.
)

start "Shoestring Studios (server - close this window to stop)" "%VENVPY%" scripts\server.py
if "%BROWSER%"=="1" (
  timeout /t 3 /nobreak >nul
  start "" "http://localhost:8000"
  echo [OK] Server starting in a new window, browser opening...
) else (
  echo [OK] Server starting in a new window.
  pause
)

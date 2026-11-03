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
  echo [INFO] Installing requirements into .venv - includes LightRAG, first run is slow...
  "%VENVPY%" scripts\pip_install.py
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

REM ---- Video toolchain, part 1: Kokoro voice (requirements-video.txt), only when it changed ----
set VHASH=
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "requirements-video.txt" SHA256 2^>nul') do (
  if not defined VHASH set "VHASH=%%H"
)
set OLDVHASH=
if exist ".venv\requirements-video.sha" set /p OLDVHASH=<".venv\requirements-video.sha"
if "%VHASH%"=="" set OLDVHASH=FORCE-INSTALL
if "%VHASH%"=="%OLDVHASH%" (
  echo [INFO] Voice packages unchanged, skipping install.
) else (
  echo [INFO] Installing voice packages - Kokoro TTS, first run downloads a few hundred MB...
  "%VENVPY%" -m pip install --disable-pip-version-check -r requirements-video.txt
  if errorlevel 1 (
    echo [WARN] Voice packages failed to install. Wren cannot make narration until this works:
    echo        .venv\Scripts\python -m pip install -r requirements-video.txt
  ) else (
    >".venv\requirements-video.sha" echo %VHASH%
  )
)

REM ---- Video toolchain, part 2: Remotion slide renderer (needs Node.js 16+) ----
REM Node.js is installed automatically with winget when it is missing
REM (24.x, the line the renderer was tested on; Windows may ask for admin).
where node >nul 2>nul
if errorlevel 1 if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%PATH%"
where node >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if errorlevel 1 (
    echo [WARN] Node.js not found and winget is not available.
  ) else (
    echo [INFO] Node.js not found - installing Node.js 24 LTS with winget, please accept the prompts...
    winget install --id OpenJS.NodeJS.LTS --exact --version 24.22.1 --silent --accept-package-agreements --accept-source-agreements
    if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%PATH%"
  )
)
where node >nul 2>nul
if errorlevel 1 (
  echo [WARN] Node.js not found. Remy cannot render slides, so no video can be made.
  echo        Install Node.js LTS from https://nodejs.org/ and run start_server.bat again.
) else (
  if not exist "video\remotion\node_modules" (
    echo [INFO] Installing the Remotion slide renderer - npm, first run is slow...
    pushd video\remotion
    call npm install --no-audit --no-fund
    popd
    if not exist "video\remotion\node_modules" (
      echo [WARN] npm install failed in video\remotion. Run it there by hand to see the error.
    )
  ) else (
    echo [INFO] Remotion renderer already installed.
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
  echo      This window stays open so you can review the log. Press any key to close it.
  pause >nul
) else (
  echo [OK] Server starting in a new window.
  pause
)

@echo off
REM Shoestring Studios 2 - one-click start.
REM Sets up .venv, installs requirements.txt when it changed, then starts the Shoestring site
REM (http://localhost:8000). The site starts nextop studio itself on an internal port; use only port 8000.
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

set PY=python
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ first: https://www.python.org/downloads/
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
  echo [WARN] .env missing. The site loads, but the crew needs the keys in .env.example
  echo        ^(LOCAL_LLM_API_KEY for the LLM, MODEL_API_KEY for Gene's pictures, ...^).
  echo.
)

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

REM ---- install requirements.txt only when it changed (hash kept in .venv\requirements.sha) ----
set NEWHASH=
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "requirements.txt" SHA256 2^>nul') do (
  if not defined NEWHASH set "NEWHASH=%%H"
)
set OLDHASH=
if exist ".venv\requirements.sha" set /p OLDHASH=<".venv\requirements.sha"
if "%NEWHASH%"=="" set OLDHASH=FORCE-INSTALL
if "%NEWHASH%"=="%OLDHASH%" (
  echo [INFO] Dependencies unchanged, skipping install.
) else (
  echo [INFO] Installing requirements.txt into .venv...
  "%VENVPY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
  )
  if not "%NEWHASH%"=="" (echo %NEWHASH%)>".venv\requirements.sha"
)

REM ---- the narrator's voice (Kokoro): requirements-voice.txt, once ----
if not exist ".venv\voice.ok" (
  echo [INFO] Installing the voice packages ^(requirements-voice.txt, torch CPU^)...
  "%VENVPY%" -m pip install -r requirements-voice.txt
  if errorlevel 1 (
    echo [ERROR] Voice packages failed to install.
    pause
    exit /b 1
  )
  (echo ok)>".venv\voice.ok"
)

REM ---- the slide renderer (Remotion): npm install in remotion\, once ----
if not exist "remotion\node_modules\@remotion\cli" (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Node.js ^(npm^) is not installed: get it from https://nodejs.org and run this again.
    pause
    exit /b 1
  )
  echo [INFO] Installing the slide renderer ^(npm install in remotion^)...
  pushd remotion
  call npm install
  if errorlevel 1 (
    popd
    echo [ERROR] npm install failed.
    pause
    exit /b 1
  )
  popd
)

REM ---- the Shoestring site ----
start "" "http://localhost:8000/"
"%VENVPY%" scripts\server.py --port 8000
pause

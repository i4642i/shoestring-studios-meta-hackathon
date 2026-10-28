@echo off
REM Shoestring Studios - one-click git repo setup.
REM Double-click this file: init repo (if needed), stage everything
REM allowed by .gitignore, and create the initial commit.
setlocal
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] git is not installed. Install Git for Windows first:
  echo   https://git-scm.com/download/win
  pause
  exit /b 1
)

if not exist ".git" (
  git init -b main >nul 2>nul
  if errorlevel 1 git init
  echo [OK] repo initialized.
) else (
  echo [OK] .git already exists, reusing it.
)

git check-ignore -q .env
if errorlevel 1 (
  echo [ERROR] .env is NOT ignored. Refusing to commit secrets.
  echo Add ".env" to .gitignore first.
  pause
  exit /b 1
)

git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Initial commit: Shoestring Studios (Meta Global AI Developer Hackathon 2026)"
  echo [OK] initial commit created.
) else (
  echo [OK] nothing new to commit.
)

echo.
echo ---- next: publish to GitHub ----
echo   1. Create an EMPTY public repo on github.com (no README, no license).
echo   2. git remote add origin https://github.com/YOU/REPO.git
echo   3. git branch -M main
echo   4. git push -u origin main
echo.
git log --oneline -3
pause

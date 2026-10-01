@echo off
title Auto Video AI - Setup
echo ================================
echo  Auto Video AI - First-time setup
echo ================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found!
  echo Please install Python 3.10 or newer from https://www.python.org/downloads/
  echo IMPORTANT: tick "Add python.exe to PATH" during install.
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [INFO] FFmpeg not found - trying to install via winget...
  winget install ffmpeg 2>nul
  echo If that failed, install manually from https://ffmpeg.org/download.html
) else (
  echo [OK] FFmpeg found
)

echo [INFO] Installing Python packages (2-5 minutes)...
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist .env (
  copy .env.example .env >nul
  echo [OK] Created .env from template - add API keys later if you want AI video
)

echo [INFO] Installing Playwright browser for Flow bridge (one-time)...
python -m playwright install chromium
if errorlevel 1 echo [WARN] Playwright browser skipped - Flow bridge needs: python -m playwright install chromium

echo.
echo ================================
echo  DONE! Now double-click run_windows.bat to start!
echo ================================
pause

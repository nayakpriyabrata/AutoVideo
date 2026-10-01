@echo off
title Flow Chrome (remote debugging)
echo ============================================================
echo  Starting Chrome with remote debugging on 127.0.0.1:9222...
echo  Uses a DEDICATED profile (flow-chrome) so your main
echo  Chrome keeps running untouched. Log into Google once here.
echo  (Chrome 136+ requires a non-default profile for remote
echo   debugging - that is why we use a separate folder.)
echo ============================================================
set PROF=%LOCALAPPDATA%\AutoVideoAI\flow-chrome
if not exist "%PROF%" mkdir "%PROF%"
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="%PROF%" https://labs.google/fx
echo.
echo Chrome launched. In the app: SETTINGS -^> Browser mode = cdp,
echo CDP URL = http://127.0.0.1:9222 -^> Save. Then FLOW SESSION -^> Open Flow.
echo (WSL users: 'auto' mode finds this automatically - no URL needed.)
echo Keep this Chrome window open while generating.
echo.
echo Verifying the debug port - waiting 6s for Chrome to start...
timeout /t 6 /nobreak >nul
curl -s -m 5 http://127.0.0.1:9222/json/version >nul
if errorlevel 1 (
  echo [FAIL] Chrome is NOT listening on 127.0.0.1:9222
  echo Close ALL Chrome windows and run this file again. Still failing?
  echo Run check-cdp.bat and share its output.
) else (
  echo [OK] Chrome debug port is live on Windows.
  echo Now test from WSL: curl http://127.0.0.1:9222/json/version
  echo Expect the same JSON. If refused: mirrored-network/firewall issue.
)
pause

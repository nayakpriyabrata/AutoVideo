@echo off
title AutoVideoAI - CDP check on Windows side
echo === 1. Chrome debug endpoint on Windows localhost ===
curl -s -m 5 http://127.0.0.1:9222/json/version
echo.
echo.
echo === 2. What is listening on port 9222? ===
netstat -ano | findstr :9222
echo.
echo === 3. Any Chrome running WITH the debug flag? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | ForEach-Object { $_.CommandLine }"
echo.
echo Look for --remote-debugging-port=9222 above. Absent = flag was ignored,
echo usually because Chrome was already running - close ALL Chrome windows,
echo then run chrome-debug.bat again.
echo.
echo === 4. WSL version - mirrored networking needs Store WSL 2.x ===
wsl --version
echo.
echo === 5. .wslconfig contents ===
type "%USERPROFILE%\.wslconfig"
echo.
echo === Paste sections 1-5 when asking for help ===
pause

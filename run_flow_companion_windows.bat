@echo off
cd /d %~dp0
start "AutoVideoAI Bridge" cmd /k python -m engine.bridge.server
start "AutoVideoAI Dashboard" cmd /k python -m streamlit run app.py
start "" "https://labs.google/fx/tools/flow"
echo.
echo Bridge + dashboard launched. Make sure the unpacked AutoVideoAI Flow Companion extension is enabled in Chrome.
pause

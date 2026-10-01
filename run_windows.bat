@echo off
title Auto Video AI - Dashboard
echo Starting Auto Video AI... open http://localhost:8501 in your browser
python -m streamlit run app.py --server.headless=true --browser.gatherUsageStats=false
pause

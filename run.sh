#!/bin/bash
# Auto Video AI - launcher (Mac / Linux / WSL)
cd "$(dirname "$0")"
echo "Starting Auto Video AI... open http://localhost:8501 in your browser"
python3 -m streamlit run app.py --server.headless=true --browser.gatherUsageStats=false

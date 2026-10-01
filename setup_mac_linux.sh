#!/bin/bash
# Auto Video AI - first-time setup (Mac / Linux)
set -e
cd "$(dirname "$0")"

echo "================================"
echo " Auto Video AI - First-time setup"
echo "================================"

if ! command -v python3 &>/dev/null; then
  echo "[ERROR] python3 not found. Install Python 3.10+ first."
  exit 1
fi

if ! command -v ffmpeg &>/dev/null; then
  echo "[INFO] FFmpeg not found."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Install it with: brew install ffmpeg"
  else
    echo "Install it with: sudo apt install ffmpeg"
  fi
  echo "Continuing anyway (imageio-ffmpeg fallback may cover it)..."
else
  echo "[OK] FFmpeg found"
fi

echo "[INFO] Installing Python packages (2-5 minutes)..."
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt || python3 -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[OK] Created .env from template"
fi

# Fix PATH for --user installs (pip puts streamlit in ~/.local/bin)
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
  export PATH="$HOME/.local/bin:$PATH"
  grep -q '.local/bin' ~/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  grep -q '.local/bin' ~/.zshrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc 2>/dev/null || true
  echo "[OK] Added ~/.local/bin to PATH (restart terminal for it to stick)"
fi

echo "[INFO] Installing Playwright browser for Flow bridge (one-time, ~150MB)..."
python3 -m playwright install chromium 2>&1 | tail -3
test ${PIPESTATUS[0]} -eq 0 && echo "[OK] Playwright browser ready" || echo "[WARN] Browser download had issues - the app can still use YOUR system Chrome instead (see FLOW_SETUP.md)."

chmod +x run.sh

echo ""
echo "================================"
echo " DONE! Start with:"
echo "   ./run.sh"
echo " then open http://localhost:8501"
echo "================================"

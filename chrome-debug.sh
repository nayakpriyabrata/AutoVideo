#!/bin/bash
# Launch Chrome/Chromium with remote debugging for CDP attach (port 9222).
# Uses a separate profile dir so your main browser is untouched.
set -e
PROF="$HOME/flow-chrome"
mkdir -p "$PROF"
BIN="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"
"$BIN" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="$PROF" https://labs.google/fx &
echo "Chrome launched with CDP on :9222 (profile: $PROF)"
echo "App: SETTINGS -> Browser mode = cdp, CDP URL = http://localhost:9222"

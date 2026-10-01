"""Background music selection/downloading for YouTube productions.

Priority:
  1. user/local assets/music (zero network, most reliable)
  2. optional browser-assisted Pixabay public music search (no API key)

Browser downloading is deliberately isolated in a subprocess so it can never
poison Gemini/Flow Playwright lifecycle state.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from .sound_design import pick_music


def ensure_background_music(mood: str, workdir: str, mode: str = "auto") -> dict:
    mode = str(mode or "auto").lower()
    if mode == "off":
        return {"path": None, "source": "off"}
    local = pick_music(mood)
    if local:
        return {"path": local, "source": "local", "license": "user-supplied/local"}
    if mode == "local":
        return {"path": None, "source": "local", "error": "no local music asset"}

    os.makedirs(workdir, exist_ok=True)
    out = os.path.join(workdir, "background_music.mp3")
    cmd = [sys.executable, "-m", "engine.providers.web_media_helper",
           "music", "--query", mood or "soft motivational ambient instrumental",
           "--out", out]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if cp.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 30000:
            meta = {"path": out, "source": "pixabay-browser", "license": "Pixabay Content License"}
            try:
                last = (cp.stdout or "").strip().splitlines()[-1]
                meta.update(json.loads(last))
            except Exception:
                pass
            return meta
        return {"path": None, "source": "pixabay-browser", "error": (cp.stderr or cp.stdout or "browser music lookup failed")[-500:]}
    except Exception as e:
        return {"path": None, "source": "pixabay-browser", "error": str(e)[:500]}

"""Optional local/Pixabay background music for local video productions.

Browser-assisted Pixabay search is isolated in a subprocess so it cannot share
Gemini/Flow Playwright state. Downloaded media is accompanied by public source
provenance and a SHA-256; users should still review the item page and current
terms rather than treating a provider label as legal clearance.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from .sound_design import pick_music

PIXABAY_LICENSE_URL = "https://pixabay.com/service/license-summary/"


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_background_music(mood: str, workdir: str, mode: str = "auto") -> dict:
    """Find one local or Pixabay track; never silently substitute on failure.

    ``mode='pixabay'`` always performs a fresh Internet search, even if a local
    music library exists. ``auto`` retains the legacy local-first behavior.
    ``local`` only inspects the configured local library; ``off`` returns no
    track.
    """
    mode = str(mode or "auto").strip().lower()
    if mode == "off":
        return {"path": None, "source": "off"}
    if mode not in {"auto", "local", "pixabay", "browser", "internet"}:
        raise ValueError("Music source must be auto, local, pixabay, or off.")

    local = pick_music(mood) if mode in {"auto", "local"} else None
    if local:
        return {
            "path": os.path.abspath(local),
            "source": "local-library",
            "license": "User-supplied/local; verify its licence",
            "page_url": "",
            "creator": "",
            "query": str(mood or "")[:180],
            "sha256": _sha256(local),
            "provenance_note": "Local library track; AutoVideoAI does not verify its publication rights.",
        }
    if mode == "local":
        return {"path": None, "source": "local-library", "error": "no local music asset"}

    os.makedirs(workdir, exist_ok=True)
    query = str(mood or "soft ambient instrumental").strip()[:180] or "soft ambient instrumental"
    # A unique path prevents a failed new lookup from accidentally reusing a
    # prior track with an unrelated mood/query.
    out = os.path.join(workdir, f"background_music-{time.time_ns()}.mp3")
    cmd = [sys.executable, "-m", "engine.providers.web_media_helper",
           "music", "--query", query, "--out", out]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if cp.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 30000:
            meta = {}
            try:
                meta = json.loads((cp.stdout or "").strip().splitlines()[-1])
            except Exception:
                meta = {}
            page_url = str(meta.get("page_url") or meta.get("source_page") or "")[:500]
            media_meta = {
                "path": os.path.abspath(out),
                "source": str(meta.get("source") or "pixabay-browser")[:80],
                "license": str(meta.get("license") or "Pixabay Content License")[:180],
                "license_url": PIXABAY_LICENSE_URL,
                "page_url": page_url,
                "creator": str(meta.get("creator") or "")[:160],
                "asset_name": str(meta.get("asset_name") or "")[:160],
                "asset_id": str(meta.get("asset_id") or "")[:100],
                "query": str(meta.get("query") or query)[:180],
                "sha256": _sha256(out),
                "provenance_note": "Review the exact item page and current terms; this is not a guarantee of copyright clearance.",
            }
            # The helper's temporary sidecar contains a raw CDN media URL; it
            # is not needed after download. Keep public item-page provenance.
            try:
                os.remove(out + ".source.json")
            except OSError:
                pass
            return media_meta

        # Do not expose subprocess output verbatim: it may contain signed media
        # URLs. This actionable message includes no request credentials.
        try:
            if os.path.isfile(out):
                os.remove(out)
        except OSError:
            pass
        return {
            "path": None,
            "source": "pixabay-browser",
            "error": "No downloadable Pixabay music was found. Check Internet/browser access and try a more concrete soft-instrumental search term.",
        }
    except Exception as exc:
        try:
            if os.path.isfile(out):
                os.remove(out)
        except OSError:
            pass
        return {
            "path": None,
            "source": "pixabay-browser",
            "error": f"Pixabay music search failed ({type(exc).__name__}). Check Internet/browser dependencies or use a local track.",
        }

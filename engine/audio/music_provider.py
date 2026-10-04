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


_SEARCH_ERRORS = {
    "playwright_missing": (
        "Playwright is not installed in the Python environment running Streamlit. "
        "Install requirements.txt, then retry or choose a local music file."),
    "browser_install_missing": (
        "Playwright Chromium is not installed in this WSL environment. Run "
        "`python -m playwright install chromium` with the same Python used by Streamlit, then retry."),
    "browser_launch_failed": (
        "Chromium could not start for the Pixabay search. Check the WSL browser dependencies "
        "or set AUTOVIDEO_MEDIA_BROWSER_VISIBLE=1 to inspect the browser, then retry."),
    "pixabay_unreachable": (
        "Pixabay could not be reached from this WSL session. Check Internet/proxy access and retry."),
    "no_track_results": (
        "Pixabay loaded, but no music item pages were found for this search. Try a concrete term "
        "such as soft piano background music, or use a local file."),
    "no_audio_media": (
        "Pixabay track pages loaded, but their audio preview/download was unavailable. "
        "Try AUTOVIDEO_MEDIA_BROWSER_VISIBLE=1 or choose a local file."),
    "download_rejected": (
        "Pixabay returned links, but they were not valid downloadable audio. "
        "Check network restrictions or choose a local file."),
    "browser_failed": (
        "The isolated Pixabay browser search did not complete. Check WSL network/browser setup "
        "or choose a local file."),
    "browser_timeout": (
        "Pixabay music search exceeded its bounded four-minute limit. Check browser/network access "
        "or choose a local file."),
}


def _safe_browser_search_error(stderr: str) -> str:
    """Translate only helper status codes; never echo signed URLs or raw stderr."""
    prefix = "AUTOVIDEO_MEDIA_SEARCH="
    for line in str(stderr or "").splitlines():
        line = line.strip()
        if line.startswith(prefix):
            code = line[len(prefix):].strip()
            return _SEARCH_ERRORS.get(code, _SEARCH_ERRORS["browser_failed"])
    return _SEARCH_ERRORS["browser_failed"]


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
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
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

        # Translate only the helper's allowlisted status code. Never echo its
        # raw output: transport errors can contain signed media URLs.
        error = _safe_browser_search_error(cp.stderr)
        for path in (out, out + ".part", out + ".source.json"):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        return {"path": None, "source": "pixabay-browser", "error": error}
    except subprocess.TimeoutExpired:
        error = _SEARCH_ERRORS["browser_timeout"]
    except Exception as exc:
        error = f"Pixabay music search failed ({type(exc).__name__}). Check WSL browser dependencies or use a local track."
    for path in (out, out + ".part", out + ".source.json"):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
    return {"path": None, "source": "pixabay-browser", "error": error}

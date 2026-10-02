"""
Free Stock Motion Footage (no watermark, commercial use OK)
1. Pexels Video API (free key, generous limits) <- best
2. Pixabay Video API (free key) <- fallback
Get keys: pexels.com/api (instant) | pixabay.com/api/docs (instant)
"""
import os
import json
import subprocess
import sys
import requests
import re


def _pick_pexels_file(files: list, vertical: bool):
    """Pick file closest to target aspect, >=480p."""
    target = 9 / 16 if vertical else 16 / 9
    best, best_score = None, None
    for f in files:
        w, h = f.get("width") or 0, f.get("height") or 0
        if not w or not h or h < 400 or not f.get("link"):
            continue
        score = (abs(w / h - target), -h)
        if best_score is None or score < best_score:
            best, best_score = f, score
    return best


def _pexels_clip(query: str, vertical: bool, used_ids: set):
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/v1/videos/search",
            headers={"Authorization": key},
            params={"query": query, "orientation": "portrait" if vertical else "landscape",
                    "per_page": 6, "size": "medium"},
            timeout=25,
        )
        if r.status_code != 200:
            print(f"Pexels stock search returned HTTP {r.status_code}.")
            return None
        for v in r.json().get("videos", []):
            if v.get("id") in used_ids:
                continue
            f = _pick_pexels_file(v.get("video_files", []), vertical)
            if f:
                used_ids.add(v.get("id"))
                return {"url": f["link"], "source": "pexels-api",
                        "asset_id": v.get("id"), "page_url": v.get("url", ""),
                        "creator": ((v.get("user") or {}).get("name") or "")}
    except Exception as e:
        # Exception strings can contain request URLs/headers; keep credentials
        # out of logs and surface a generic search failure instead.
        print(f"Pexels stock search failed ({type(e).__name__}).")
    return None


def _pixabay_clip(query: str, vertical: bool, page: int, used_ids=None):
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        return None
    try:
        r = requests.get("https://pixabay.com/api/videos/",
                         params={"key": key, "q": query,
                                 "orientation": "vertical" if vertical else "horizontal",
                                 "per_page": 5, "page": page, "safesearch": "true"},
                         timeout=25)
        if r.status_code != 200:
            return None
        for v in r.json().get("hits", []):
            if v.get("id") in (used_ids or set()):
                continue
            vs = v.get("videos", {})
            for q in ("large", "medium", "small"):
                if q in vs and vs[q].get("url"):
                    return {"url": vs[q]["url"], "source": "pixabay-api",
                            "asset_id": v.get("id"), "page_url": v.get("pageURL", ""),
                            "creator": v.get("user", "")}
    except Exception as e:
        # Requests exceptions may echo Pixabay's API-key query parameter.
        print(f"Pixabay stock search failed ({type(e).__name__}).")
    return None


def _download(url: str, path: str) -> bool:
    try:
        r = requests.get(url, timeout=180, stream=True)
        r.raise_for_status()
        with open(path, "wb") as f:
            for ch in r.iter_content(65536):
                f.write(ch)
        return os.path.getsize(path) > 50000
    except Exception as e:
        # Signed media URLs are not useful diagnostics and can contain tokens.
        print(f"Stock media download failed ({type(e).__name__}).")
        return False


def _browser_clip(query: str, workdir: str, idx: int) -> tuple[str | None, dict]:
    out = os.path.join(workdir, f"stock{idx:02d}_browser.mp4")
    cmd = [sys.executable, "-m", "engine.providers.web_media_helper",
           "stock", "--query", query, "--out", out]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if cp.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 50000:
            meta = {"source": "browser-stock", "query": query}
            try:
                meta.update(json.loads((cp.stdout or "").strip().splitlines()[-1]))
            except Exception:
                pass
            return out, meta
        detail = (cp.stderr or cp.stdout or "").strip()
        if "No downloadable stock media found" in detail:
            reason = "No downloadable matching stock video was found by the browser search."
        else:
            reason = "Browser stock search did not complete; check network access and browser dependencies."
        return None, {"source": "browser-stock", "error": reason}
    except Exception as e:
        return None, {"source": "browser-stock",
                      "error": f"Browser stock search failed ({type(e).__name__}); check network access and browser dependencies."}


def get_stock_videos(scenes: list, topic: str, workdir: str, vertical: bool = True,
                     source_mode: str = "auto", excluded_assets: dict | None = None) -> dict:
    """Fetch one stock-motion clip per scene.

    source_mode: auto/local handled by StockProvider, api, browser, or auto.
    API calls are attempted first when free Pexels/Pixabay keys are configured;
    the browser helper is a no-key best-effort fallback and runs out-of-process.
    """
    os.makedirs(workdir, exist_ok=True)
    mode = str(source_mode or "auto").lower()
    allow_api = mode in ("auto", "api")
    allow_browser = mode in ("auto", "browser")
    clips, used, src, metadata, errors = [], set(), set(), [], []
    used.update((excluded_assets or {}).get("pexels-api", []))
    used_pixabay = set((excluded_assets or {}).get("pixabay-api", []))
    for i, scene in enumerate(scenes):
        # Stock search is not an image-generation prompt. Preserve Unicode
        # terms and concrete nouns; style filler made generic landscapes win.
        q = " ".join(re.findall(r"[^\W_]+", str(scene or topic), flags=re.UNICODE))[:180]
        q = q.strip() or "nature city technology people"
        out = os.path.join(workdir, f"stock{i:02d}.mp4")
        candidate = None
        if allow_api:
            candidate = _pexels_clip(q, vertical, used)
            if not candidate:
                candidate = _pixabay_clip(q, vertical, page=(i % 3) + 1, used_ids=used_pixabay)
                if candidate:
                    used_pixabay.add(candidate.get("asset_id"))
        if candidate and _download(candidate.get("url", ""), out):
            from_src = str(candidate.get("source") or "stock-api")
            clips.append(out); src.add(from_src)
            meta = {"path": out, "query": q, "media_url": candidate.get("url", ""),
                    "license": "Pexels License" if from_src.startswith("pexels") else "Pixabay Content License",
                    **candidate}
            metadata.append(meta)
            try:
                with open(out + ".source.json", "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass
            continue
        if candidate:
            candidate = None
        if allow_browser:
            bp, meta = _browser_clip(q, workdir, i)
            if bp:
                clips.append(bp); src.add(str(meta.get("source") or "browser-stock")); metadata.append(meta)
                continue
            errors.append(str(meta.get("error") or "Browser stock search found no usable video."))
        if not candidate:
            if mode == "local":
                errors.append("No matching local stock video; add a keyword-named clip to the stock library or choose an Internet source.")
            elif mode == "api":
                errors.append("No matching API stock video; check PEXELS_API_KEY/PIXABAY_API_KEY and network access.")
            elif not allow_browser:
                errors.append("No matching stock video was found; check stock source settings and network access.")
            else:
                errors.append("No matching downloadable stock video was found; check network access or add a relevant local stock clip.")
        # No implicit reuse: a missing scene must get an explicit skip/retry.
    return {"clips": clips, "source": "+".join(sorted(src)) or "none",
            "metadata": metadata, "errors": errors}

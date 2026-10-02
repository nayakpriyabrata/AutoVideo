"""Isolated browser helper for searching public stock-video/music candidates.

This module is run as a subprocess. It intentionally does not share Playwright
objects with Gemini or Flow. API providers remain preferred when keys exist;
this is a best-effort no-key fallback for the user's own browser environment.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from urllib.parse import quote
import requests


def _extract_media_urls(page, kind: str) -> list[str]:
    script = r"""
    (kind) => {
      const out = [];
      const add = (u) => { if (u && typeof u === 'string' && !out.includes(u)) out.push(u); };
      if (kind === 'stock') {
        document.querySelectorAll('video').forEach(v => {
          add(v.currentSrc); add(v.src);
          v.querySelectorAll('source').forEach(s => add(s.src));
        });
      } else {
        document.querySelectorAll('audio').forEach(a => {
          add(a.currentSrc); add(a.src);
          a.querySelectorAll('source').forEach(s => add(s.src));
        });
        document.querySelectorAll('a[href]').forEach(a => {
          const h = a.href || '';
          if (/\.mp3(\?|$)/i.test(h) || /audio.*download/i.test(h)) add(h);
        });
      }
      try {
        performance.getEntriesByType('resource').forEach(e => {
          const u = e.name || '';
          if (kind === 'stock' && (/\.mp4(\?|$)/i.test(u) || /video/i.test(u))) add(u);
          if (kind === 'music' && (/\.mp3(\?|$)/i.test(u) || /audio/i.test(u))) add(u);
        });
      } catch (_) {}
      return out;
    }
    """
    try:
        urls = page.evaluate(script, kind) or []
    except Exception:
        urls = []
    clean = []
    for u in urls:
        if not isinstance(u, str) or not u.startswith("http"):
            continue
        lu = u.lower()
        if kind == "stock" and (".mp4" in lu or "video" in lu) and ".m3u8" not in lu:
            clean.append(u)
        elif kind == "music" and (".mp3" in lu or "audio" in lu) and ".m3u8" not in lu:
            clean.append(u)
    return clean


def _download(url: str, out: str, referer: str) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
        "Referer": referer,
    }
    try:
        with requests.get(url, headers=headers, stream=True, timeout=90, allow_redirects=True) as r:
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if "text/html" in ctype:
                return False
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, "wb") as f:
                for chunk in r.iter_content(128 * 1024):
                    if chunk:
                        f.write(chunk)
        return os.path.isfile(out) and os.path.getsize(out) > 30000
    except Exception:
        return False


def _page_metadata(page) -> dict:
    """Best-effort visible item/creator metadata; do not retain media URL fields."""
    result = {}
    try:
        heading = page.locator("h1").first
        if heading.count() and heading.is_visible(timeout=500):
            result["asset_name"] = (heading.inner_text(timeout=1000) or "").strip()[:160]
    except Exception:
        pass
    try:
        links = page.locator("a[href*='/users/']")
        for index in range(min(links.count(), 10)):
            link = links.nth(index)
            if link.is_visible(timeout=200):
                name = (link.inner_text(timeout=500) or "").strip()
                if name and len(name) <= 160:
                    result["creator"] = name
                    break
    except Exception:
        pass
    return result


def run(kind: str, query: str, out: str) -> dict:
    from playwright.sync_api import sync_playwright
    profile = os.path.expanduser("~/.local/share/autovideoai/stock-media-profile")
    os.makedirs(profile, exist_ok=True)
    sources = []
    if kind == "stock":
        sources = [
            ("pexels-browser", f"https://www.pexels.com/search/videos/{quote(query)}/", "Pexels License"),
            ("pixabay-browser", f"https://pixabay.com/videos/search/{quote(query)}/", "Pixabay Content License"),
        ]
    else:
        sources = [
            ("pixabay-browser", f"https://pixabay.com/music/search/{quote(query)}/", "Pixabay Content License"),
        ]
    visible = os.getenv("AUTOVIDEO_MEDIA_BROWSER_VISIBLE", "0").strip().lower() in {"1", "true", "yes"}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, headless=not visible,
                                                   viewport={"width": 1440, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            for source, url, license_name in sources:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(4500)
                    # Start one visible media item so lazy sources become concrete.
                    if kind == "stock":
                        try:
                            page.locator("video").first.hover(timeout=2000)
                        except Exception:
                            pass
                    else:
                        # Pixabay often exposes the actual audio only on the item page.
                        if not _extract_media_urls(page, kind):
                            for sel in ("a[href*='/music/']", "a[href*='/sound-effects/']"):
                                try:
                                    href = page.locator(sel).nth(1).get_attribute("href", timeout=2500)
                                    if href and "/music/search/" not in href:
                                        if href.startswith("/"):
                                            href = "https://pixabay.com" + href
                                        page.goto(href, wait_until="domcontentloaded", timeout=30000)
                                        page.wait_for_timeout(2500)
                                        break
                                except Exception:
                                    continue
                    urls = _extract_media_urls(page, kind)
                    # Prefer explicit file extensions/CDN media first.
                    urls.sort(key=lambda u: (0 if re.search(r"\.(mp4|mp3)(\?|$)", u, re.I) else 1, len(u)))
                    for media_url in urls[:12]:
                        if _download(media_url, out, page.url):
                            meta = {"path": out, "source": source, "query": query,
                                    "source_page": page.url, "page_url": page.url,
                                    "media_url": media_url, **_page_metadata(page),
                                    "license": license_name, "downloaded_at": int(time.time())}
                            with open(out + ".source.json", "w", encoding="utf-8") as f:
                                json.dump(meta, f, indent=2)
                            return meta
                except Exception:
                    continue
        finally:
            ctx.close()
    raise RuntimeError(f"No downloadable {kind} media found via browser for query: {query}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["stock", "music"])
    ap.add_argument("--query", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        meta = run(a.kind, a.query, a.out)
        print(json.dumps(meta, ensure_ascii=False))
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()

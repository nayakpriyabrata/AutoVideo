"""Isolated browser helper for searching public stock-video/music candidates.

This module is run as a subprocess. It intentionally does not share Playwright
objects with Gemini or Flow. Media is downloaded only from the expected stock
provider domains, checked by content type/signature, and accompanied by public
source-page provenance. Provider errors are reduced to safe status codes; signed
media URLs and browser profile data are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import quote, unquote, urljoin, urlsplit

import requests

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".opus")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov")
MAX_AUDIO_BYTES = 100 * 1024 * 1024
MAX_VIDEO_BYTES = 300 * 1024 * 1024


class MediaSearchError(RuntimeError):
    """Search failure with a non-sensitive code suitable for the parent UI."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _allowed_media_host(url: str, kind: str) -> bool:
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.username or parts.password:
            return False
        host = (parts.hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return False
    roots = ("pixabay.com",) if kind == "music" else ("pixabay.com", "pexels.com")
    return any(host == root or host.endswith("." + root) for root in roots)


def _looks_like_media_url(url: str, kind: str) -> bool:
    try:
        parts = urlsplit(url)
        candidate = unquote(parts.path + "?" + parts.query).lower()
    except (TypeError, ValueError):
        return False
    if re.search(r"\.(?:jpe?g|png|gif|webp|svg|m3u8|html?)(?:$|[?#&])", candidate):
        return False
    extensions = AUDIO_EXTENSIONS if kind == "music" else VIDEO_EXTENSIONS
    return any(re.search(re.escape(ext) + r"(?:$|[?#&])", candidate) for ext in extensions)


def _extract_media_urls(page, kind: str) -> list[str]:
    """Extract direct media only; audio thumbnails under /audio/ are not tracks."""
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
          if (/\.(mp3|m4a|wav|ogg|aac|flac|opus)(?:[?#&]|$)/i.test(h) || /\/download\/audio(?:[/?#]|$)/i.test(h)) add(h);
        });
        document.querySelectorAll('meta[property="og:audio"], meta[name="og:audio"]').forEach(m => add(m.content));
      }
      try {
        performance.getEntriesByType('resource').forEach(e => {
          const u = e.name || '';
          if (kind === 'stock' && /\.(mp4|webm|mov)(?:[?#]|$)/i.test(u)) add(u);
          if (kind === 'music' && /\.(mp3|m4a|wav|ogg|aac|flac|opus)(?:[?#]|$)/i.test(u)) add(u);
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
    for url in urls:
        if (isinstance(url, str) and _allowed_media_host(url, kind)
                and _looks_like_media_url(url, kind) and url not in clean):
            clean.append(url)
    return clean


def _music_result_pages(page, limit: int = 6) -> list[str]:
    """Collect concrete Pixabay music-item pages, not generic search/tag links."""
    try:
        hrefs = page.locator("a[href*='/music/']").evaluate_all(
            "els => els.map(el => el.href || el.getAttribute('href') || '')") or []
    except Exception:
        hrefs = []
    pages = []
    ignored = {"search", "genre", "mood", "theme", "movement", "users", "collections"}
    for href in hrefs:
        if not isinstance(href, str):
            continue
        full = urljoin("https://pixabay.com/", href)
        try:
            parts = urlsplit(full)
            pieces = [piece for piece in parts.path.split("/") if piece]
        except ValueError:
            continue
        if (not _allowed_media_host(full, "music") or len(pieces) < 2
                or pieces[0] != "music" or pieces[1].lower() in ignored
                or "/search/" in parts.path.lower()):
            continue
        # Pixabay item routes include the numeric asset ID in their slug.
        if not re.search(r"-\d+(?:/|$)", parts.path):
            continue
        canonical = f"https://{parts.netloc}{parts.path}"
        if canonical not in pages:
            pages.append(canonical)
        if len(pages) >= max(1, min(int(limit), 10)):
            break
    return pages


def _looks_like_audio_file(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            data = handle.read(8192)
    except OSError:
        return False
    if data.startswith((b"ID3", b"fLaC", b"OggS")):
        return True
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return True
    # MP3 without an ID3 tag starts with MPEG sync; scan a small bounded prefix.
    return any(data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0
               for i in range(max(0, len(data) - 1)))


def _looks_like_video_file(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            data = handle.read(16)
    except OSError:
        return False
    return len(data) >= 8 and (data[4:8] == b"ftyp" or data.startswith(b"\x1aE\xdf\xa3")
                               or (data.startswith(b"RIFF") and data[8:12] == b"AVI "))


def _download(url: str, out: str, referer: str, kind: str = "stock") -> bool:
    """Download one bounded file; reject HTML, images, and mismatched payloads."""
    if kind not in {"music", "stock"} or not _allowed_media_host(url, kind):
        return False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
        "Referer": referer,
    }
    part = out + ".part"
    max_bytes = MAX_AUDIO_BYTES if kind == "music" else MAX_VIDEO_BYTES
    try:
        with requests.get(url, headers=headers, stream=True, timeout=(15, 60), allow_redirects=True) as response:
            response.raise_for_status()
            if not _allowed_media_host(response.url, kind):
                return False
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if kind == "music":
                valid_type = content_type.startswith("audio/") or content_type in {
                    "application/octet-stream", "binary/octet-stream"}
            else:
                valid_type = content_type.startswith("video/") or content_type in {
                    "application/octet-stream", "binary/octet-stream"}
            if not valid_type:
                return False
            try:
                content_length = int(response.headers.get("content-length") or 0)
            except (TypeError, ValueError):
                content_length = 0
            if content_length > max_bytes:
                return False
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            total = 0
            with open(part, "wb") as handle:
                for chunk in response.iter_content(128 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        return False
                    handle.write(chunk)
        if total <= 30000:
            return False
        if kind == "music" and not _looks_like_audio_file(part):
            return False
        if kind == "stock" and not _looks_like_video_file(part):
            return False
        os.replace(part, out)
        return True
    except Exception:
        return False
    finally:
        try:
            if os.path.isfile(part):
                os.remove(part)
        except OSError:
            pass


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


def _activate_player(page, kind: str) -> None:
    """Start a page's native preview so lazy media URLs become visible."""
    if kind == "stock":
        try:
            page.locator("video").first.hover(timeout=2000)
        except Exception:
            pass
        return
    selectors = (
        'button[aria-label*="play" i]', '[role="button"][aria-label*="play" i]',
        'button[title*="play" i]', 'button[data-testid*="play" i]',
        'button[aria-label*="listen" i]',
    )
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for index in range(min(loc.count(), 3)):
                button = loc.nth(index)
                if button.is_visible(timeout=300):
                    button.click(timeout=1200)
                    page.wait_for_timeout(700)
                    return
        except Exception:
            continue


def _dedupe_urls(urls: list[str], kind: str) -> list[str]:
    clean = []
    for url in urls:
        if not isinstance(url, str) or not _allowed_media_host(url, kind):
            continue
        if url not in clean:
            clean.append(url)
    # Prefer known media extensions. A response captured from an HTML audio
    # player may have no extension, so it remains a safe later candidate.
    clean.sort(key=lambda item: (0 if _looks_like_media_url(item, kind) else 1, len(item)))
    return clean[:16]


def _save_download_metadata(out: str, source: str, query: str, page_url: str,
                            license_name: str, page) -> dict:
    asset_match = re.search(r"-(\d+)(?:/|$)", urlsplit(page_url).path)
    meta = {"path": out, "source": source, "query": query,
            "source_page": page_url, "page_url": page_url,
            "asset_id": asset_match.group(1) if asset_match else "",
            **_page_metadata(page), "license": license_name,
            "downloaded_at": int(time.time())}
    with open(out + ".source.json", "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)
    return meta


def run(kind: str, query: str, out: str) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise MediaSearchError("playwright_missing") from exc

    profile = os.path.expanduser("~/.local/share/autovideoai/stock-media-profile")
    os.makedirs(profile, exist_ok=True)
    if kind == "stock":
        sources = [
            ("pexels-browser", f"https://www.pexels.com/search/videos/{quote(query, safe='')}/", "Pexels License"),
            ("pixabay-browser", f"https://pixabay.com/videos/search/{quote(query, safe='')}/", "Pixabay Content License"),
        ]
    else:
        sources = [
            ("pixabay-browser", f"https://pixabay.com/music/search/{quote(query, safe='')}/", "Pixabay Content License"),
        ]
    visible = os.getenv("AUTOVIDEO_MEDIA_BROWSER_VISIBLE", "0").strip().lower() in {"1", "true", "yes"}
    try:
        manager = sync_playwright()
        playwright = manager.start()
        try:
            ctx = playwright.chromium.launch_persistent_context(
                profile, headless=not visible,
                viewport={"width": 1440, "height": 900})
        except Exception as exc:
            if "executable" in str(exc).lower() and "doesn't exist" in str(exc).lower():
                raise MediaSearchError("browser_install_missing") from exc
            raise MediaSearchError("browser_launch_failed") from exc

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        response_media: list[str] = []

        def capture_media_response(response):
            try:
                content_type = (response.headers.get("content-type") or "").lower()
                expected = "audio/" if kind == "music" else "video/"
                if expected in content_type and _allowed_media_host(response.url, kind):
                    if response.url not in response_media:
                        response_media.append(response.url)
            except Exception:
                pass

        page.on("response", capture_media_response)
        track_pages_seen = 0
        search_pages_failed = 0
        media_links_seen = 0
        try:
            for source_name, search_url, license_name in sources:
                response_media.clear()
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3500)
                except Exception:
                    search_pages_failed += 1
                    continue

                if kind == "stock":
                    _activate_player(page, kind)
                    media_urls = _dedupe_urls(
                        _extract_media_urls(page, kind) + list(response_media), kind)
                    media_links_seen += len(media_urls)
                    for media_url in media_urls:
                        if _download(media_url, out, page.url, kind=kind):
                            return _save_download_metadata(
                                out, source_name, query, page.url, license_name, page)
                    continue

                item_pages = _music_result_pages(page, limit=6)
                if not item_pages:
                    continue
                track_pages_seen += len(item_pages)
                # Test at most three track pages per search. This keeps retries
                # bounded while avoiding dependence on a brittle nth-link guess.
                for item_url in item_pages[:3]:
                    response_media.clear()
                    try:
                        page.goto(item_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(1400)
                    except Exception:
                        continue
                    page_url = page.url
                    media_urls = _dedupe_urls(
                        _extract_media_urls(page, "music") + list(response_media), "music")
                    media_links_seen += len(media_urls)
                    for media_url in media_urls:
                        if _download(media_url, out, page_url, kind="music"):
                            return _save_download_metadata(
                                out, source_name, query, page_url, license_name, page)

                    _activate_player(page, "music")
                    page.wait_for_timeout(700)
                    media_urls = _dedupe_urls(
                        _extract_media_urls(page, "music") + list(response_media), "music")
                    media_links_seen += len(media_urls)
                    for media_url in media_urls:
                        if _download(media_url, out, page_url, kind="music"):
                            return _save_download_metadata(
                                out, source_name, query, page_url, license_name, page)
        finally:
            try:
                ctx.close()
            finally:
                manager.stop()
    except MediaSearchError:
        raise
    except Exception as exc:
        if "executable" in str(exc).lower() and "doesn't exist" in str(exc).lower():
            raise MediaSearchError("browser_install_missing") from exc
        raise MediaSearchError("browser_launch_failed") from exc

    if kind == "music":
        if search_pages_failed:
            raise MediaSearchError("pixabay_unreachable")
        if not track_pages_seen:
            raise MediaSearchError("no_track_results")
        if media_links_seen:
            raise MediaSearchError("download_rejected")
        raise MediaSearchError("no_audio_media")
    raise MediaSearchError("stock_not_found")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["stock", "music"])
    parser.add_argument("--query", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        meta = run(args.kind, args.query, args.out)
        print(json.dumps(meta, ensure_ascii=False))
    except MediaSearchError as exc:
        if args.kind == "music":
            print(f"AUTOVIDEO_MEDIA_SEARCH={exc.code}", file=sys.stderr)
        else:
            print("No downloadable stock media found via browser for this search.", file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        # Do not dump Playwright/network exception strings; they can contain
        # signed URLs or other transient transport details.
        if args.kind == "music":
            print("AUTOVIDEO_MEDIA_SEARCH=browser_failed", file=sys.stderr)
        else:
            print("Stock browser search failed; check network/browser dependencies.", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()

"""
Visuals - 100% FREE, no key required
1. Pollinations.ai text-to-image (free, unlimited, no key) <- default
2. Pexels stock photos (free tier, needs free key) <- optional upgrade
"""
import os
import re
import hashlib
import urllib.parse
import requests

VERTICAL = (720, 1280)    # 9:16 shorts
HORIZONTAL = (1280, 720)  # 16:9 youtube


def _keywords(scene_text: str, topic: str) -> str:
    """Extract a short image prompt from scene text."""
    stop = {"the", "this", "that", "with", "from", "your", "about", "into",
            "will", "they", "them", "then", "than", "have", "has", "are",
            "was", "were", "and", "for", "you", "our", "but", "not", "all"}
    words = re.findall(r"[a-zA-Z]{4,}", scene_text.lower())
    keys = [w for w in words if w not in stop][:6]
    base = " ".join(keys) if keys else topic
    return f"{base}, cinematic, high quality, vibrant"


def _pollinations_url(prompt: str, w: int, h: int, seed: int,
                      model: str | None = "flux") -> str:
    q = urllib.parse.quote(prompt[:180])
    url = (f"https://image.pollinations.ai/prompt/{q}"
           f"?width={w}&height={h}&seed={seed}&nologo=true")
    return url + (f"&model={model}" if model else "")


def _download(url: str, path: str, timeout: int = 90, quiet: bool = False) -> bool:
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "")
        if "image" not in ct and len(r.content) < 5000:
            return False
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return os.path.getsize(path) > 5000
    except Exception as e:
        if not quiet:
            print(f"download failed: {e}")
        return False


def _pollinations_with_retry(prompt: str, w: int, h: int, seed: int, out: str) -> bool:
    """Bounded retries for flaky free provider: 2x flux w/ backoff, then default model."""
    import time
    urls = [_pollinations_url(prompt, w, h, seed, "flux"),
            _pollinations_url(prompt, w, h, seed + 1, "flux"),
            _pollinations_url(prompt, w, h, seed + 2, None)]
    for i, url in enumerate(urls):
        if _download(url, out, quiet=(i < len(urls) - 1)):
            return True
        time.sleep(2 if i == 0 else 4)
    return False


def _placeholder_image(path: str, w: int, h: int, text: str):
    """Gradient placeholder so video NEVER fails (works offline)."""
    from PIL import Image, ImageDraw
    import random
    c1 = (random.randint(20, 80), random.randint(40, 100), random.randint(90, 160))
    c2 = (random.randint(100, 180), random.randint(40, 90), random.randint(120, 200))
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / h
        for x in range(0, w, 4):
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    d = ImageDraw.Draw(img)
    # simple centered text (wrapped)
    words, lines, cur = text.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) < 18:
            cur = (cur + " " + wd).strip()
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    y0 = h // 2 - len(lines) * 30
    for ln in lines[:8]:
        d.text((w // 2 - len(ln) * 9, y0), ln, fill=(255, 255, 255))
        y0 += 55
    img.save(path)


def _try_pexels(topic: str, count: int, orientation: str) -> list:
    """Return list of image urls from Pexels if key exists, else []."""
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": topic, "per_page": count, "orientation": orientation},
            timeout=20,
        )
        if r.status_code == 200:
            photos = r.json().get("photos", [])
            return [p["src"]["large"] for p in photos if "src" in p]
    except Exception as e:
        print(f"Pexels failed: {e}")
    return []


def get_visuals(scenes: list, topic: str, workdir: str,
                vertical: bool = True) -> dict:
    """
    Download/generate one image per scene.
    Returns {"images": [paths], "source": "pollinations"|"pexels"|"mixed"|"placeholder"}
    """
    os.makedirs(workdir, exist_ok=True)
    w, h = VERTICAL if vertical else HORIZONTAL
    orientation = "portrait" if vertical else "landscape"

    pexels_urls = _try_pexels(topic, len(scenes), orientation)
    images, sources = [], set()

    for i, scene in enumerate(scenes):
        out = os.path.join(workdir, f"scene{i:02d}.jpg")
        ok = False
        # 1) Pexels URL if available
        if i < len(pexels_urls):
            if _download(pexels_urls[i], out):
                ok = True
                sources.add("pexels")
        # 2) Pollinations AI image (free, no key) - retried before giving up
        if not ok:
            prompt = _keywords(scene, topic)
            seed = int(hashlib.md5((topic + str(i)).encode()).hexdigest()[:8], 16) % 999999
            if _pollinations_with_retry(prompt, w, h, seed, out):
                ok = True
                sources.add("pollinations")
        # 3) Offline placeholder (never fail)
        if not ok:
            _placeholder_image(out, w, h, scene[:120])
            sources.add("placeholder")
        images.append(out)

    if len(sources) == 1:
        src = list(sources)[0]
    else:
        src = "mixed"
    return {"images": images, "source": src}

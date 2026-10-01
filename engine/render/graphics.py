"""YouTube-style editorial graphics and branding overlays.

The graphics engine intentionally works from the *approved script/shot plan* and
renders transparent PNG overlays with Pillow. FFmpeg only has to composite PNGs,
which is far more reliable across WSL/Linux builds than complex drawtext chains.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, asdict
from typing import Iterable

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover
    Image = ImageDraw = ImageFont = None


ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
CARDINALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


@dataclass
class OverlayEvent:
    kind: str
    start: float
    end: float
    title: str = ""
    body: str = ""
    anchor: str = "center"
    opacity: float = 1.0
    path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _font_candidates(bold: bool = False) -> list[str]:
    base = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/mnt/c/Windows/Fonts/arialbd.ttf" if bold else "/mnt/c/Windows/Fonts/arial.ttf",
        "/mnt/c/Windows/Fonts/calibrib.ttf" if bold else "/mnt/c/Windows/Fonts/calibri.ttf",
    ]
    return [p for p in base if os.path.isfile(p)]


def _font(size: int, bold: bool = False):
    if ImageFont is None:
        return None
    for p in _font_candidates(bold):
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap(text: str, max_chars: int) -> list[str]:
    words = re.sub(r"\s+", " ", text or "").strip().split()
    if not words:
        return []
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        if cur and len(test) > max_chars:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def _short_phrase(text: str, max_words: int = 8) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    # Prefer first clause instead of slicing through a thought.
    t = re.split(r"[.!?;:]", t)[0].strip() or t
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words])
    return t.rstrip(",.- ")


def _section_number(text: str) -> int | None:
    low = (text or "").lower()
    m = re.search(r"\b(?:habit|step|tip|rule|lesson|mistake|reason)\s*#?\s*(\d{1,2})\b", low)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    for word, n in ORDINALS.items():
        if re.search(rf"\b{word}\b", low):
            return n
    m = re.search(r"\b(?:habit|step|tip|rule|lesson|mistake|reason|point|number)\s+"
                  r"(one|two|three|four|five|six|seven|eight|nine|ten)\b", low)
    if m:
        return CARDINALS.get(m.group(1))
    return None


def _section_title(text: str, n: int) -> str:
    title = re.sub(
        r"^(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
        r"(?:habit|step|tip|rule|lesson|mistake|reason|point|number)\s*(?:#?\d+|"
        r"one|two|three|four|five|six|seven|eight|nine|ten))[,\s:—-]+",
        "", str(text or "").strip(), flags=re.I)
    return _short_phrase(title, 9) or f"Point {n}"


def plan_overlays(manifest, script_data: dict, channel_name: str = "",
                  show_watermark: bool = True, max_keypoints: int = 6,
                  actual_duration: float | None = None) -> list[OverlayEvent]:
    """Create restrained YouTube-style overlays from the approved shot plan.

    The plan intentionally avoids turning every spoken sentence into text. It
    generates an opening promise, section cards for enumerated/list content,
    sparse key-point callouts, a persistent subtle watermark, and an outro CTA.
    """
    shots = list(getattr(manifest, "shots", []) or [])
    total = float(getattr(manifest, "target_seconds", 0) or 0)
    if shots:
        total = max(total, max(float(getattr(s, "voice_end", 0) or 0) for s in shots))
    if actual_duration is not None:
        total = max(0.0, float(actual_duration))
    topic = str(getattr(manifest, "topic", "") or "").strip()
    events: list[OverlayEvent] = []

    # Strong but brief hook/title card. Keep enough visual visible behind it.
    if total > 3 and topic:
        events.append(OverlayEvent("intro", 0.35, min(5.2, total), _short_phrase(topic, 10),
                                   "Watch to the end for the practical takeaway."))

    seen_sections: set[int] = set()
    section_events: list[OverlayEvent] = []
    for s in shots:
        narr = str(getattr(s, "narration", "") or "")
        n = _section_number(narr)
        if n is None or n in seen_sections:
            continue
        seen_sections.add(n)
        at = max(0.0, float(getattr(s, "voice_start", 0) or 0))
        title = _section_title(narr, n)
        section_events.append(OverlayEvent("chapter", at, min(total, at + 4.5), f"{n:02d}", title or f"Point {n}"))
    # For list videos, keep a compact progress agenda beside the subject. The
    # current point is highlighted while earlier/future points remain visible.
    if len(section_events) >= 2:
        events.extend(section_events[:10])
        rows = "\n".join(f"{int(e.title)}. {e.body}" for e in section_events[:6])
        for i, e in enumerate(section_events[:6]):
            end = section_events[i + 1].start if i + 1 < len(section_events) else min(total, e.start + 24.0)
            events.append(OverlayEvent("progress_list", e.start, max(e.start + 3.0, end),
                                       str(int(e.title)), rows, anchor="right"))
    else:
        events.extend(section_events[:10])

    # Sparse callouts: select shots well away from chapter cards and each other.
    if shots and max_keypoints > 0:
        chapter_times = [e.start for e in section_events]
        candidates = []
        # Prefer approved beat headings over truncated spoken fragments. Match
        # their text to shot narration rather than spacing cards arbitrarily.
        from ..editorial_text import STOP, clean_text, usable_headline
        for beat in script_data.get("beats", []) or []:
            title = clean_text(beat.get("onscreen_text") or beat.get("name") or "")
            if not usable_headline(title):
                continue
            tokens = set(re.findall(r"[a-z]{3,}", str(beat.get("text") or title).lower())) - STOP
            scored_shots = [(len(tokens & (set(re.findall(r"[a-z]{3,}", str(getattr(s, "narration", "")).lower())) - STOP)), s) for s in shots]
            overlap, shot = max(scored_shots, key=lambda pair: pair[0])
            at = float(getattr(shot, "voice_start", 0) or 0)
            if overlap >= 2 and 8 <= at < total - 10 and not any(abs(at-x) < 9 for x in chapter_times):
                candidates.append((20 + overlap, at, title))
        for s in shots:
            at = float(getattr(s, "voice_start", 0) or 0)
            narr = str(getattr(s, "narration", "") or "")
            if at < 8 or total - at < 15:
                continue
            if any(abs(at - x) < 9 for x in chapter_times):
                continue
            from ..editorial_text import callout
            phrase = callout(narr)
            if len(phrase.split()) < 4:
                continue
            # Prefer concrete, actionable lines.
            low = narr.lower()
            score = sum(k in low for k in ("do ", "use ", "write", "choose", "avoid", "remember", "focus", "instead", "because", "rule", "habit"))
            candidates.append((score, at, phrase))
        # Spread by time buckets, then prefer higher score within each bucket.
        if candidates:
            bucket = max(22.0, total / max(1, max_keypoints + 1))
            chosen = []
            used_b = set()
            for score, at, phrase in sorted(candidates, key=lambda x: (-x[0], x[1])):
                b = int(at / bucket)
                if b in used_b:
                    continue
                used_b.add(b)
                chosen.append((at, phrase))
                if len(chosen) >= max_keypoints:
                    break
            for at, phrase in sorted(chosen):
                events.append(OverlayEvent("keypoint", at + 0.4, min(total, at + 4.6), phrase, ""))

    # Recap/table card before the CTA: this replaces passive transcript text
    # with a compact visual summary viewers can actually scan.
    if len(section_events) >= 3 and total > 20:
        rows = []
        for e in section_events[:5]:
            rows.append(f"{e.title}. {e.body}")
        events.append(OverlayEvent("recap", max(0.0, total - 12.0), max(0.1, total - 5.5),
                                   "QUICK RECAP", "\n".join(rows)))

    # Subtle persistent channel identity. Keep clear of the final end screen.
    if show_watermark and channel_name and total > 12:
        events.append(OverlayEvent("watermark", 5.0, max(5.5, total - 6.0), channel_name,
                                   "", anchor="bottom-right", opacity=0.36))

    # Designed closure with CTA/end-screen breathing room.
    if total > 12:
        start = max(0.0, total - 5.0)
        events.append(OverlayEvent("outro", start, total - 0.25,
                                   "LIKE  •  SUBSCRIBE  •  COMMENT",
                                   "Watch the next video and keep building momentum."))
    # Never schedule a CTA outside the measured narration, or leave an agenda
    # running beyond the video end.
    for event in events:
        event.end = min(total, event.end)
    return sorted([e for e in events if 0 <= e.start < e.end <= total],
                  key=lambda e: (e.start, e.kind))


def _rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    except Exception:
        draw.rectangle(xy, fill=fill, outline=outline, width=width)


def _draw_centered(draw, lines: Iterable[str], font, y: int, W: int, fill, spacing: int = 10):
    yy = y
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        draw.text(((W - tw) / 2, yy), line, font=font, fill=fill)
        yy += th + spacing
    return yy


def render_overlay_png(event: OverlayEvent, path: str, W: int, H: int,
                       logo_path: str = "") -> str:
    if Image is None:
        raise RuntimeError("Pillow is required for professional graphic overlays")
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    scale = max(0.6, min(1.5, W / 1920.0))
    white = (255, 255, 255, 245)
    muted = (230, 233, 238, 225)
    accent = (255, 196, 66, 245)

    if event.kind == "intro":
        x0, x1 = int(W * 0.10), int(W * 0.90)
        y0, y1 = int(H * 0.28), int(H * 0.67)
        _rounded_rect(d, (x0, y0, x1, y1), int(28 * scale), (8, 12, 20, 72), (255,255,255,55), 2)
        title_font = _font(int(66 * scale), True)
        body_font = _font(int(30 * scale), False)
        lines = _wrap(event.title.upper(), 30 if W >= H else 19)[:3]
        yy = _draw_centered(d, lines, title_font, y0 + int(58*scale), W, white, int(10*scale))
        d.rectangle((int(W*.34), yy + int(16*scale), int(W*.66), yy + int(22*scale)), fill=accent)
        _draw_centered(d, _wrap(event.body, 55 if W >= H else 28)[:2], body_font, yy + int(48*scale), W, muted, 8)

    elif event.kind == "chapter":
        x0, x1 = int(W*.075), int(W*.67)
        y0, y1 = int(H*.13), int(H*.31)
        _rounded_rect(d, (x0, y0, x1, y1), int(24*scale), (8, 12, 20, 82))
        num_font = _font(int(82*scale), True)
        title_font = _font(int(38*scale), True)
        d.text((x0 + int(34*scale), y0 + int(24*scale)), event.title, font=num_font, fill=accent)
        tx = x0 + int(150*scale)
        lines = _wrap(event.body.upper(), 28 if W >= H else 16)[:2]
        yy = y0 + int(38*scale)
        for line in lines:
            d.text((tx, yy), line, font=title_font, fill=white)
            yy += int(48*scale)

    elif event.kind == "keypoint":
        x0, x1 = int(W*.12), int(W*.88)
        y0, y1 = int(H*.70), int(H*.83)
        _rounded_rect(d, (x0, y0, x1, y1), int(20*scale), (8, 12, 20, 68))
        d.rectangle((x0, y0, x0 + int(9*scale), y1), fill=accent)
        f = _font(int(36*scale), True)
        lines = _wrap(event.title, 48 if W >= H else 24)[:2]
        yy = y0 + int(30*scale)
        for line in lines:
            d.text((x0 + int(32*scale), yy), line, font=f, fill=white)
            yy += int(44*scale)

    elif event.kind == "recap":
        x0, x1 = int(W*.12), int(W*.88)
        y0, y1 = int(H*.17), int(H*.82)
        _rounded_rect(d, (x0, y0, x1, y1), int(24*scale), (8, 12, 20, 96), (255,255,255,55), 2)
        title_font = _font(int(46*scale), True)
        row_font = _font(int(30*scale), False)
        d.text((x0 + int(42*scale), y0 + int(34*scale)), event.title, font=title_font, fill=accent)
        yy = y0 + int(115*scale)
        for row in (event.body or "").splitlines()[:5]:
            lines = _wrap(row, 58 if W >= H else 26)[:2]
            for li, line in enumerate(lines):
                d.text((x0 + int(48*scale) + (int(18*scale) if li else 0), yy), line, font=row_font, fill=white if li == 0 else muted)
                yy += int(42*scale)
            yy += int(12*scale)

    elif event.kind == "progress_list":
        # Reference-style agenda rail: occupy one side rather than dimming the
        # entire shot. This keeps the speaker/footage readable behind the card.
        landscape = W >= H
        x0 = int(W * (.66 if landscape else .08))
        x1 = int(W * (.97 if landscape else .92))
        y0 = int(H * (.13 if landscape else .10))
        rows = (event.body or "").splitlines()[:6]
        row_h = int((60 if landscape else 76) * scale)
        y1 = min(int(H * .88), y0 + int(62 * scale) + row_h * len(rows))
        _rounded_rect(d, (x0, y0, x1, y1), int(18*scale),
                      (246, 249, 250, 158), (255, 255, 255, 105), 2)
        head_font = _font(int(25*scale), True)
        row_font = _font(int(24*scale), True)
        d.text((x0 + int(24*scale), y0 + int(18*scale)), "TODAY'S KEY POINTS",
               font=head_font, fill=(22, 95, 72, 245))
        yy = y0 + int(60*scale)
        try:
            current = int(event.title or 0)
        except Exception:
            current = 0
        for row in rows:
            try:
                number = int(row.split(".", 1)[0])
            except Exception:
                number = 0
            active = number == current
            if active:
                _rounded_rect(d, (x0 + int(12*scale), yy - int(7*scale),
                                  x1 - int(12*scale), yy + row_h - int(9*scale)),
                              int(10*scale), (44, 190, 125, 205))
            color = (255, 255, 255, 250) if active else (32, 40, 46, 225)
            text = row if len(row) <= (34 if landscape else 25) else row[:31] + "…"
            d.text((x0 + int(24*scale), yy), text, font=row_font, fill=color)
            yy += row_h

    elif event.kind == "outro":
        # Keep the final footage visible.  Older builds placed an opaque black
        # full-frame card here, which made healthy video look blank.
        x0, x1 = int(W*.08), int(W*.92)
        y0, y1 = int(H*.31), int(H*.66)
        _rounded_rect(d, (x0, y0, x1, y1), int(28*scale), (6, 9, 15, 78), (255,255,255,50), 2)
        f1 = _font(int(58*scale), True)
        f2 = _font(int(31*scale), False)
        _draw_centered(d, _wrap(event.title, 42 if W >= H else 20)[:2], f1, int(H*.38), W, white, 10)
        _draw_centered(d, _wrap(event.body, 60 if W >= H else 28)[:2], f2, int(H*.55), W, muted, 8)
        # simple end-screen placeholders without copying any external design
        if W >= H:
            _rounded_rect(d, (int(W*.18), int(H*.70), int(W*.48), int(H*.90)), int(18*scale), (255,255,255,22), (255,255,255,80), 2)
            _rounded_rect(d, (int(W*.55), int(H*.70), int(W*.82), int(H*.90)), int(18*scale), (255,255,255,22), (255,255,255,80), 2)

    elif event.kind == "watermark":
        f = _font(int(24*scale), True)
        text = event.title.strip()
        box = d.textbbox((0,0), text, font=f)
        tw, th = box[2]-box[0], box[3]-box[1]
        pad = int(14*scale)
        x = W - tw - pad*3
        y = H - th - pad*3
        alpha = int(max(0.15, min(1.0, event.opacity))*255)
        # Shadow only; no visible black label/card over the footage.
        d.text((x+1, y+1), text, font=f, fill=(0,0,0,int(alpha*.65)))
        d.text((x,y), text, font=f, fill=(255,255,255,alpha))

    # Optional logo on intro/outro. Never fail the whole render on bad logo.
    if logo_path and os.path.isfile(logo_path) and event.kind in {"intro", "outro"}:
        try:
            logo = Image.open(logo_path).convert("RGBA")
            max_w = int(W*.11); max_h = int(H*.11)
            logo.thumbnail((max_w,max_h), Image.Resampling.LANCZOS)
            img.alpha_composite(logo, (int(W*.055), int(H*.055)))
        except Exception:
            pass

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path)
    event.path = path
    return path


def build_overlay_assets(manifest, script_data: dict, out_dir: str,
                         channel_name: str = "", logo_path: str = "",
                         show_watermark: bool = True,
                         actual_duration: float | None = None) -> list[dict]:
    os.makedirs(out_dir, exist_ok=True)
    events = plan_overlays(manifest, script_data, channel_name=channel_name,
                           show_watermark=show_watermark, actual_duration=actual_duration)
    out = []
    for i, e in enumerate(events):
        path = os.path.join(out_dir, f"overlay_{i:02d}_{e.kind}.png")
        try:
            render_overlay_png(e, path, int(manifest.width), int(manifest.height), logo_path=logo_path)
            out.append(e.to_dict())
        except Exception as ex:
            out.append({**e.to_dict(), "path": "", "error": str(ex)[:180]})
    return out

"""YouTube-style editorial graphics and branding overlays.

The graphics engine intentionally works from the *approved script/shot plan* and
renders transparent PNG overlays with Pillow. FFmpeg only has to composite PNGs,
which is far more reliable across WSL/Linux builds than complex drawtext chains.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, asdict, field
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
    layout: dict = field(default_factory=dict)
    fade_in: float = 0.18
    fade_out: float = 0.18

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
    from .typography import font
    return font(size, bold=bold)


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
        events.append(OverlayEvent("intro", 0.35, min(3.2, total), _short_phrase(topic, 10),
                                   ""))

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
        pages = [rows[i:i+2] for i in range(0, len(rows), 2)]
        end = total - 5.5
        start = max(0.0, end - len(pages)*3.2)
        for i, page in enumerate(pages):
            events.append(OverlayEvent("recap", start+i*3.2, min(end, start+(i+1)*3.2),
                                       "QUICK RECAP", "\n".join(page)))

    # Subtle persistent channel identity. Keep clear of the final end screen.
    if show_watermark and channel_name and total > 12:
        events.append(OverlayEvent("watermark", 5.0, max(5.5, total - 6.0), channel_name,
                                   "", anchor="bottom-right", opacity=0.36))

    # Designed closure with CTA/end-screen breathing room.
    if total > 12 and str(getattr(manifest, "content_type", "")).lower() not in {"kids_story", "kids", "cartoon_story", "cinematic_story", "storytelling"}:
        start = max(0.0, total - 5.0)
        events.append(OverlayEvent("outro", start, total - 0.25,
                                   "LIKE  •  SUBSCRIBE  •  COMMENT",
                                   "Watch the next video and keep building momentum."))
    # Never schedule a CTA outside the measured narration, or leave an agenda
    # running beyond the video end.
    for event in events:
        event.end = min(total, event.end)
    # One readable card at a time. The old agenda/title/chapter layers could
    # all stack at t=0, hiding one another even with a bigger font.
    intro_end = max((e.end for e in events if e.kind == "intro"), default=0)
    for e in events:
        if e.kind not in {"intro", "watermark"} and e.start < intro_end:
            duration = e.end-e.start
            e.start = intro_end+.15
            e.end = min(total, e.start+duration)
        if e.kind == "progress_list":
            chapter = next((c for c in section_events if c.title.lstrip('0') == e.title), None)
            if chapter:
                e.start = max(e.start, chapter.end+.15)
            e.end = min(e.end, e.start+5)
    priority = {"intro": 0, "chapter": 1, "recap": 0, "outro": 0, "keypoint": 2, "progress_list": 3}
    scheduled = []
    for event in sorted(events, key=lambda e: (e.start, priority.get(e.kind, 0))):
        if event.kind == "watermark":
            continue
        if not 0 <= event.start < event.end <= total:
            continue
        prior = scheduled[-1] if scheduled else None
        if prior and event.start < prior.end+.12:
            if event.kind in {"outro", "recap"}:
                prior.end = event.start-.12
                if prior.end-prior.start < 1.5:
                    scheduled.pop()
            elif event.kind in {"progress_list", "keypoint"}:
                continue  # Decorative callouts never compete with a section.
            else:
                event.start = prior.end+.12
        if event.end-event.start >= 1.5:
            scheduled.append(event)
    scheduled += [e for e in events if e.kind == "watermark" and 0 <= e.start < e.end <= total]
    return sorted(scheduled, key=lambda e: (e.start, e.kind))


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
                       logo_path: str = "", style: str = "bold") -> str:
    from .typography import resolve_style, PALETTES, fit, draw_text, font
    if Image is None:
        raise RuntimeError("Pillow is required for graphic overlays")
    style = resolve_style(style)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    vertical = H > W
    scale = min(W, H) / 1080.0
    palette = PALETTES[style]
    pad, stroke = max(12, int(30 * scale)), max(1, int(3 * scale))
    left, right = int(W * .065), int(W * (.86 if vertical else .88))
    top = int(H * (.13 if vertical else .15))
    ink_boxes, sizes = [], []

    def panel(box):
        _rounded_rect(d, box, int(28 * scale), palette['panel'], (255, 255, 255, 65), max(1, int(2 * scale)))
        # A short accent rail gives hierarchy without covering the footage.
        x0, y0, x1, y1 = box
        _rounded_rect(d, (x0+pad, y0+pad, x0+pad+int(72*scale), y0+pad+int(7*scale)), int(3*scale), palette['accent'])

    def text(value, box, *, title=False, size=None, minimum=None, align='left', color=None, lines=3):
        layout = fit(d, value, box[2]-box[0], box[3]-box[1],
                     size=size or (88 if title else 48)*scale,
                     minimum=minimum or (62 if title else 40)*scale,
                     style=style, bold=True, headline=title, max_lines=lines, stroke=stroke)
        if layout:
            ink_boxes.append(draw_text(d, layout, box, color or (255, 255, 255, 255), align=align))
            sizes.append(layout.size)
        return layout

    if event.kind in {'intro', 'outro', 'keypoint', 'chapter'}:
        # Top-third cards leave the centre action and caption/UI safe zone clear.
        panel_h = int(H * (.25 if vertical else .30))
        if event.kind != 'chapter' or not event.title.strip().isdigit():
            body = event.body if event.kind != 'keypoint' else ''
            heading = fit(d, event.title, right-left-2*pad,
                          panel_h-2*pad-int(26*scale)-(int(92*scale) if body else 0),
                          size=88*scale, minimum=62*scale, style=style, bold=True,
                          headline=True, max_lines=3, stroke=stroke)
            panel_h = min(panel_h, 2*pad+int(26*scale)+heading.height+(int(104*scale) if body else 0))
        box = (left, top, right, top+panel_h)
        panel(box)
        content_top = top+pad+int(26*scale)
        if event.kind == 'chapter' and event.title.strip().isdigit():
            badge_w = int(120*scale)
            text(event.title, (left+pad, content_top, left+pad+badge_w, top+panel_h-pad),
                 title=True, size=90*scale, minimum=65*scale, color=palette['accent'], lines=1)
            text(event.body, (left+pad+badge_w+pad//2, content_top, right-pad, top+panel_h-pad),
                 title=True, size=76*scale, minimum=52*scale, lines=3)
        else:
            headline = event.title
            body = event.body if event.kind != 'keypoint' else ''
            head_bottom = top+panel_h-pad-(int(92*scale) if body else 0)
            text(headline, (left+pad, content_top, right-pad, head_bottom), title=True,
                 color=palette['accent'] if style == 'playful' else None, lines=3)
            if body:
                text(body, (left+pad, head_bottom+int(12*scale), right-pad, top+panel_h-pad),
                     size=44*scale, minimum=38*scale, lines=2)

    elif event.kind == 'progress_list':
        # Six tiny truncated agenda rows became unreadable on phones. Show one
        # current idea at a time, in full, instead of squeezing the entire list.
        rows = event.body.splitlines() or [event.title]
        current = next((row for row in rows if row.split('.', 1)[0].strip() == event.title.strip()), rows[0])
        box = (left, top, right, top+int(H*(.23 if vertical else .29)))
        panel(box)
        text("CURRENT POINT", (left+pad+int(86*scale), top+pad, right-pad, top+pad+int(42*scale)),
             size=34*scale, minimum=30*scale, color=palette['secondary'], lines=1)
        text(current, (left+pad, top+pad+int(62*scale), right-pad, box[3]-pad),
             title=True, size=74*scale, minimum=50*scale, lines=3)

    elif event.kind == 'recap':
        rows = event.body.splitlines() or []
        # Recaps are paginated by plan_overlays; reject an overloaded manual
        # card rather than silently clipping or reducing type to unreadable size.
        if len(rows) > 3:
            raise ValueError("Recap needs timed pages of at most three full rows")
        box = (left, top, right, top+int(H*(.40 if vertical else .62)))
        panel(box)
        text(event.title, (left+pad, top+pad+int(25*scale), right-pad, top+int(125*scale)),
             title=True, size=70*scale, minimum=52*scale, color=palette['accent'], lines=1)
        y = top+int(155*scale)
        row_h = (box[3]-pad-y)/max(1, len(rows))
        for row in rows:
            text(row, (left+pad, y, right-pad, y+row_h-int(12*scale)),
                 size=50*scale, minimum=40*scale, lines=3)
            y += row_h

    elif event.kind == 'watermark':
        face = font(max(16, int(26*scale)), bold=True, style=style)
        value = event.title.strip()
        ink = d.textbbox((0, 0), value, font=face)
        x = W-(ink[2]-ink[0])-int(W*.14 if vertical else 30*scale)
        y = H-int(H*.23 if vertical else 44*scale)-(ink[3]-ink[1])
        alpha = int(max(.15, min(1, event.opacity))*255)
        d.text((x, y), value, font=face, fill=(255, 255, 255, alpha),
               stroke_width=1, stroke_fill=(8, 13, 28, alpha))
    else:
        raise ValueError("Unknown editorial card: " + event.kind)

    if logo_path and os.path.isfile(logo_path) and event.kind in {'intro', 'outro'}:
        with Image.open(logo_path) as original:
            logo = original.convert('RGBA')
        logo.thumbnail((int(W*.10), int(H*.08)), Image.Resampling.LANCZOS)
        img.alpha_composite(logo, (left, int(H*.04)))
    event.layout = {'style': style, 'font_sizes': sizes, 'text_boxes': ink_boxes,
                    'reading_floor': round(38*scale), 'canvas': [W, H]}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path)
    event.path = path
    return path


def build_overlay_assets(manifest, script_data: dict, out_dir: str,
                         channel_name: str = "", logo_path: str = "",
                         show_watermark: bool = True,
                         actual_duration: float | None = None,
                         text_cards_enabled: bool = True, style: str = "auto") -> list[dict]:
    from .typography import resolve_style
    style = resolve_style(style, manifest)
    os.makedirs(out_dir, exist_ok=True)
    events = plan_overlays(manifest, script_data, channel_name=channel_name,
                           show_watermark=show_watermark, actual_duration=actual_duration)
    if not text_cards_enabled:
        events = [e for e in events if e.kind == 'watermark']
    out = []
    for i, e in enumerate(events):
        path = os.path.join(out_dir, f"overlay_{i:02d}_{e.kind}.png")
        try:
            render_overlay_png(e, path, int(manifest.width), int(manifest.height), logo_path=logo_path, style=style)
            out.append(e.to_dict())
        except Exception as ex:
            out.append({**e.to_dict(), "path": "", "error": str(ex)[:180]})
    return out

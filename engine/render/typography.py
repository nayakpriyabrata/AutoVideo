"""Measured, portable display typography for transparent video cards.

Bungee and Fredoka are bundled with their SIL Open Font Licenses. Text is never
silently cropped or squeezed below the reading floor to fit a crowded card.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

from PIL import ImageFont

FONT_ROOT = Path(__file__).resolve().parents[2] / "assets" / "fonts"
PALETTES = {
    "bold": {"accent": (255, 207, 61, 255), "secondary": (109, 230, 223, 255), "panel": (12, 20, 35, 158)},
    "playful": {"accent": (255, 217, 79, 255), "secondary": (136, 245, 213, 255), "panel": (40, 25, 79, 158)},
    "clean": {"accent": (125, 245, 210, 255), "secondary": (173, 207, 255, 255), "panel": (12, 24, 36, 158)},
}


def resolve_style(style="auto", manifest=None):
    if style == "auto":
        cartoon = str(getattr(manifest, "content_type", "")).lower() in ("kids_story", "kids", "cartoon_story", "cinematic_story")
        cartoon = cartoon or "cartoon" in str(getattr(manifest, "preset", "")).lower()
        return "playful" if cartoon else "bold"
    if style not in PALETTES:
        raise ValueError("Unknown text card style: " + str(style))
    return style


def font(size, bold=False, style="clean", headline=False):
    size = max(8, int(round(size)))
    style = resolve_style(style)
    candidates = []
    if style == "playful":
        candidates.append(FONT_ROOT / "Fredoka-Variable.ttf")
    elif style == "bold" and headline:
        candidates.append(FONT_ROOT / "Bungee-Regular.ttf")
    name = "DejaVuSans-Bold.ttf" if bold or headline else "DejaVuSans.ttf"
    candidates += [Path('/usr/share/fonts/truetype/dejavu') / name,
                   Path('/usr/share/fonts/truetype/liberation2') / ('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf'),
                   Path('/mnt/c/Windows/Fonts') / ('arialbd.ttf' if bold else 'arial.ttf')]
    # A scalable bundled fallback, NOT Pillow's unreadably tiny bitmap font.
    candidates.append(FONT_ROOT / "Fredoka-Variable.ttf")
    for path in candidates:
        if path.is_file():
            try:
                loaded = ImageFont.truetype(str(path), size=size)
                if path.name == "Fredoka-Variable.ttf":
                    axes = loaded.get_variation_axes()
                    values = [(650 if bold or headline else 500) if b'Weight' in a['name'] else a['default'] for a in axes]
                    loaded.set_variation_by_axes(values)
                return loaded
            except (OSError, ValueError):
                continue
    raise RuntimeError("No scalable card font available. Reinstall the bundled assets/fonts folder.")


@dataclass
class TextLayout:
    text: str
    font: object
    size: int
    width: int
    height: int
    spacing: int
    stroke: int
    lines: int


def measured_wrap(draw, text, face, width, stroke=0):
    lines = []
    for paragraph in str(text).splitlines() or [str(text)]:
        words = re.sub(r'\s+', ' ', paragraph).strip().split()
        current = ''
        for word in words:
            if draw.textlength(word, font=face) + 2 * stroke > width:
                return None
            proposed = (current + ' ' + word).strip()
            if current and draw.textlength(proposed, font=face) + 2 * stroke > width:
                lines.append(current)
                current = word
            else:
                current = proposed
        if current:
            lines.append(current)
    return '\n'.join(lines)


def fit(draw, text, width, height, *, size, minimum, style="clean", bold=False,
        headline=False, max_lines=4, stroke=2):
    if not str(text).strip():
        return None
    for px in range(int(round(size)), int(round(minimum)) - 1, -1):
        face = font(px, bold, style, headline)
        content = measured_wrap(draw, text, face, width, stroke)
        if not content or len(content.splitlines()) > max_lines:
            continue
        # Balance two-line headings so a single final word is not stranded.
        if headline and len(content.splitlines()) == 2 and '\n' not in str(text):
            words = str(text).split()
            candidates = []
            for cut in range(1, len(words)):
                pair = [' '.join(words[:cut]), ' '.join(words[cut:])]
                widths = [draw.textlength(line, font=face)+2*stroke for line in pair]
                if max(widths) <= width:
                    candidates.append((abs(widths[0]-widths[1]), '\n'.join(pair)))
            if candidates:
                content = min(candidates, key=lambda pair: pair[0])[1]
        spacing = max(5, int(px * .18))
        box = draw.multiline_textbbox((0, 0), content, font=face, spacing=spacing, stroke_width=stroke)
        tw, th = box[2] - box[0], box[3] - box[1]
        if tw <= width and th <= height:
            return TextLayout(content, face, px, tw, th, spacing, stroke, len(content.splitlines()))
    raise ValueError("Card copy is too long to read at this resolution; shorten it or split it into timed cards")


def draw_text(draw, layout, box, color=(255, 255, 255, 255), *, align="left"):
    """Place the actual ink bbox inside its slot, including outlines/ascenders."""
    if layout is None:
        return None
    x0, y0, x1, y1 = box
    ink = draw.multiline_textbbox((0, 0), layout.text, font=layout.font,
                                 spacing=layout.spacing, stroke_width=layout.stroke, align=align)
    x = x0 + ((x1 - x0 - layout.width) / 2 if align == "center" else 0)
    y = y0
    at = (x - ink[0], y - ink[1])
    # An outline keeps white/yellow copy legible on both dark and bright footage.
    draw.multiline_text(at, layout.text, font=layout.font, spacing=layout.spacing,
                        align=align, fill=color, stroke_width=layout.stroke,
                        stroke_fill=(8, 13, 28, 255))
    return [round(x, 2), round(y, 2), round(x + layout.width, 2), round(y + layout.height, 2)]

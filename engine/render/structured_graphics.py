"""Explicit, timed editorial graphics. Never invent numbers or truncate labels."""
import math
from pathlib import Path

from PIL import Image, ImageDraw
from .graphics import _font
from ..production import read


def validate_events(events, total):
    if not isinstance(events, list):
        raise ValueError('graphics.events must be a list')
    clean = []
    for e in events:
        if not isinstance(e, dict) or e.get('kind') not in ('list', 'comparison', 'bar_chart'):
            raise ValueError('Graphic kind must be list, comparison or bar_chart')
        start, end = e.get('start'), e.get('end')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)):
            raise ValueError('Graphic timing must be finite seconds')
        if not 0 <= start < end <= total or end-start < 1:
            raise ValueError('Graphic must last at least one second and fit the rendered duration')
        if not isinstance(e.get('title'), str) or not e['title'].strip():
            raise ValueError('Graphic needs a title')
        rows = e.get('rows')
        if not isinstance(rows, list) or not 1 <= len(rows) <= 5:
            raise ValueError('Use one to five rows per card')
        if any(not isinstance(row, dict) or not isinstance(row.get('label'), str)
               or not row['label'].strip() for row in rows):
            raise ValueError('Every graphic row needs a label')
        if e['kind'] == 'comparison' and any(not isinstance(r.get('detail'), str) or not r['detail'].strip() for r in rows):
            raise ValueError('Comparison rows need detail text')
        if e['kind'] == 'bar_chart':
            if not isinstance(e.get('source'), str) or not e['source'].strip() or not e.get('unit'):
                raise ValueError('Charts need a source and unit; values are supplied, never inferred')
            values = [r.get('value') for r in rows]
            if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values) or max(values) <= 0:
                raise ValueError('Chart values must be finite, nonnegative and include a positive value')
        if 'active' in e and (type(e['active']) is not int or not 0 <= e['active'] < len(rows)):
            raise ValueError('active must be a zero-based row index')
        if any(start < x['end'] and end > x['start'] for x in clean):
            raise ValueError('Structured cards cannot overlap; combine them or adjust their timings')
        clean.append(e)
    return clean


def fit_text(draw, text, width, height, size, bold=False):
    """Wrap by measured width, fail rather than silently crop excessive copy."""
    for px in range(size, max(14, int(size*.65))-1, -1):
        font = _font(px, bold)
        lines = []
        for para in str(text).splitlines():
            line = ''
            for word in para.split():
                if draw.textlength(word, font=font) > width:
                    break
                test = (line + ' ' + word).strip()
                if line and draw.textlength(test, font=font) > width:
                    lines.append(line)
                    line = word
                else:
                    line = test
            else:
                lines.append(line)
                continue
            break
        else:
            content = '\n'.join(lines)
            box = draw.multiline_textbbox((0, 0), content, font=font, spacing=6, stroke_width=1)
            if box[3]-box[1] <= height:
                return content, font
    raise ValueError('Graphic text is too long for readable layout; shorten it or split into timed cards')


def render_card(event, path, width, height):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    vertical = height > width
    # One translucent rail; no full-screen black box or full-frame dimming.
    left, top = int(width*.05), int(height*(.12 if vertical else .15))
    panel_w = int(width*(.90 if vertical else .53))
    rows = event['rows']
    panel_h = int(height*(min(.64, .13+.095*len(rows)) if vertical else min(.75, .22+.12*len(rows))))
    pad = max(12, int(width*.018))
    d.rounded_rectangle((left, top, left+panel_w, top+panel_h), radius=pad,
                        fill=(12, 24, 36, 48))
    content_w = panel_w-2*pad
    title_h = int(panel_h*.16)
    title, font = fit_text(d, event['title'], content_w, title_h, max(22, int(width*(.05 if vertical else .032))), True)
    d.multiline_text((left+pad, top+pad), title, font=font, spacing=6,
                     fill='white', stroke_width=1, stroke_fill=(0, 0, 0, 180))
    footer_h = int(panel_h*.12) if event['kind'] == 'bar_chart' else 0
    row_h = (panel_h-title_h-3*pad-footer_h)/len(rows)
    max_value = max((r.get('value', 0) for r in rows), default=1) or 1
    for index, row in enumerate(rows):
        y = int(top+title_h+2*pad+index*row_h)
        active = event.get('active') == index
        color = (125, 245, 180, 255) if active else (255, 255, 255, 255)
        text = f"{index+1}. {row['label']}" if event['kind'] == 'list' else row['label']
        if event['kind'] == 'comparison': text += ' — ' + row['detail']
        if event['kind'] == 'bar_chart': text += f": {row['value']:g} {event['unit']}"
        bar_h = int(row_h*.25) if event['kind'] == 'bar_chart' else 0
        text, font = fit_text(d, text, content_w, row_h-pad-bar_h, max(20, int(width*(.039 if vertical else .025))), active)
        d.multiline_text((left+pad, y), text, font=font, spacing=6, fill=color,
                         stroke_width=1, stroke_fill=(0, 0, 0, 200))
        if bar_h and row['value'] > 0:
            bar_y = int(y+row_h-pad-bar_h)
            d.rectangle((left+pad, bar_y, left+pad+int(content_w*row['value']/max_value), bar_y+bar_h),
                        fill=(100, 215, 240, 215))
    if footer_h:
        source, font = fit_text(d, 'Source: '+event['source'], content_w, footer_h,
                               max(16, int(width*.016)))
        d.multiline_text((left+pad, top+panel_h-pad-footer_h), source, font=font, spacing=6, fill='white')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return {'kind': event['kind'], 'start': event['start'], 'end': event['end'],
            'title': event['title'], 'path': str(path), 'opacity': 1, 'anchor': 'center'}


def build_structured_overlays(root, total, width, height):
    root = Path(root)
    events = validate_events(read(root/'production/graphics.json', {}).get('events', []), total)
    return [render_card(e, root/'render/graphics'/f'structured-{i:03d}.png', int(width), int(height))
            for i, e in enumerate(events)]

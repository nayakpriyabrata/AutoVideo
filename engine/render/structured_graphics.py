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


def render_card(event, path, width, height, style="bold"):
    from .typography import resolve_style, PALETTES, fit, draw_text
    style = resolve_style(style)
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    vertical = height > width
    scale = min(width, height)/1080.0
    palette = PALETTES[style]
    left, top = int(width*.065), int(height*.12)
    panel_w = int(width*(.795 if vertical else .70))
    rows = event['rows']
    panel_h = int(height*(min(.54, .22+.064*len(rows)) if vertical else min(.76, .30+.09*len(rows))))
    pad, stroke = max(12, int(28*scale)), max(1, int(3*scale))
    d.rounded_rectangle((left, top, left+panel_w, top+panel_h), radius=int(28*scale),
                        fill=palette['panel'], outline=(255, 255, 255, 65), width=max(1, int(2*scale)))
    content_w = panel_w-2*pad
    title_h = int(128*scale)
    layout = fit(d, event['title'], content_w, title_h, size=76*scale, minimum=52*scale,
                 style=style, bold=True, headline=True, max_lines=2, stroke=stroke)
    boxes = [draw_text(d, layout, (left+pad, top+pad, left+panel_w-pad, top+pad+title_h), palette['accent'])]
    sizes = [layout.size]
    footer_h = int(96*scale) if event['kind'] == 'bar_chart' else 0
    row_h = (panel_h-title_h-3*pad-footer_h)/len(rows)
    max_value = max((r.get('value', 0) for r in rows), default=1) or 1
    for index, row in enumerate(rows):
        y = int(top+title_h+2*pad+index*row_h)
        active = event.get('active') == index
        color = palette['secondary'] if active else (255, 255, 255, 255)
        value = f"{index+1}. {row['label']}" if event['kind'] == 'list' else row['label']
        if event['kind'] == 'comparison': value += ' — ' + row['detail']
        if event['kind'] == 'bar_chart': value += f": {row['value']:g} {event['unit']}"
        bar_h = int(row_h*.18) if event['kind'] == 'bar_chart' else 0
        row_box = (left+pad, y, left+panel_w-pad, y+row_h-int(12*scale)-bar_h)
        layout = fit(d, value, content_w, row_box[3]-row_box[1], size=52*scale, minimum=40*scale,
                     style=style, bold=True, max_lines=3, stroke=stroke)
        boxes.append(draw_text(d, layout, row_box, color))
        sizes.append(layout.size)
        if bar_h and row['value'] > 0:
            bar_y = int(y+row_h-int(8*scale)-bar_h)
            d.rounded_rectangle((left+pad, bar_y, left+pad+int(content_w*row['value']/max_value), bar_y+bar_h),
                                radius=max(1, bar_h//3), fill=palette['secondary'])
    if footer_h:
        footer_box = (left+pad, top+panel_h-pad-footer_h, left+panel_w-pad, top+panel_h-pad)
        layout = fit(d, 'Source: '+event['source'], content_w, footer_h, size=40*scale, minimum=34*scale,
                     style=style, bold=True, max_lines=2, stroke=max(1, stroke-1))
        boxes.append(draw_text(d, layout, footer_box))
        sizes.append(layout.size)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return {'kind': event['kind'], 'start': event['start'], 'end': event['end'],
            'title': event['title'], 'path': str(path), 'opacity': 1, 'anchor': 'center',
            'fade_in': .18, 'fade_out': .18,
            'layout': {'style': style, 'font_sizes': sizes, 'text_boxes': boxes, 'canvas': [width, height]}}


def build_structured_overlays(root, total, width, height, style="bold"):
    root = Path(root)
    events = validate_events(read(root/'production/graphics.json', {}).get('events', []), total)
    return [render_card(e, root/'render/graphics'/f'structured-{i:03d}.png', int(width), int(height), style=style)
            for i, e in enumerate(events)]

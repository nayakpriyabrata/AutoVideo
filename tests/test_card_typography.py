"""Measured type, full copy and transparent phone-safe cards."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw
import pytest

from engine.render.graphics import OverlayEvent, render_overlay_png, build_overlay_assets, plan_overlays
from engine.render.typography import font, fit, resolve_style
from engine.render.structured_graphics import render_card


@pytest.mark.parametrize('style', ['bold', 'playful', 'clean'])
@pytest.mark.parametrize('dimensions', [(1080, 1920), (1920, 1080), (720, 1280)])
def test_display_type_is_large_and_inside_safe_zone(tmp_path, style, dimensions):
    w, h = dimensions
    event = OverlayEvent('keypoint', 0, 3, 'Tiny steps. Big adventures.')
    render_overlay_png(event, str(tmp_path/'card.png'), w, h, style=style)
    assert min(event.layout['font_sizes']) >= 62*min(w, h)/1080-1
    assert event.layout['style'] == style
    for x0, y0, x1, y1 in event.layout['text_boxes']:
        assert 0 <= x0 < x1 <= w*.88 and 0 <= y0 < y1 < h*.64
    with Image.open(tmp_path/'card.png') as image:
        alpha = np.asarray(image.getchannel('A'))
    assert alpha[0, 0] == 0
    assert np.mean(alpha >= 180) < .08


def test_bundled_faces_are_real_scalable_display_fonts():
    assert 'Bungee' in font(88, True, 'bold', headline=True).getname()[0]
    assert 'Fredoka' in font(88, True, 'playful', headline=True).getname()[0]
    assert font(88, True, 'playful').size == 88
    assert resolve_style('auto', SimpleNamespace(content_type='kids_story', preset='cartoon_story')) == 'playful'


def test_measured_layout_preserves_copy_or_fails_readably():
    d = ImageDraw.Draw(Image.new('RGBA', (1080, 1920)))
    value = 'Small acts of kindness make a big difference'
    layout = fit(d, value, 850, 300, size=78, minimum=62, style='playful', headline=True, max_lines=3)
    assert ' '.join(layout.text.split()) == value
    assert layout.size >= 62
    with pytest.raises(ValueError, match='too long'):
        fit(d, 'unreasonablylongword'*40, 200, 100, size=80, minimum=62)


def test_current_point_is_full_copy_not_truncated_agenda(tmp_path):
    event = OverlayEvent('progress_list', 1, 4, '2', '1. Start small\n2. A kind act can change the whole day\n3. Share the joy')
    render_overlay_png(event, str(tmp_path/'agenda.png'), 1080, 1920, style='playful')
    assert min(event.layout['font_sizes'][1:]) >= 50


def test_no_cards_build_omits_every_editorial_kind(tmp_path):
    m = SimpleNamespace(topic='A happy adventure', target_seconds=45, shots=[], width=1080, height=1920,
                        content_type='kids_story', preset='cartoon_story')
    assert build_overlay_assets(m, {}, str(tmp_path), text_cards_enabled=False, show_watermark=False) == []
    assert not list(tmp_path.glob('*.png'))
    assert all(e.kind != 'outro' for e in plan_overlays(m, {}))


def test_structured_card_keeps_labels_at_readable_size(tmp_path):
    event = dict(kind='comparison', start=0, end=5, title='Small choices matter',
                 rows=[{'label':'Kindness', 'detail':'Share what you can'}, {'label':'Courage', 'detail':'Try one new thing'}])
    overlay = render_card(event, tmp_path/'structured.png', 1080, 1920, style='playful')
    assert min(overlay['layout']['font_sizes']) >= 40
    assert overlay['fade_in'] > 0
    for box in overlay['layout']['text_boxes']:
        assert box[2] <= 1080*.86 and box[3] < 1920*.70


def test_package_includes_licensed_fonts_not_user_uploads(tmp_path):
    from tools.build_release import release_files
    root = tmp_path/'repo'; folder = root/'assets/fonts'; folder.mkdir(parents=True)
    for name in ('Bungee-Regular.ttf', 'Fredoka-Variable.ttf', 'OFL-Bungee.txt', 'OFL-Fredoka.txt', 'private-font.ttf', 'private-license.txt'):
        (folder/name).write_bytes(b'fixture')
    included = {p.name for p in release_files(root)}
    assert included == {'Bungee-Regular.ttf', 'Fredoka-Variable.ttf', 'OFL-Bungee.txt', 'OFL-Fredoka.txt'}


def test_automatic_cards_never_stack_over_one_another():
    from engine.project.manifest import Shot, ProductionManifest
    m = ProductionManifest(job_id='j', topic='Three ways to be kind', target_seconds=90,
                           shots=[Shot(voice_start=i*20, voice_end=(i+1)*20,
                                       narration=f'Step {i+1}: Choose a kind action every day.') for i in range(4)])
    events = [e for e in plan_overlays(m, {}) if e.kind != 'watermark']
    assert all(a.end <= b.start for a, b in zip(events, events[1:]))

"""Actual encoded output: music-only, truly silent, and no unwanted text."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from engine.factory import Factory
from engine.project.manifest import Shot
from engine.render.ffmpeg_renderer import build_ffmpeg_cmd
from tests.test_audio_mix_quality import tone_amplitude


def encode(ffmpeg, media, out, **options):
    cmd, meta = build_ffmpeg_cmd([{'src': media['video'], 'dur': 4, 'hard_cut': True}],
                               None, str(out), W=320, H=180, encoder='libx264',
                               quality='preview', safe_concat=True, **options)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    return meta


@pytest.mark.parametrize('loudnorm', [True, False])
def test_music_only_real_output_no_voice_detector(ffmpeg_binary, ffmpeg_media, tmp_path, loudnorm):
    out = tmp_path/'music-only.mp4'
    meta = encode(ffmpeg_binary, ffmpeg_media, out, music=ffmpeg_media['music'], music_volume=.55, use_loudnorm=loudnorm)
    assert 'sidechaincompress' not in meta['filter_complex'] and '[voice]' not in meta['filter_complex']
    assert not meta['voiceover_enabled'] and meta['audio_present']
    decoded = subprocess.run([ffmpeg_binary, '-v', 'error', '-i', str(out), '-map', '0:a:0',
                              '-ar', '48000', '-f', 'f32le', '-'], capture_output=True, timeout=30)
    assert decoded.returncode == 0
    samples = np.frombuffer(decoded.stdout, dtype='<f4').reshape(-1, 2)
    assert abs(len(samples)/48000-4) < .05
    assert np.sqrt(np.mean((samples[:, 0]-samples[:, 1])**2)) > .001
    assert tone_amplitude(samples, 220, .3, .8) > .02
    assert tone_amplitude(samples, 220, 3.3, 3.8) > .02
    assert tone_amplitude(samples, 440, .5, 3) < .002  # No narration tone.


def test_silent_real_output_has_no_audio_stream(ffmpeg_binary, ffmpeg_media, tmp_path):
    out = tmp_path/'silent.mp4'
    meta = encode(ffmpeg_binary, ffmpeg_media, out)
    assert not meta['audio_present'] and '[mix]' not in meta['filter_complex']
    probe = subprocess.run([ffmpeg_binary, '-v', 'error', '-i', str(out), '-map', '0:a:0',
                            '-f', 'null', '-'], capture_output=True, timeout=20)
    assert probe.returncode != 0 and b'matches no streams' in probe.stderr


def test_music_sfx_overlay_input_indices_without_voice(tmp_path):
    music = tmp_path/'music.wav'; music.write_bytes(b'fixture')
    image = tmp_path/'overlay.png'; image.write_bytes(b'fixture')
    sfx = tmp_path/'sfx.wav'; sfx.write_bytes(b'fixture')
    cmd, meta = build_ffmpeg_cmd([{'src':'clip.mp4', 'dur':4}], None, 'out.mp4', encoder='libx264',
                               music=str(music), sfx=[{'path':str(sfx), 'at':1}],
                               overlays=[{'path':str(image), 'start':.5, 'end':3, 'fade_in':.2, 'fade_out':.2}])
    graph = meta['filter_complex']
    assert '[1:a]' in graph and '[2:a]' in graph and '[3:v]' in graph
    assert 'fade=t=in:st=0.500:d=0.200:alpha=1' in graph
    assert 'sidechain' not in graph and 'None' not in cmd


def saved_job(tmp_path, media):
    f = Factory(str(tmp_path/'outputs'), str(tmp_path/'db.sqlite'))
    job = f.create_job('A bunny shares a carrot', production_mode='youtube_pro', voiceover_enabled=False,
                       text_cards_enabled=False, target_seconds=4, background_music='local',
                       background_music_path=media['music'], text_card_style='playful')
    m = f.pm.load_manifest(job)
    m.width, m.height = 320, 180
    m.shots = [Shot(shot_id='shot_001', voice_end=4, duration_target=4,
                   status='accepted', accepted_take=media['video'], actual_provider='image')]
    f.pm.save_manifest(m)
    root = Path(f.pm.job_dir(job))
    (root/'script.json').write_text(json.dumps({'narration':'Unspoken story notes', 'source':'test-ai', 'editorial_qc':{'passed':True}}))
    (root/'production').mkdir(exist_ok=True)
    (root/'production/graphics.json').write_text('INVALID OLD CARDS THAT MUST NOT BE READ WHEN OFF')
    # Old speech artifacts are intentionally retained but must never be read/burned.
    (root/'narration/voice.mp3.words.json').write_text('INVALID OLD TRANSCRIPT')
    return f, job, root


def test_factory_renders_without_narration_or_cards(monkeypatch, tmp_path, ffmpeg_media):
    from engine import captions
    from engine.render import captions_ass, ffmpeg_renderer as ff
    from engine.audio import music_provider
    from engine.render import graphics, structured_graphics
    def forbidden(*args, **kwargs):
        pytest.fail('Disabled presentation stage/provider was invoked')
    monkeypatch.setattr(captions, 'get_word_timestamps', forbidden)
    monkeypatch.setattr(captions_ass, 'build_captions', forbidden)
    monkeypatch.setattr(graphics, 'build_overlay_assets', forbidden)
    monkeypatch.setattr(structured_graphics, 'build_structured_overlays', forbidden)
    monkeypatch.setattr(music_provider, 'ensure_background_music', forbidden)
    monkeypatch.setattr(ff, 'detect_encoder', lambda: 'libx264')
    f, job, root = saved_job(tmp_path, ffmpeg_media)
    result = f.render_job(job, quality='preview')
    assert Path(result['video']).is_file() and result['renderer'] == 'ffmpeg'
    assert result['graphics'] == [] and result['captions']['disabled']
    assert result['publish_readiness']['checks']['captions_present']
    assert result['publish_readiness']['checks']['editorial_graphics']
    assert 'captions_present' in result['publish_readiness']['checks_not_applicable']
    sound = json.loads((root/'audio/sound_plan.json').read_text())
    assert sound['sfx'] == [] and sound['ambience'] is None and not sound['voiceover_enabled']
    assert not (root/'narration/voice.mp3').exists()
    assert (root/'narration/voice.mp3.words.json').read_text() == 'INVALID OLD TRANSCRIPT'


def test_requested_music_is_not_silently_dropped(tmp_path, ffmpeg_media):
    f, job, root = saved_job(tmp_path, ffmpeg_media)
    f.set_presentation_options(job, background_music_path=str(tmp_path/'missing.wav'))
    with pytest.raises(ValueError, match='does not exist'):
        f.render_job(job, quality='preview')
    assert f.pm.load_manifest(job).shots[0].status == 'accepted'


@pytest.mark.parametrize('music_on', [True, False])
def test_moviepy_fallback_honours_music_only_and_silent(tmp_path, ffmpeg_media, ffmpeg_binary, music_on):
    from engine.render.moviepy_renderer import render_moviepy
    path = tmp_path/'compatibility.mp4'
    result = render_moviepy([{'src':ffmpeg_media['video'], 'dur':4, 'in':0}], None, path,
                            total=4, W=320, H=180, music=ffmpeg_media['music'] if music_on else None,
                            music_volume=.55, words=[{'word':'DO NOT SHOW', 'start':0, 'end':4}], captions=True)
    assert result['audio_present'] is music_on and not result['voiceover_enabled']
    assert not result['captions_requested'] and result['overlays'] == 0
    assert path.is_file()
    audio = subprocess.run([ffmpeg_binary, '-v', 'error', '-i', str(path), '-map', '0:a:0', '-f', 'null', '-'], capture_output=True, timeout=20)
    assert (audio.returncode == 0) is music_on


def test_music_only_display_card_fade_renders_without_altering_canvas(ffmpeg_binary, ffmpeg_media, tmp_path):
    from engine.render.graphics import OverlayEvent, render_overlay_png
    overlay = tmp_path/'card.png'
    event = OverlayEvent('keypoint', .5, 3.5, 'Share the joy!')
    render_overlay_png(event, str(overlay), 320, 180, style='playful')
    out = tmp_path/'music-card.mp4'
    meta = encode(ffmpeg_binary, ffmpeg_media, out, music=ffmpeg_media['music'], overlays=[event.to_dict()])
    assert meta['overlays'] == 1 and meta['total'] == 4
    assert 'alpha=1' in meta['filter_complex'] and 'sidechain' not in meta['filter_complex']
    decoded = subprocess.run([ffmpeg_binary, '-v', 'error', '-ss', '1', '-i', str(out),
                              '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt','rgb24','-'], capture_output=True, timeout=20)
    assert decoded.returncode == 0 and len(decoded.stdout) == 320*180*3

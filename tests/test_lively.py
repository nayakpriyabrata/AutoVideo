"""'Lifeless video' fixes: moving Ken Burns, font discovery, narration fit."""
import os
import subprocess

import numpy as np
import pytest


def test_kenburns_pan_moves_frame():
    from PIL import Image
    import pytest
    ImageClip = pytest.importorskip("moviepy.editor").ImageClip
    from engine.video_builder import _ken_burns
    # left black -> right white gradient: any crop drift changes brightness
    grad = np.tile(np.linspace(0, 255, 360).astype(np.uint8), (640, 1))
    rgb = np.stack([grad, grad, grad], axis=-1)
    p = "/tmp/_kb_test.jpg"
    Image.fromarray(rgb).save(p)
    clip = ImageClip(p, duration=4.0)
    out = _ken_burns(clip, 180, 320, 4.0, zoom_in=True, pan=(1.0, 0.0))
    f0 = out.get_frame(0).mean()
    f1 = out.get_frame(3.99).mean()
    assert out.get_frame(0).shape == (320, 180, 3)  # exact size, no bars
    assert abs(f1 - f0) > 8  # crop visibly drifted across the gradient


def test_kenburns_defaults_have_motion():
    import inspect
    from engine.video_builder import _ken_burns
    sig = inspect.signature(_ken_burns)
    assert sig.parameters["zoom_range"].default >= 0.2  # was 0.13, too sleepy


def test_motion_varies_per_shot_and_is_stable():
    from engine.providers.image_provider import ImageProvider
    a = ImageProvider.motion_for("shot_001")
    assert ImageProvider.motion_for("shot_001") == a  # deterministic reruns
    moves = {ImageProvider.motion_for(f"shot_{i:03d}") for i in range(1, 9)}
    assert len(moves) >= 4  # shots don't all drift the same way


def test_clip_duration_covers_voice_window():
    import types
    from engine.providers.image_provider import ImageProvider
    s = types.SimpleNamespace(shot_id="shot_003", gen_duration=8,
                              voice_start=0.0, voice_end=11.8, duration_target=11.8)
    assert ImageProvider.clip_duration(s) == pytest.approx(11.8)  # no freeze-fill


def test_dir_has_font_detection(tmp_path):
    from engine.render.ffmpeg_renderer import _dir_has_font, FONTS_DIR_CANDIDATES
    assert "/mnt/c/Windows/Fonts" in FONTS_DIR_CANDIDATES  # WSL real fonts
    assert _dir_has_font(str(tmp_path)) is False
    (tmp_path / "arial.ttf").write_bytes(b"fake")
    assert _dir_has_font(str(tmp_path)) is True
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "x.otf").write_bytes(b"fake")
    (tmp_path / "arial.ttf").unlink()
    assert _dir_has_font(str(tmp_path)) is True  # one level down


def _ff_has_lame():
    from engine.audio.tts import _ffmpeg_bin
    ff = _ffmpeg_bin()
    if not ff:
        return None
    r = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True)
    return ff if "libmp3lame" in r.stdout else None


def test_fit_narration_caps_speedup_without_hard_trim(tmp_path):
    ff = _ff_has_lame()
    if not ff:
        pytest.skip("no ffmpeg+libmp3lame here")
    from engine.audio.tts import fit_narration_to_target
    mp3 = str(tmp_path / "v.mp3")
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
                    "-codec:a", "libmp3lame", mp3],
                   capture_output=True, check=True)
    words = [{"word": f"w{i}", "start": float(i), "end": float(i + 1)} for i in range(10)]
    w2, d2 = fit_narration_to_target(mp3, words, 5.0)
    # v5 deliberately refuses to squeeze 10s of speech into 5s. The script
    # director must rewrite overlong narration; this final stage only permits
    # the gentle 1.08x correction.
    assert d2 == pytest.approx(10.0 / 1.08, abs=0.35)
    assert w2[-1]["end"] > 8.5
    assert w2[0]["start"] == pytest.approx(0.0)


def test_fit_narration_keeps_short_audio(tmp_path):
    ff = _ff_has_lame()
    if not ff:
        pytest.skip("no ffmpeg+libmp3lame here")
    from engine.audio.tts import fit_narration_to_target
    mp3 = str(tmp_path / "v.mp3")
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-codec:a", "libmp3lame", mp3],
                   capture_output=True, check=True)
    words = [{"word": "hi", "start": 0.0, "end": 4.0}]
    w2, d2 = fit_narration_to_target(mp3, words, 20.0)
    assert d2 == pytest.approx(4.0, abs=0.3) and w2 == words

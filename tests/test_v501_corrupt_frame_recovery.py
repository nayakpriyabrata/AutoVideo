from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from engine.factory import Factory
from engine.providers.image_provider import ImageProvider


def _shot():
    return SimpleNamespace(
        shot_id="shot_006", visual_goal="test", negative="",
        voice_start=0.0, voice_end=2.0, duration_target=2.0, gen_duration=2.0,
        opening_frame=None, closing_frame=None,
    )


def test_factory_rejects_corrupt_cached_image(tmp_path, monkeypatch):
    f = Factory(outputs=str(tmp_path / "out"), db_path=str(tmp_path / "jobs.db"))
    monkeypatch.setattr(f, "_flow_frame_cache_dir", lambda url: str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    key = f._flow_frame_cache_key("https://flow.google.com/project/abc", "p", False, "closing frame")
    bad = tmp_path / "cache" / f"{key}.jpg"
    bad.write_bytes(b"not-a-jpeg")
    assert f._flow_frame_cache_get("https://flow.google.com/project/abc", "p", False, "closing frame") is None
    assert not bad.exists()


def test_image_provider_ignores_bad_optional_closing_frame(tmp_path, monkeypatch):
    # Avoid actual MoviePy/ffmpeg work; this test only proves the corrupt end frame
    # is filtered before Pillow tries to decode it.
    start = tmp_path / "open.jpg"
    Image.new("RGB", (128, 72), "white").save(start, "JPEG")
    end = tmp_path / "close.jpg"
    end.write_bytes(b"not-a-jpeg")

    # Monkeypatch imports used inside generate via lightweight fake modules.
    import sys, types
    class FakeClip:
        def __init__(self, *a, **k): pass
        def set_duration(self, *a, **k): return self
        def write_videofile(self, path, **k): Path(path).write_bytes(b"video")
        def close(self): pass
    fake = types.ModuleType("moviepy.editor")
    fake.ImageClip = FakeClip
    fake.CompositeVideoClip = lambda *a, **k: FakeClip()
    monkeypatch.setitem(sys.modules, "moviepy.editor", fake)

    import engine.video_builder as vb
    monkeypatch.setattr(vb, "_cover_resize", lambda im, w, h: im.resize((w, h)))
    monkeypatch.setattr(vb, "_ken_burns", lambda clip, *a, **k: clip)

    out = tmp_path / "out.mp4"
    r = ImageProvider().generate(_shot(), {"prompt": "x"}, {"start": str(start), "end": str(end)}, str(out), False)
    assert r["path"] == str(out)
    assert r["model"] == "kenburns_plus"

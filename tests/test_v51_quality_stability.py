from pathlib import Path
from types import SimpleNamespace
import os


def test_v51_gemini_audio_extractor_and_raw_pcm(tmp_path):
    from engine.audio.tts import GeminiTTSProvider
    payload = {"interaction": {"output_audio": {"data": "A" * 300}}}
    assert GeminiTTSProvider._audio_data(payload) == "A" * 300


def test_v51_groq_chunks_respect_provider_limit():
    from engine.audio.tts import GroqTTSProvider
    text = ("A natural sentence about building a better life through small habits. " * 20).strip()
    chunks = GroqTTSProvider._chunks(text)
    assert chunks
    assert all(1 <= len(x) <= 190 for x in chunks)
    assert len(chunks) > 1


def test_v51_auto_tts_does_not_load_kokoro_without_optin(monkeypatch, tmp_path):
    from engine.audio import tts as mod
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("AUTOVIDEO_ENABLE_LOCAL_TTS", raising=False)
    monkeypatch.setattr(mod, "_kokoro_available", lambda: True)

    def fail_kokoro(self, *a, **k):
        raise AssertionError("Kokoro must be opt-in in auto mode")

    def fake_edge(self, text, voice, out, rate="+0%", **kwargs):
        return {"audio": out, "words": [], "duration": 10.0, "engine": "edge-native"}

    monkeypatch.setattr(mod.KokoroProvider, "synth", fail_kokoro)
    monkeypatch.setattr(mod.EdgeTTSProvider, "synth", fake_edge)
    r = mod.synthesize_narration("hello world", "voice", str(tmp_path / "a.mp3"), provider="auto")
    assert r["engine"] == "edge-native"


def test_v51_wordpop_events_never_overlap():
    from engine.video_builder import _wordpop_events
    words = [
        {"word": "Build", "start": 0.00, "end": 0.35},
        {"word": "better", "start": 0.30, "end": 0.70},
        {"word": "habits.", "start": 0.66, "end": 1.10},
        {"word": "Today", "start": 1.02, "end": 1.40},
    ]
    ev = _wordpop_events(words, 2.0)
    assert ev
    for a, b in zip(ev, ev[1:]):
        assert a["end"] <= b["start"] + 1e-9


def test_v51_visual_diversity_detects_reencoded_duplicate(tmp_path):
    from PIL import Image
    from engine.qc.visual_diversity import analyze_storyboard
    d = tmp_path / "storyboard"
    d.mkdir()
    a = Image.new("RGB", (320, 180), (40, 70, 120))
    # add geometry so dHash is meaningful
    for x in range(30, 150):
        for y in range(50, 120):
            a.putpixel((x, y), (230, 220, 80))
    a.save(d / "shot_001_open.jpg", quality=95)
    a.save(d / "shot_001_close.jpg", quality=70)
    b = Image.new("RGB", (320, 180), (220, 220, 220))
    for x in range(180, 300):
        for y in range(20, 150):
            b.putpixel((x, y), (20, 30, 30))
    b.save(d / "shot_002_open.jpg", quality=90)
    r = analyze_storyboard(str(d))
    assert r["frames"] == 3
    assert r["unique_frames"] <= 2
    assert r["near_duplicate_pairs"]


def test_v51_storage_guard_fails_before_corrupt_media(monkeypatch, tmp_path):
    from engine.factory import Factory
    fake = SimpleNamespace(free=int(0.25 * 1024**3))
    monkeypatch.setattr("engine.factory.shutil.disk_usage", lambda p: fake)
    monkeypatch.setenv("AUTOVIDEO_MIN_FREE_GB", "1.5")
    try:
        Factory._check_storage(str(tmp_path))
    except RuntimeError as e:
        assert "Insufficient free disk space" in str(e)
    else:
        raise AssertionError("low storage must stop before media generation")


def test_v51_motion_profiles_vary_by_coverage():
    from engine.providers.image_provider import ImageProvider
    a = SimpleNamespace(shot_id="shot_001", coverage="insert")
    b = SimpleNamespace(shot_id="shot_001", coverage="broll")
    assert ImageProvider.motion_for(a) != ImageProvider.motion_for(b)
    assert ImageProvider.motion_for("shot_001") == ImageProvider.motion_for("shot_001")


def test_v51_ffmpeg_retries_software_encoder(monkeypatch, tmp_path):
    from engine.render import ffmpeg_renderer as fr

    calls = []
    class R:
        def __init__(self, code, err=""):
            self.returncode = code
            self.stderr = err
            self.stdout = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return R(1, "Cannot load libcuda / hardware encoder unavailable") if len(calls) == 1 else R(0, "")

    monkeypatch.setattr(fr.subprocess, "run", fake_run)
    seg = [{"src": "x.mp4", "in": 0, "dur": 1.0, "freeze": 0.0, "trans_out": "cut"}]
    out = tmp_path / "out.mp4"
    r = fr.render_ffmpeg(seg, "voice.mp3", str(out), W=320, H=180,
                         encoder="h264_nvenc", quality="preview")
    assert r["retried_software_encoder"] is True
    assert r["encoder"] == "libx264"
    assert len(calls) == 2

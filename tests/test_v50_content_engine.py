from pathlib import Path
import json

from engine.planning import script_engine
from engine.captions import align_words_to_script


def test_v50_full_script_provider_owns_narration(monkeypatch):
    payload = {
        "angle": "decisions before motivation",
        "audience": "young professionals",
        "hook": "Winning starts before the hard moment arrives.",
        "hooks": ["Winning starts before the hard moment arrives."],
        "beats": [
            {"name": "setup", "text": "Design the choice before pressure appears.", "visual_intent": "desk", "emotion": "calm"},
            {"name": "practice", "text": "Repeat the smallest useful action until it becomes automatic.", "visual_intent": "practice", "emotion": "focused"},
        ],
        "narration": "Winning starts before the hard moment arrives. " +
                     "Design the choice before pressure appears. " * 10,
        "cta": "",
        "cta_kind": "none",
    }
    monkeypatch.setattr(script_engine, "_provider_available", lambda p: p == "gemini")
    monkeypatch.setattr(script_engine, "_call_provider", lambda *a, **k: json.dumps(payload))
    plan = script_engine.generate_script_plan(
        "How develop a winner mindset", "motivation", 45, "cinematic", "en",
        provider="gemini", model="gemini-test", quality="standard", target_words=80,
    )
    assert plan is not None
    assert plan["source"] == "gemini:gemini-test"
    assert plan["narration"].startswith("Winning starts")
    assert plan["beats"][0]["visual_intent"] == "desk"


def test_v50_caption_alignment_uses_exact_script_words():
    script = "Discipline means choosing the harder action, even when motivation disappears."
    asr = [
        {"word": "Discipline", "start": 0.0, "end": 0.4},
        {"word": "means", "start": 0.4, "end": 0.7},
        {"word": "choosing", "start": 0.7, "end": 1.1},
        {"word": "harder", "start": 1.3, "end": 1.7},
        {"word": "action", "start": 1.7, "end": 2.0},
        {"word": "motivation", "start": 2.5, "end": 3.1},
        {"word": "disappears", "start": 3.1, "end": 3.8},
    ]
    out = align_words_to_script(script, asr, 4.0)
    assert " ".join(x["word"] for x in out) == script
    assert out[0]["start"] == 0.0
    assert out[-1]["end"] <= 4.0
    assert all(out[i]["start"] <= out[i]["end"] <= out[i+1]["start"]
               for i in range(len(out) - 1))


def test_v50_retime_has_sentence_safe_offline_fallback(monkeypatch):
    monkeypatch.setattr(script_engine, "_provider_available", lambda p: False)
    plan = {
        "angle": "x", "audience": "general", "hook": "Hook one.", "hooks": ["Hook one."],
        "beats": [], "cta": "", "cta_kind": "none", "source": "planner",
        "narration": " ".join([
            "This is the first complete sentence.",
            "This is the second complete sentence with more detail.",
            "This is the third complete sentence with another useful idea.",
            "This is the fourth complete sentence that should probably be removed.",
        ]),
        "words": 36,
    }
    out = script_engine.retime_script_plan(
        plan, "topic", "education", 12, "calm", "en", 20,
        provider="auto", model="auto",
    )
    assert out is not None
    assert out["narration"].endswith((".", "!", "?"))
    assert "sentence-retime" in out["source"]


def test_v50_ass_style_has_exact_v4plus_field_count(tmp_path):
    from engine.render.captions_ass import build_captions
    words = [
        {"word": "Natural", "start": 0.0, "end": 0.4},
        {"word": "captions", "start": 0.4, "end": 0.9},
    ]
    out = build_captions(words, str(tmp_path / "captions"), template="HORMOZI",
                         aspect="16:9", W=1920, H=1080)
    text = Path(out["ass"]).read_text(encoding="utf-8")
    style_line = next(x for x in text.splitlines() if x.startswith("Style: Cap,"))
    # Everything after "Style: " follows the 23-column V4+ Styles Format.
    assert len(style_line[len("Style: "):].split(",")) == 23


def test_v50_ffmpeg_can_disable_loudnorm_for_safe_retry(tmp_path):
    from engine.render.ffmpeg_renderer import build_ffmpeg_cmd
    clip = tmp_path / "clip.mp4"
    voice = tmp_path / "voice.mp3"
    # Command construction does not inspect input bytes.
    clip.write_bytes(b"x")
    voice.write_bytes(b"x")
    cmd, meta = build_ffmpeg_cmd(
        [{"src": str(clip), "dur": 2.0, "in": 0, "trans_out": "cut"}],
        str(voice), str(tmp_path / "out.mp4"), W=640, H=360,
        encoder="libx264", use_loudnorm=False,
    )
    fc = meta["filter_complex"]
    assert "loudnorm=" not in fc
    assert "[mix]anull[aout]" in fc
    assert meta["use_loudnorm"] is False

import json
from types import SimpleNamespace as NS

import pytest


@pytest.mark.parametrize("provider", ["gemini-hybrid", "gemini-web-hybrid"])
def test_partial_gemini_results_are_preserved(monkeypatch, tmp_path, provider):
    import engine.clipping as c
    from engine.render import captions_ass, ffmpeg_renderer
    source = "https://youtube.com/watch?v=fixture"
    highlights = [{"start": i*35., "end": i*35.+30, "duration": 30,
                   "title": f"Useful lesson number {i}", "score": 90,
                   "text": "Practice builds confidence over time.", "ranking": "gemini-hybrid"}
                  for i in range(5)]
    monkeypatch.setattr(c, "resolve_input", lambda *a, **k: "source.mp4")
    monkeypatch.setattr(c, "_duration", lambda *a: 200)
    monkeypatch.setattr(c, "_transcribe_in_chunks", lambda *a: [
        {"word": "practice", "start": i, "end": i+.5} for i in range(200)])
    monkeypatch.setattr(c, "_gemini_youtube_candidates", lambda *a, **k: highlights)
    monkeypatch.setattr(c, "_gemini_web_youtube_candidates", lambda *a, **k: highlights)
    monkeypatch.setattr(c, "_verify_gemini_candidates", lambda *a: highlights)
    monkeypatch.setattr(c, "rank_highlights", lambda *a, **k: pytest.fail("discarded valid Gemini candidates"))
    monkeypatch.setattr(captions_ass, "build_captions", lambda *a, **k: {"ass": str(tmp_path / "captions.ass")})
    monkeypatch.setattr(c, "_face_crop_x", lambda *a: .5)
    monkeypatch.setattr(ffmpeg_renderer, "_run_ffmpeg_progress", lambda *a, **k: NS(returncode=0))
    monkeypatch.setattr(c, "_clip_qc_report", lambda *a: {"decision": "PASS", "quality_score": 90})
    (tmp_path / "useful-lesson-number-0.mp4").write_bytes(b"existing video")
    result = c.create_highlight_clips(source, str(tmp_path), count=10,
                                      source_rights="own_content", ranking_provider=provider)
    assert result["actual_count"] == 5 and result["requested_count"] == 10
    assert result["partial_result"] is True
    assert result["highlights"][0]["title"] == "Useful lesson number 0"
    assert result["outputs"][0].endswith("useful-lesson-number-0-2.mp4")
    assert (tmp_path / "useful-lesson-number-0.mp4").read_bytes() == b"existing video"
    assert (tmp_path / "logs/progress.json").exists()
    assert json.loads((tmp_path / "highlights.json").read_text())["actual_count"] == 5


def test_title_ignores_filler_opening():
    from engine.clipping import _short_title
    assert _short_title("Yeah. Practice builds confidence over time.") == "Practice builds confidence over time"


def test_cards_do_not_truncate_a_thought():
    from engine.editorial_text import callout
    assert callout("We wake up, sit at our desks, and") == ""
    assert callout("Our true human human potential for for far") == ""
    assert callout("Choose one task and protect your attention.") == "Choose one task and protect your attention"


def test_graphics_uses_approved_beat_heading_and_actual_duration():
    from engine.render.graphics import plan_overlays
    m = NS(topic="How AI changes work", target_seconds=300, shots=[
        NS(voice_start=20, voice_end=28, narration="Automation can remove repetitive tasks while we work on complex decisions and creative problems.")])
    script = {"beats": [{"name": "Automation frees creative time", "text": "Automation removes repetitive tasks and supports creative work"}]}
    events = plan_overlays(m, script, actual_duration=100)
    assert any(e.title == "Automation frees creative time" for e in events)
    assert all(e.end <= 100 for e in events)
    assert next(e for e in events if e.kind == "outro").start == 95


def test_bad_word_anchors_no_long_gap_or_collapsed_tail():
    from engine.captions import align_words_to_script
    text = " ".join(["We build useful habits every day."] * 50)
    tokens = text.split()
    bad = [{"word": w, "start": i*.2 + (130 if i > 30 else 0),
            "end": i*.2 + (130 if i > 30 else 0) + .18} for i, w in enumerate(tokens)]
    result = align_words_to_script(text, bad, 210)
    assert len(result) == len(tokens)
    assert all(w["end"] > w["start"] for w in result)
    assert max(result[i]["start"]-result[i-1]["end"] for i in range(1, len(result))) < 6


def test_coverage_blocks_long_extension_and_identical_copies(tmp_path):
    from engine.render.coverage import audit_coverage
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"same content"); b.write_bytes(a.read_bytes())
    segments = [{"shot_id": "shot_006", "src": str(a), "dur": 7.2, "freeze": 132.7},
                {"shot_id": "shot_009", "src": str(b), "dur": 7.2, "freeze": 42.5}]
    report = audit_coverage(segments, 287.9)
    assert not report["passed"]
    assert "shot_006" in report["issues"][0]
    assert any("Repeated source" in issue for issue in report["issues"])


def test_coverage_allows_distinct_motion_clips(tmp_path):
    from engine.render.coverage import audit_coverage
    a = tmp_path / "a.mp4"; a.write_bytes(b"source A")
    assert audit_coverage([{"src": str(a), "dur": 8, "freeze": 1}], 9)["passed"]


def test_hard_cut_graph_does_not_subtract_dissolve_time(tmp_path):
    from engine.render.ffmpeg_renderer import build_ffmpeg_cmd
    segments = [{"src": "a.mp4", "dur": 4, "freeze": 0, "in": 0, "hard_cut": True,
                 "trans_out": "dissolve"} for _ in range(3)]
    _, meta = build_ffmpeg_cmd(segments, "voice.mp3", "out.mp4", W=320, H=180,
                               safe_concat=True, encoder="libx264", use_loudnorm=False)
    assert meta["total"] == 12
    assert "xfade=" not in meta["filter_complex"]


def test_static_tail_detected_until_eof(monkeypatch, tmp_path):
    from engine.render import ffmpeg_renderer as r
    path = tmp_path / "frozen.mp4"; path.write_bytes(b"x" * 2048)
    monkeypatch.setattr(r.subprocess, "run", lambda *a, **k: NS(
        returncode=0, stdout="", stderr="freeze_start: 2.0"))
    result = r._freeze_metrics(str(path), 30)
    assert result["longest"] == 28 and result["ratio"] > .9


def test_unrelated_local_stock_is_rejected_even_small_library(monkeypatch):
    from engine.providers.stock_provider import StockProvider
    monkeypatch.setattr(StockProvider, "_library_files", lambda: ["clouds.mp4"])
    assert StockProvider._pick_local("software computer office") is None


def test_ai_stock_query_not_weather_clouds():
    from engine.planning.economy_storyboard import _stock_query
    shot = NS(narration="AI agents automate cloud computing workflows", visual_goal="", environment="", subject="")
    assert "software" in _stock_query(shot)
    assert "cloud" not in _stock_query(shot)


def test_gemini_refuses_wrong_current_chat():
    from engine.providers.gemini_web import GeminiWebBrowser
    b = object.__new__(GeminiWebBrowser)
    b._submitted_chat_id = "owned"
    b._page = NS(url="https://gemini.google.com/app/other")
    assert b.delete_current_chat() is False


def test_gemini_refuses_existing_chat_after_failed_fresh_navigation(monkeypatch):
    from engine.providers.gemini_web import GeminiWebBrowser, GeminiWebUIChanged
    b = object.__new__(GeminiWebBrowser)
    b._page = NS(url="https://gemini.google.com/app/existing")
    monkeypatch.setattr(b, "start_fresh_chat", lambda: None)
    with pytest.raises(GeminiWebUIChanged, match="existing conversation"):
        b.ask("test")


@pytest.mark.parametrize("url", ["https://evil.example/app/owned", "https://gemini.google.com/app", "https://gemini.google.com/app/a/b"])
def test_invalid_chat_urls_rejected(url):
    from engine.providers.gemini_web import GeminiWebBrowser
    assert GeminiWebBrowser._chat_id(url) == ""

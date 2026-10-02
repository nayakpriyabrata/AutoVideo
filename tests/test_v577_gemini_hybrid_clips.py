import json
from types import SimpleNamespace

import pytest


def _timed_words(seconds=90):
    words = []
    for i in range(seconds * 2):
        token = "important" if 20 <= i * .5 <= 55 else "practice"
        if i % 16 == 15:
            token += "."
        words.append({"word": token, "start": i * .5, "end": i * .5 + .42})
    return words


def test_timestamp_parser_accepts_seconds_mmss_and_hhmmss():
    from engine.clipping import _timestamp_seconds

    assert _timestamp_seconds(12.5) == 12.5
    assert _timestamp_seconds("01:20") == 80
    assert _timestamp_seconds("1:02:03") == 3723
    assert _timestamp_seconds("bad") is None


def test_specific_rights_declaration_is_required_for_url():
    from engine.clipping import _rights_policy

    with pytest.raises(RuntimeError, match="source-rights"):
        _rights_policy("https://youtube.com/watch?v=x")
    own = _rights_policy("https://youtube.com/watch?v=x", "own_content")
    assert own["public_upload_cleared_by_declaration"] is True
    review = _rights_policy("https://youtube.com/watch?v=x", "commentary_or_review")
    assert review["public_upload_cleared_by_declaration"] is False
    assert "minor edits" in review["warnings"][0]


def test_gemini_youtube_request_uses_video_part_and_parses_candidates(monkeypatch):
    import engine.clipping as clipping

    seen = {}
    body = {"candidates": [
        {"start": "00:20", "end": "00:52", "score": 94,
         "title": "A strong lesson", "reason": "complete payoff",
         "requires_context": False},
        {"start": "00:55", "end": "01:20", "score": 99,
         "title": "Rejected", "requires_context": True},
    ]}

    def post(url, **kwargs):
        seen["url"] = url
        seen["payload"] = kwargs["json"]
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"candidates": [{"content": {"parts": [
                {"thought": True, "text": "internal"},
                {"text": json.dumps(body)},
            ]}}]},
        )

    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setattr(clipping.requests, "post", post)
    result = clipping._gemini_youtube_candidates(
        "https://www.youtube.com/watch?v=test", 120, 3, 25, 55,
        model="gemini-test")
    assert len(result) == 1 and result[0]["start"] == 20
    parts = seen["payload"]["contents"][0]["parts"]
    assert parts[0]["file_data"]["file_uri"].startswith("https://www.youtube.com/")
    assert "gemini-test:generateContent" in seen["url"]


def test_gemini_api_retries_transient_503(monkeypatch):
    import engine.clipping as clipping
    import requests

    calls, waits, messages = [], [], []
    valid = {"candidates": [{"start": "00:10", "end": "00:40", "score": 88,
                             "title": "Complete", "requires_context": False}]}

    class Response:
        def __init__(self, fail):
            self.fail = fail
            self.status_code = 503 if fail else 200
        def raise_for_status(self):
            if self.fail:
                raise requests.HTTPError("503 unavailable", response=self)
        def json(self):
            return {"candidates": [{"content": {"parts": [
                {"text": json.dumps(valid)}]}}]}

    def post(*args, **kwargs):
        calls.append(1)
        return Response(fail=len(calls) < 3)

    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setattr(clipping.requests, "post", post)
    monkeypatch.setattr(clipping.time, "sleep", lambda value: waits.append(value))
    result = clipping._gemini_youtube_candidates(
        "https://youtube.com/watch?v=x", 100, 1, 25, 55,
        model="test-configured-model",
        progress_cb=messages.append)
    assert len(result) == 1
    assert len(calls) == 3 and waits == [2, 5]
    assert all("retrying" in message for message in messages)


def test_gemini_browser_candidate_analysis_and_cleanup_setting(monkeypatch):
    import engine.clipping as clipping
    import engine.providers.gemini_web as gemini_web

    seen = {}
    answer = {"candidates": [{"start": "00:20", "end": "00:50", "score": 91,
                              "title": "Browser pick", "requires_context": False}]}

    def generate(system, user, model="auto"):
        seen["user"] = user
        seen["cleanup"] = clipping.os.getenv("AUTOVIDEO_GEMINI_CHAT_CLEANUP")
        return json.dumps(answer)

    monkeypatch.setattr(gemini_web, "gemini_web_generate", generate)
    monkeypatch.delenv("AUTOVIDEO_GEMINI_CHAT_CLEANUP", raising=False)
    result = clipping._gemini_web_youtube_candidates(
        "https://youtube.com/watch?v=x", 100, 1, 25, 55,
        cleanup="delete-after-read")
    assert result[0]["title"] == "Browser pick"
    assert "https://youtube.com/watch?v=x" in seen["user"]
    assert seen["cleanup"] == "delete-after-read"
    assert clipping.os.getenv("AUTOVIDEO_GEMINI_CHAT_CLEANUP") is None


def test_gemini_candidates_are_snapped_and_locally_verified():
    from engine.clipping import _verify_gemini_candidates

    proposals = [{"start": 19.8, "end": 51.7, "duration": 31.9,
                  "gemini_score": 92, "title": "Strong idea",
                  "editorial_reason": "hook and payoff"}]
    verified = _verify_gemini_candidates(proposals, _timed_words(), 90, 25, 55)
    assert len(verified) == 1
    assert verified[0]["ranking"] == "gemini-hybrid"
    assert verified[0]["text"].endswith(".")
    assert verified[0]["local_score"] > 0
    assert 0 < verified[0]["score"] <= 100


def test_local_music_needs_no_music_specific_acknowledgement(tmp_path, monkeypatch):
    import engine.clipping as clipping

    source = tmp_path / "mine.mp4"
    music = tmp_path / "music.mp3"
    source.write_bytes(b"video")
    music.write_bytes(b"music")
    monkeypatch.setattr(clipping, "resolve_input",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("source stage reached")))
    with pytest.raises(RuntimeError, match="source stage reached"):
        clipping.create_highlight_clips(
            str(source), str(tmp_path / "out"), background_music=str(music),
            music_license="none", source_rights="own_content")

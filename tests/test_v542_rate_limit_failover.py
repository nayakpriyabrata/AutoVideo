import requests
import pytest

from engine.planning import script_engine as se


class DummyResponse:
    status_code = 429


def _http429():
    err = requests.HTTPError("429 Client Error: Too Many Requests")
    err.response = DummyResponse()
    return err


def test_rate_limit_detector():
    assert se._is_rate_limited(_http429())
    assert se._is_rate_limited(RuntimeError("429 Too Many Requests: rate limit exceeded"))
    assert not se._is_rate_limited(RuntimeError("500 server error"))


def test_auto_skips_rate_limited_provider(monkeypatch):
    monkeypatch.setattr(se, "auto_provider_order", lambda: ["groq", "gemini"])
    monkeypatch.setattr(se, "_provider_available", lambda p: p in {"groq", "gemini"})
    monkeypatch.setattr(se, "_default_model", lambda p: "dummy")

    good = {
        "narration": " ".join(["word"] * 620),
        "beats": [
            {"label":"Habit 1","narration":"one","visual_intent":"a"},
            {"label":"Habit 2","narration":"two","visual_intent":"b"},
            {"label":"Habit 3","narration":"three","visual_intent":"c"},
            {"label":"Habit 4","narration":"four","visual_intent":"d"},
            {"label":"Habit 5","narration":"five","visual_intent":"e"},
        ],
        "hook":"hook", "cta":"cta"
    }

    calls=[]
    def fake_two_stage(p, *args, **kwargs):
        calls.append(p)
        if p == "groq":
            raise _http429()
        return good, "ok"
    monkeypatch.setattr(se, "_generate_longform_two_stage", fake_two_stage)
    monkeypatch.setattr(se, "_quality_flags", lambda *a, **k: [])
    monkeypatch.setattr(se, "script_quality_report", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(se, "_call_provider", lambda *a, **k: "{}")

    out = se.generate_script_plan(
        "5 habits for a successful life", "education", 300, "clear", "en",
        provider="auto", quality="publish", target_words=620
    )
    assert out is not None
    assert calls == ["groq", "gemini"]


def test_explicit_rate_limited_provider_fails_immediately(monkeypatch):
    monkeypatch.setattr(se, "_provider_available", lambda p: p == "groq")
    monkeypatch.setattr(se, "_default_model", lambda p: "dummy")
    monkeypatch.setattr(se, "_generate_longform_two_stage", lambda *a, **k: (_ for _ in ()).throw(_http429()))

    with pytest.raises(se.ScriptProviderError) as exc:
        se.generate_script_plan(
            "5 habits for a successful life", "education", 300, "clear", "en",
            provider="groq", quality="publish", target_words=620
        )
    assert "rate-limited" in str(exc.value).lower()

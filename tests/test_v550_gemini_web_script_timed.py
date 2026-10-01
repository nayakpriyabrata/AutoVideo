import os


def test_script_timed_captions_use_exact_script_and_duration():
    from engine.captions import script_timed_word_timestamps
    text = "Habit one: plan tomorrow tonight. Habit two: protect your health, even on busy days."
    words = script_timed_word_timestamps(text, 12.5)
    assert words
    assert [w["word"] for w in words] == text.split()
    assert words[0]["start"] == 0.0
    assert abs(words[-1]["end"] - 12.5) < 0.01
    assert all(words[i]["start"] >= words[i-1]["end"] for i in range(1, len(words)))


def test_get_word_timestamps_script_timed_never_calls_asr(monkeypatch, tmp_path):
    import engine.captions as c
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake")
    monkeypatch.setattr(c, "_audio_duration", lambda p: 8.0)
    monkeypatch.setattr(c, "_groq_word_timestamps", lambda *a, **k: (_ for _ in ()).throw(AssertionError("groq called")))
    monkeypatch.setattr(c, "_local_word_timestamps", lambda *a, **k: (_ for _ in ()).throw(AssertionError("local called")))
    words = c.get_word_timestamps(str(audio), provider="script-timed",
                                  script_text="One useful sentence. Another useful sentence.",
                                  force=True)
    assert words
    assert abs(words[-1]["end"] - 8.0) < 0.01


def test_gemini_web_is_explicit_provider_without_api_key(monkeypatch):
    import engine.planning.script_engine as s
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert s._provider_available("gemini-web") is True
    monkeypatch.delenv("AUTOVIDEO_ENABLE_GEMINI_WEB", raising=False)
    assert "gemini-web" not in s.auto_provider_order()
    monkeypatch.setenv("AUTOVIDEO_ENABLE_GEMINI_WEB", "1")
    assert "gemini-web" in s.auto_provider_order()


def test_gemini_web_call_routes_to_browser_adapter(monkeypatch):
    import engine.providers.gemini_web as gw
    import engine.planning.script_engine as s
    monkeypatch.setattr(gw, "gemini_web_generate", lambda system, user, model="auto": '{"ok": true}')
    out = s._call_provider("gemini-web", "gemini-web", "sys", "user")
    assert '"ok": true' in out

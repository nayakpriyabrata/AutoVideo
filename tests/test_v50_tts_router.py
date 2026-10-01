from engine.audio import tts as ttsmod


def test_v50_auto_tts_prefers_gemini_when_keyed(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    calls = []

    def fake_gemini(self, text, voice, out, rate="+0%", **kwargs):
        calls.append("gemini-lite" if self.lite else "gemini")
        return {"audio": out, "words": [], "duration": 10.0, "engine": calls[-1]}

    def fail_edge(self, *a, **k):
        raise AssertionError("Edge should not run when Gemini succeeds")

    monkeypatch.setattr(ttsmod.GeminiTTSProvider, "synth", fake_gemini)
    monkeypatch.setattr(ttsmod.EdgeTTSProvider, "synth", fail_edge)
    out = ttsmod.synthesize_narration("hello", "legacy", str(tmp_path / "v.mp3"), provider="auto")
    assert out["engine"] == "gemini"
    assert calls == ["gemini"]


def test_v50_default_speedup_is_gentle():
    import inspect
    sig = inspect.signature(ttsmod.fit_narration_to_target)
    assert sig.parameters["max_rate"].default == 1.08
    assert sig.parameters["hard_trim"].default is False

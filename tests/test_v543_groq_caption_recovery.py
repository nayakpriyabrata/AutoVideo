import json
from pathlib import Path

import requests

from engine import captions


def test_compact_groq_prompt_stays_short():
    src = " ".join(f"word{i}" for i in range(700))
    out = captions._compact_groq_prompt(src)
    assert len(out.split()) <= 110
    assert len(out) <= 900


def test_segments_can_supply_word_anchors():
    segs = [{"start": 1.0, "end": 3.0, "text": "hello successful world"}]
    words = captions._segments_to_word_timestamps(segs)
    assert [w["word"] for w in words] == ["hello", "successful", "world"]
    assert words[0]["start"] == 1.0
    assert words[-1]["end"] <= 3.0


def test_groq_400_with_prompt_retries_without_prompt(monkeypatch, tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"ID3" + b"x" * 2048)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    calls = []

    class Resp:
        def __init__(self, status, payload=None, text=""):
            self.status_code = status
            self._payload = payload or {}
            self.text = text
        def json(self):
            return self._payload

    def fake_request(audio_path, key, data, timeout=180):
        calls.append(list(data))
        has_prompt = any(k == "prompt" for k, _ in data)
        if has_prompt:
            r = Resp(400, text='{"error":{"message":"prompt too long"}}')
            raise requests.HTTPError("Groq transcription HTTP 400: prompt too long", response=r)
        return Resp(200, payload={"words": [{"word": "hello", "start": 0.1, "end": 0.4}]})

    monkeypatch.setattr(captions, "_groq_transcription_request", fake_request)
    out = captions._groq_word_timestamps(str(audio), "whisper-large-v3-turbo", "en", " ".join(["test"] * 500))
    assert out and out[0]["word"] == "hello"
    assert len(calls) == 2
    assert any(k == "prompt" for k, _ in calls[0])
    assert not any(k == "prompt" for k, _ in calls[1])


def test_groq_segment_fallback_stays_same_provider(monkeypatch, tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"ID3" + b"x" * 2048)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = []

    class Resp:
        status_code = 200
        text = ""
        def __init__(self, payload): self._payload = payload
        def json(self): return self._payload

    def fake_request(audio_path, key, data, timeout=180):
        calls.append(list(data))
        gran = [v for k, v in data if k == "timestamp_granularities[]"]
        if gran == ["word"]:
            r = type("Bad", (), {"status_code": 400, "text": '{"error":{"message":"bad optional field"}}'})()
            raise requests.HTTPError("400", response=r)
        return Resp({"segments": [{"start": 0.0, "end": 1.2, "text": "one two three"}]})

    monkeypatch.setattr(captions, "_groq_transcription_request", fake_request)
    out = captions._groq_word_timestamps(str(audio), "whisper-large-v3-turbo", "en", "")
    assert [w["word"] for w in out] == ["one", "two", "three"]
    assert any(any(k == "timestamp_granularities[]" and v == "segment" for k, v in c) for c in calls)

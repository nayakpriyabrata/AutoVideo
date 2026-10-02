"""Focused tests for the optional Gemini Web → Google Flow mini-reel path."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import mini_reels as reels
from engine.providers.flow_browser import FlowRequestPending


BRIEF = {
    "title": "A tiny garden wakes up",
    "angle": "A miniature seedling opens beside a glowing dew drop.",
    "video_prompt": (
        "Show a tiny handcrafted garden at dawn. A small seedling slowly opens beside a clear dew drop, "
        "the camera makes a gentle macro push-in, and warm sunlight catches the miniature leaves."
    ),
    "voiceover_line": "Small beginnings can change everything.",
    "narration": "Small beginnings can change everything.",
    "caption": "A little light goes a long way.",
    "hashtags": ["#Miniature", "#TinyGarden"],
    "idea": "tiny garden",
    "visual_style": "miniature-diorama",
    "language": "en",
    "audio_mode": "flow-voiceover",
    "prompt_provider": "gemini-web",
}


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start:start + chunk_size]

    def close(self):
        pass


def test_trends_parse_bounded_google_rss_and_deduplicate(monkeypatch):
    payload = b"""<?xml version='1.0'?>
    <rss xmlns:ht='http://www.google.com/trends/hottrends'>
      <channel>
        <item><title>Garden ideas</title><link>https://trends.google.com/one</link>
          <pubDate>Today</pubDate><ht:approx_traffic>2K+</ht:approx_traffic></item>
        <item><title> garden IDEAS </title><link>https://trends.google.com/two</link></item>
        <item><title>Miniature garden</title></item>
      </channel>
    </rss>"""
    seen = {}

    def get(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return FakeResponse(payload)

    monkeypatch.setattr(reels.requests, "get", get)
    rows = reels.fetch_trend_ideas("in", count=10)
    assert [row["title"] for row in rows] == ["Garden ideas", "Miniature garden"]
    assert rows[0]["approx_traffic"] == "2K+"
    assert rows[0]["region"] == "IN"
    assert "geo=IN" in seen["url"]
    assert seen["kwargs"]["timeout"] == (5, 20)


def test_trends_fail_closed_on_invalid_region_or_unsafe_xml(monkeypatch):
    with pytest.raises(ValueError, match="supported trend region"):
        reels.fetch_trend_ideas("ZZ")
    monkeypatch.setattr(reels.requests, "get", lambda *a, **k: FakeResponse(b"<!DOCTYPE rss><rss/>"))
    with pytest.raises(ValueError, match="DTD/entities"):
        reels.fetch_trend_ideas("US")


def test_trend_response_size_is_bounded(monkeypatch):
    payload = b"x" * (reels.MAX_TREND_FEED_BYTES + 1)
    monkeypatch.setattr(reels.requests, "get", lambda *a, **k: FakeResponse(payload))
    with pytest.raises(ValueError, match="512 KB safety limit"):
        reels.fetch_trend_ideas("GB")


def test_brief_json_validation_and_audio_mode():
    raw = 'preface ```json\n' + json.dumps(BRIEF) + '\n``` end'
    value = reels._extract_json_object(raw)
    brief = reels.validate_prompt_brief(value, audio_mode="flow-voiceover")
    assert brief["prompt_provider"] == "gemini-web"
    assert brief["voiceover_line"] == "Small beginnings can change everything."
    assert brief["hashtags"] == ["#Miniature", "#TinyGarden"]
    silent = reels.validate_prompt_brief(value, audio_mode="silent")
    assert silent["voiceover_line"] == ""
    too_long = dict(BRIEF, voiceover_line="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty one")
    with pytest.raises(ValueError, match="at most 16 words"):
        reels.validate_prompt_brief(too_long, audio_mode="flow-voiceover")


def test_gemini_prompt_uses_visible_web_provider_without_api_fallback(monkeypatch):
    import engine.providers.gemini_web as gemini_web
    called = {}

    def fake_generate(system, user, model):
        called.update({"system": system, "user": user, "model": model})
        return json.dumps(BRIEF)

    monkeypatch.setattr(gemini_web, "gemini_web_generate", fake_generate)
    brief = reels.generate_prompt_brief(
        "tiny garden trend", visual_style="miniature-diorama", language="en",
        audio_mode="flow-voiceover")
    assert called["model"] == "gemini-web"
    assert "no Gemini API fallback" not in called["system"].lower()
    assert "tiny garden trend" in called["user"]
    assert "exactly 8 seconds" in called["user"]
    assert brief["prompt_provider"] == "gemini-web"


def test_flow_prompt_contains_explicit_portrait_audio_and_model_instructions():
    prompt = reels.compose_flow_prompt(
        BRIEF, visual_style="miniature-diorama", language="en",
        audio_mode="flow-voiceover", model="veo_fast")
    assert "portrait 9:16" in prompt
    assert "approximately 8 seconds" in prompt
    assert "Veo 3.1 - Fast" in prompt
    assert "says exactly" in prompt
    assert "Small beginnings can change everything." in prompt
    ambient = reels.compose_flow_prompt(
        BRIEF, visual_style="miniature-stop-motion", language="hi",
        audio_mode="flow-ambience", model="veo_lite")
    assert "no spoken words" in ambient
    assert "Miniature stop-motion" not in ambient  # the style description, not its UI label, is used


def test_reel_id_path_is_bounded(tmp_path):
    with pytest.raises(ValueError, match="Invalid mini-reel id"):
        reels._reel_paths("../../secrets", str(tmp_path))
    folder, metadata, video = reels._reel_paths("20261002-123456-abcd1234", str(tmp_path))
    assert folder.parent == tmp_path.resolve()
    assert metadata.name == "mini_reel.json"
    assert video.name == "mini-reel.mp4"


def test_flow_generation_saves_result_and_never_generates_twice(tmp_path, monkeypatch):
    calls = {"generate": 0, "closed": 0}

    class FakeProvider:
        def __init__(self):
            pass

        def generate(self, shot, compiled, refs, out_path, vertical, dry_run):
            calls["generate"] += 1
            assert shot.duration_target == 8
            assert shot.model == "veo_fast"
            assert vertical is True and dry_run is False
            assert "says exactly" in compiled["prompt"]
            Path(out_path).write_bytes(b"x" * 4096)
            return {"path": out_path, "project_url": "https://flow.google.com/project/example",
                    "model": "veo_fast", "credits": 10}

        def close(self):
            calls["closed"] += 1

    monkeypatch.setattr(reels, "FlowBrowserProvider", FakeProvider)
    monkeypatch.setattr(reels, "_audio_stream_present", lambda _path: True)
    reel_id = "20261002-123456-abcd1234"
    prompt = reels.compose_flow_prompt(BRIEF, visual_style="miniature-diorama",
                                       language="en", audio_mode="flow-voiceover", model="veo_fast")
    result = reels.generate_flow_reel(
        reel_id, brief=BRIEF, flow_prompt=prompt, model="veo_fast",
        visual_style="miniature-diorama", audio_mode="flow-voiceover", language="en",
        output_root=str(tmp_path))
    assert result["status"] == "complete"
    assert result["audio_stream_present"] is True
    assert result["flow_project_url"].endswith("example")
    assert len(result["video_sha256"]) == 64
    assert calls == {"generate": 1, "closed": 1}

    reopened = reels.generate_flow_reel(reel_id, output_root=str(tmp_path))
    assert reopened["status"] == "complete"
    assert calls == {"generate": 1, "closed": 1}


def test_uncertain_flow_request_blocks_changed_prompt_and_other_generation(tmp_path, monkeypatch):
    calls = {"generate": 0}

    class PendingProvider:
        def generate(self, shot, compiled, refs, out_path, vertical, dry_run):
            calls["generate"] += 1
            Path(str(out_path) + ".flow-request.json").write_text(
                json.dumps({"status": "pending", "kind": "video", "project_url": "https://flow.google.com/project/example"}),
                encoding="utf-8")
            raise FlowRequestPending("Flow request is still processing")

        def close(self):
            pass

    monkeypatch.setattr(reels, "FlowBrowserProvider", PendingProvider)
    prompt = reels.compose_flow_prompt(BRIEF, visual_style="miniature-diorama",
                                       language="en", audio_mode="flow-voiceover", model="veo_fast")
    first_id = "20261002-123456-abcd1234"
    with pytest.raises(FlowRequestPending, match="still processing"):
        reels.generate_flow_reel(first_id, brief=BRIEF, flow_prompt=prompt,
                                 model="veo_fast", visual_style="miniature-diorama",
                                 audio_mode="flow-voiceover", language="en",
                                 output_root=str(tmp_path))
    assert calls["generate"] == 1

    changed_prompt = prompt + " A completely new ending."
    with pytest.raises(FlowRequestPending, match="unresolved Flow request"):
        reels.generate_flow_reel(first_id, brief=BRIEF, flow_prompt=changed_prompt,
                                 model="veo_fast", visual_style="miniature-diorama",
                                 audio_mode="flow-voiceover", language="en",
                                 output_root=str(tmp_path))
    second_id = "20261002-123456-efef1234"
    with pytest.raises(FlowRequestPending, match="[Aa]nother mini reel"):
        reels.generate_flow_reel(second_id, brief=BRIEF, flow_prompt=prompt,
                                 model="veo_fast", visual_style="miniature-diorama",
                                 audio_mode="flow-voiceover", language="en",
                                 output_root=str(tmp_path))
    assert calls["generate"] == 1


def test_pending_reel_listing_requires_a_saved_flow_journal(tmp_path):
    reel_id = "20261002-123456-abcd1234"
    folder, metadata_path, video_path = reels._reel_paths(reel_id, str(tmp_path))
    folder.mkdir(parents=True)
    metadata_path.write_text(json.dumps({"status": "flow_request_pending", "title": "A reel"}), encoding="utf-8")
    assert reels.list_pending_reels(str(tmp_path)) == []
    Path(str(video_path) + ".flow-request.json").write_text(json.dumps({"status": "pending"}), encoding="utf-8")
    pending = reels.list_pending_reels(str(tmp_path))
    assert len(pending) == 1 and pending[0]["reel_id"] == reel_id

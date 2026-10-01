from engine.planning.script import plan_content
from engine.planning.story_bible import build_bible
from engine.planning.director import create_production_plan
from engine.project.manifest import ProductionManifest
from engine.routing.credit_router import CreditRouter
from tests.conftest import fake_words

PRESET = {"prompt_vocabulary": ["cinematic"], "color_treatment": "warm",
          "lighting": "soft", "camera_behavior": "slow", "editing_pace": "calm",
          "music_style": "ambient", "shot_length": [4, 8], "negative": ["cartoon"]}


def test_plan_content_specific():
    p = plan_content("Why 5 AM wakeups fail", "education", 45, use_llm=False)
    assert len(p["hooks"]) >= 4 and p["hook"]
    assert len(p["beats"]) >= 4
    assert 90 <= p["words"] <= 140
    assert "5 am" in p["narration"].lower() or "5 AM" in p["narration"]
    assert "stay consistent" not in p["narration"].lower()
    ad = plan_content("Candles", "advertisement", 30, use_llm=False)
    assert ad["cta_kind"] == "buy"
    st = plan_content("A tale", "cinematic_story", 30, use_llm=False)
    assert st["cta_kind"] == "none"


def test_director_voice_timed_windows():
    words = fake_words(8, 4.0)
    total = words[-1]["end"]
    m = ProductionManifest(job_id="j", topic="t", target_seconds=32)
    bible = build_bible("test morning motivation", "motivation", PRESET)
    router = CreditRouter("FLOW_BALANCED")
    m = create_production_plan(m, "x", words, [{"name": "b"}], bible, PRESET, router, total)
    assert m.shots[0].coverage == "hook"
    assert m.shots[0].priority == "HERO"
    # windows contiguous and cover full narration
    assert m.shots[0].voice_start == 0.0
    assert abs(m.shots[-1].voice_end - total) < 0.01
    for a, b in zip(m.shots, m.shots[1:]):
        assert abs(a.voice_end - b.voice_start) < 0.01
    assert all(s.provider and s.model for s in m.shots)
    assert m.shots[1].start_frame == "{prev_end_frame:shot_001}"
    assert "CHARACTER_01" in bible["identity_block"]

import json
import os
import pytest

from engine.planning import script_engine
from engine.captions import group_words, get_word_timestamps, CaptionProviderError


def _good_list_plan():
    narration = (
        "Most people chase big changes, but success is usually built from repeatable choices. "
        "Habit one: plan tomorrow before today ends. Write the three tasks that matter most, so your morning starts with direction instead of reaction. "
        "Habit two: protect your body. Move every day, eat mostly simple food, and treat sleep as part of your performance, not leftover time. "
        "Habit three: learn something useful every day. Read, practice, or ask better questions, then apply one idea before collecting ten more. "
        "Habit four: review your progress. Once a week, look at what worked, what slipped, and what you will change next. "
        "Habit five: invest in relationships. Keep promises, listen well, and make time for people who help you grow. "
        "Pick one habit to begin this week, and tell me which one in the comments."
    )
    return {
        "angle": "five practical habits",
        "audience": "general adults",
        "hook": "Most people chase big changes, but success is usually built from repeatable choices.",
        "hooks": ["Most people chase big changes, but success is usually built from repeatable choices."],
        "beats": [
            {"name": "Habit 1: Plan tomorrow", "text": "Plan tomorrow before today ends.", "visual_intent": "planner on a desk", "emotion": "focused"},
            {"name": "Habit 2: Protect your body", "text": "Protect your body.", "visual_intent": "walking and sleep routine", "emotion": "energetic"},
            {"name": "Habit 3: Learn daily", "text": "Learn something useful every day.", "visual_intent": "reading then practicing", "emotion": "curious"},
            {"name": "Habit 4: Review progress", "text": "Review progress weekly.", "visual_intent": "weekly review page", "emotion": "reflective"},
            {"name": "Habit 5: Invest in relationships", "text": "Invest in relationships.", "visual_intent": "supportive conversation", "emotion": "warm"},
        ],
        "narration": narration,
        "cta": "Tell me which one in the comments.",
        "cta_kind": "soft",
    }


def test_list_topic_detection_and_qc_passes():
    spec = script_engine.detect_list_topic("5 habits for successful life")
    assert spec["count"] == 5
    plan = _good_list_plan()
    report = script_engine.script_quality_report(
        plan, "5 habits for successful life", "education", 60,
        target_words=len(plan["narration"].split()),
    )
    assert report["passed"] is True
    assert report["flags"] == []


def test_publish_qc_rejects_keyword_stuffing_and_workflow_drift():
    plan = _good_list_plan()
    plan["narration"] += " 5 habits for successful life. 5 habits for successful life. 5 habits for successful life. Managers automate the workflow with an API."
    report = script_engine.script_quality_report(
        plan, "5 habits for successful life", "education", 60,
        target_words=len(plan["narration"].split()),
    )
    assert report["passed"] is False
    joined = " | ".join(report["flags"])
    assert "keyword stuffing" in joined
    assert "off-topic" in joined


def test_explicit_script_provider_is_strict(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(script_engine, "_provider_available", lambda p: False)
    with pytest.raises(script_engine.ScriptProviderError):
        script_engine.generate_script_plan(
            "5 habits for successful life", "education", 60, "cinematic", "en",
            provider="groq", quality="publish",
        )


def test_explicit_groq_caption_provider_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"x" * 2048)
    with pytest.raises(CaptionProviderError):
        get_word_timestamps(str(audio), provider="groq", script_text="hello world", force=True)


def test_caption_groups_prefer_phrase_boundaries():
    words = [
        {"word": "Plan", "start": 0.0, "end": 0.2},
        {"word": "tomorrow", "start": 0.2, "end": 0.5},
        {"word": "before", "start": 0.5, "end": 0.7},
        {"word": "today", "start": 0.7, "end": 0.9},
        {"word": "ends.", "start": 0.9, "end": 1.2},
        {"word": "Then", "start": 1.25, "end": 1.45},
        {"word": "protect", "start": 1.45, "end": 1.7},
        {"word": "your", "start": 1.7, "end": 1.85},
        {"word": "energy.", "start": 1.85, "end": 2.1},
    ]
    groups = group_words(words)
    assert len(groups) == 2
    assert [w["word"] for w in groups[0]["words"]] == ["Plan", "tomorrow", "before", "today", "ends."]

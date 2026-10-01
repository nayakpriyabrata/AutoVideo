import json

from engine.planning import script_engine


def _outline():
    return {
        "angle": "five practical habits that compound",
        "audience": "adults building a balanced life",
        "hook": "Success is rarely one dramatic decision; it is usually five ordinary habits repeated well.",
        "hooks": ["Success is rarely one dramatic decision; it is usually five ordinary habits repeated well."],
        "beats": [
            {"name": "Habit 1: Plan tomorrow", "text": "Choose tomorrow's three priorities before today ends.", "visual_intent": "planner and pen at dusk", "emotion": "focused"},
            {"name": "Habit 2: Protect your body", "text": "Treat movement, food, and sleep as daily foundations.", "visual_intent": "morning walk and simple meal", "emotion": "energetic"},
            {"name": "Habit 3: Learn daily", "text": "Learn one useful idea and apply it the same day.", "visual_intent": "reading then practicing", "emotion": "curious"},
            {"name": "Habit 4: Review progress", "text": "Use a weekly review to correct small mistakes early.", "visual_intent": "weekly review page", "emotion": "reflective"},
            {"name": "Habit 5: Invest in relationships", "text": "Protect time for people who help you grow.", "visual_intent": "warm conversation", "emotion": "warm"},
        ],
        "cta": "Choose one habit and tell me which one you will start this week.",
        "cta_kind": "soft",
    }


def _narration():
    return (
        "Success is rarely one dramatic decision; it is usually five ordinary habits repeated well. "
        "Habit one: plan tomorrow before today ends. Write the three priorities that matter most, so your morning starts with direction instead of reaction. "
        "Habit two: protect your body. Walk, train, eat mostly simple food, and give sleep a fixed place in your schedule because energy supports every other goal. "
        "Habit three: learn something useful every day. Read a few pages, practice a skill, or ask a better question, then apply one idea before collecting another. "
        "Habit four: review your progress once a week. Notice what worked, what slipped, and what small adjustment will make the next week easier. "
        "Habit five: invest in relationships. Keep promises, listen carefully, and make regular time for people who challenge and support you. "
        "Choose one habit to begin this week, and tell me which one in the comments."
    )


def test_longform_publish_uses_two_stage_same_provider(monkeypatch):
    calls = []
    outline = _outline()
    narration = _narration()

    monkeypatch.setattr(script_engine, "_provider_available", lambda p: p == "groq")

    def fake_call(provider, model, system, user):
        calls.append((provider, system, user))
        if "compact valid JSON outline" in system:
            return json.dumps(outline)
        if "publish-ready YouTube narration writer" in system:
            # Initial narration and optional publish polish are both allowed.
            return json.dumps({"narration": narration, "cta": outline["cta"]})
        raise AssertionError(system)

    monkeypatch.setattr(script_engine, "_call_provider", fake_call)
    target = len(narration.split())
    plan = script_engine.generate_script_plan(
        "5 habits for a successful life", "education", 180, "cinematic", "en",
        provider="groq", model="groq-test", quality="publish", target_words=target,
    )
    assert plan is not None
    assert len(plan["beats"]) == 5
    assert plan["editorial_qc"]["passed"] is True
    assert "groq:groq-test" in plan["source"]
    assert any("compact valid JSON outline" in system for _, system, _ in calls)
    assert any("publish-ready YouTube narration writer" in system for _, system, _ in calls)


def test_longform_incomplete_first_narration_retries_without_planner(monkeypatch):
    calls = {"outline": 0, "narr": 0}
    outline = _outline()
    narration = _narration()
    monkeypatch.setattr(script_engine, "_provider_available", lambda p: p == "groq")

    def fake_call(provider, model, system, user):
        if "compact valid JSON outline" in system:
            calls["outline"] += 1
            return json.dumps(outline)
        if "publish-ready YouTube narration writer" in system:
            calls["narr"] += 1
            if calls["narr"] == 1:
                return json.dumps({"narration": "Too short."})
            return json.dumps({"narration": narration, "cta": outline["cta"]})
        raise AssertionError(system)

    monkeypatch.setattr(script_engine, "_call_provider", fake_call)
    target = len(narration.split())
    plan = script_engine.generate_script_plan(
        "5 habits for a successful life", "education", 180, "cinematic", "en",
        provider="groq", model="groq-test", quality="publish", target_words=target,
    )
    assert plan is not None
    assert calls["outline"] >= 2
    assert calls["narr"] >= 2
    assert "planner" not in plan["source"]


def test_openai_compatible_requests_large_completion_budget(monkeypatch):
    seen = []

    class Resp:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"choices": [{"message": {"content": '{"narration":"ok"}'}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.append(json)
        return Resp()

    monkeypatch.setattr(script_engine.requests, "post", fake_post)
    text = script_engine._openai_compatible(
        "https://example.invalid/v1", "k", "m", "system", "user", "groq"
    )
    assert text
    assert seen[0]["max_completion_tokens"] >= 4096
    assert seen[0]["response_format"] == {"type": "json_object"}

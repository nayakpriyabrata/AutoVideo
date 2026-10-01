import json
from engine.planning import script_engine


def _outline():
    return {
        "angle": "five practical winning habits",
        "audience": "adults",
        "hook": "Winners do not rely on motivation; they make five useful habits easier to repeat.",
        "hooks": ["Winners do not rely on motivation; they make five useful habits easier to repeat."],
        "beats": [
            {"name": f"Habit {i}: H{i}", "text": f"Practical habit {i}.",
             "visual_intent": f"visual {i}", "emotion": "focused"}
            for i in range(1, 6)
        ],
        "cta": "Choose one habit and share it in the comments.",
        "cta_kind": "soft",
    }


def _narration(words):
    parts = [
        "Winners do not rely on motivation; they make five useful habits easier to repeat.",
        "Habit one: plan the next day before the current one ends, so your morning begins with direction rather than reaction.",
        "Habit two: protect your physical energy with regular movement, simple food, and a consistent bedtime that supports clear thinking.",
        "Habit three: learn something useful every day, then apply one idea immediately so knowledge turns into practical skill.",
        "Habit four: review your week honestly, noticing what worked, what slipped, and what small adjustment will make the next week easier.",
        "Habit five: invest in relationships by keeping promises, listening carefully, and making time for people who help you grow.",
    ]
    extras = [
        "A written plan reduces unnecessary decisions and makes it easier to begin important work before distractions take over.",
        "A short walk can restore attention after a demanding block of work and creates a useful reset between responsibilities.",
        "Reading a few pages is enough when you pause to capture one lesson and practice it in a real situation.",
        "A weekly review reveals patterns that are easy to miss when every day feels busy and slightly different.",
        "Strong relationships are built through many small reliable actions, not only through occasional large gestures.",
        "Keeping the system simple makes consistency easier because you spend less time deciding how to begin.",
        "When a habit becomes part of the environment, it requires less willpower and becomes easier to repeat on difficult days.",
        "Progress becomes visible when you track one or two meaningful signals instead of measuring everything at once.",
        "The goal is not perfection; the goal is to make the next useful action obvious enough to start without negotiation.",
        "Over time, these ordinary choices compound because they improve the quality of your decisions as well as your energy.",
        "The strongest routine is one you can maintain during a busy week without needing ideal conditions or extraordinary motivation.",
        "Small improvements also protect momentum because a missed day becomes a temporary interruption instead of a reason to quit.",
        "Clear boundaries make good habits easier to protect when messages, meetings, and unexpected requests compete for attention.",
        "A useful habit should solve a recurring problem in your day rather than exist only because it sounds impressive.",
        "The best systems leave enough flexibility for real life while still protecting the actions that matter most.",
    ]
    i = 0
    text = " ".join(parts)
    while len(text.split()) < words - 12:
        text += " " + extras[i % len(extras)]
        i += 1
    text += " Choose one habit and share it in the comments."
    return text


def test_short_good_gemini_draft_is_repaired_instead_of_discarded(monkeypatch):
    outline = _outline()
    calls = {"outline": 0, "narr": 0, "length": 0}
    target = 300
    short = _narration(205)
    repaired = _narration(292)
    monkeypatch.setattr(script_engine, "_provider_available", lambda p: p == "gemini-web")

    def fake(provider, model, system, user):
        if "compact valid JSON outline" in system:
            calls["outline"] += 1
            return json.dumps(outline)
        if "precision YouTube narration length editor" in system:
            calls["length"] += 1
            return json.dumps({"narration": repaired, "cta": outline["cta"]})
        if "publish-ready YouTube narration writer" in system:
            calls["narr"] += 1
            return json.dumps({"narration": short, "cta": outline["cta"]})
        raise AssertionError(system)

    monkeypatch.setattr(script_engine, "_call_provider", fake)
    plan = script_engine.generate_script_plan(
        "5 habits winners build for a successful life", "education", 180,
        "cinematic", "en", provider="gemini-web", model="gemini-web",
        quality="publish", target_words=target,
    )
    assert plan is not None
    assert plan["editorial_qc"]["passed"] is True
    assert calls["outline"] == 1
    assert calls["length"] >= 1
    assert len(plan["narration"].split()) > len(short.split())


def test_clean_script_can_be_provisional_when_only_length_remains(monkeypatch):
    outline = _outline()
    short = _narration(205)
    monkeypatch.setattr(script_engine, "_provider_available", lambda p: p == "gemini-web")

    def fake(provider, model, system, user):
        if "compact valid JSON outline" in system:
            return json.dumps(outline)
        if "publish-ready YouTube narration writer" in system:
            return json.dumps({"narration": short, "cta": outline["cta"]})
        if "precision YouTube narration length editor" in system:
            return json.dumps({"narration": short, "cta": outline["cta"]})
        raise AssertionError(system)

    monkeypatch.setattr(script_engine, "_call_provider", fake)
    plan = script_engine.generate_script_plan(
        "5 habits winners build for a successful life", "education", 180,
        "cinematic", "en", provider="gemini-web", model="gemini-web",
        quality="publish", target_words=300,
    )
    assert plan is not None
    assert plan["editorial_qc"]["passed"] is True
    assert plan["editorial_qc"].get("timing_retime_required") is True

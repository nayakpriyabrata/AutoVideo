import json


def _browser(monkeypatch, responses):
    import engine.providers.gemini_web as gw

    browser = object.__new__(gw.GeminiWebBrowser)
    browser._page = type("Page", (), {"url": "https://gemini.google.com/app"})()
    monkeypatch.setattr(browser, "start_fresh_chat", lambda: None)
    monkeypatch.setattr(browser, "_fill_prompt", lambda prompt: None)
    monkeypatch.setattr(browser, "_submit", lambda: setattr(browser._page, "url", "https://gemini.google.com/app/test"))
    monkeypatch.setattr(browser, "_save_captured_response", lambda text: None)
    monkeypatch.setattr(browser, "_generation_in_progress", lambda: False)
    sequence = iter(responses)
    monkeypatch.setattr(browser, "_response_candidates", lambda: next(sequence, responses[-1]))
    return gw, browser


def test_complete_json_rejects_stable_thinking_card():
    from engine.providers.gemini_web import GeminiWebBrowser

    assert not GeminiWebBrowser._complete_json_response("Show thinking\nGemini is working on this")
    answer = json.dumps({"narration": "useful words " * 20, "cta": "Subscribe"})
    assert GeminiWebBrowser._complete_json_response(answer)
    clips = json.dumps({"candidates": [{"start": "00:10", "end": "00:40"}]})
    assert GeminiWebBrowser._complete_json_response(clips)


def test_ask_waits_for_complete_json_and_cleans_success(monkeypatch):
    answer = json.dumps({"narration": "complete narration " * 30, "cta": "Done"})
    responses = [[], ["Show thinking: working on your response"]] + [[answer]] * 6
    gw, browser = _browser(monkeypatch, responses)
    clock = {"now": 0.0}
    monkeypatch.setattr(gw.time, "time", lambda: clock["now"])
    monkeypatch.setattr(gw.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))
    monkeypatch.setenv("AUTOVIDEO_GEMINI_CHAT_CLEANUP", "delete-after-read")
    cleaned = []
    monkeypatch.setattr(browser, "_cleanup_submitted_chat", lambda: cleaned.append(True))

    assert browser.ask("Return JSON", timeout_seconds=30) == answer
    assert cleaned == [True]


def test_ask_retains_submitted_chat_when_no_complete_answer(monkeypatch):
    responses = [[], ["Show thinking: still not the final answer"]]
    gw, browser = _browser(monkeypatch, responses)
    clock = {"now": 0.0}
    monkeypatch.setattr(gw.time, "time", lambda: clock["now"])
    monkeypatch.setattr(gw.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))
    monkeypatch.setenv("AUTOVIDEO_GEMINI_CHAT_CLEANUP", "delete-after-read")
    cleaned = []
    monkeypatch.setattr(browser, "_cleanup_submitted_chat", lambda: cleaned.append(True))

    try:
        browser.ask("Return JSON", timeout_seconds=30)
        assert False, "expected incomplete response failure"
    except gw.GeminiWebUIChanged as exc:
        assert "no complete JSON response" in str(exc)
    assert cleaned == []

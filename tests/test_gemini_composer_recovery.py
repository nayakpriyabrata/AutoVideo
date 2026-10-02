import pytest


def test_prompt_box_chooses_visible_accessible_editable_textbox():
    from engine.providers.gemini_web import GeminiWebBrowser

    class Candidate:
        def __init__(self, visible, editable, label=""):
            self.visible = visible
            self.editable = editable
            self.label = label

        def get_attribute(self, name):
            return self.label if name == "aria-label" else ""

        def is_visible(self, timeout=100):
            return self.visible

        def is_editable(self, timeout=100):
            return self.editable

    class Matches:
        def __init__(self, values):
            self.values = values

        def count(self):
            return len(self.values)

        def nth(self, index):
            return self.values[index]

    hidden = Candidate(False, True, "Gemini prompt")
    visible = Candidate(True, True, "Message Gemini")

    class Page:
        def locator(self, selector):
            if selector == "[role='textbox']":
                return Matches([hidden, visible])
            return Matches([])

        def get_by_role(self, role, **kwargs):
            return Matches([])

    browser = object.__new__(GeminiWebBrowser)
    browser._page = Page()
    browser._resolve = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fallback resolver used"))
    assert browser._prompt_box() is visible


def test_fresh_chat_wait_is_bounded_and_recovers_when_composer_appears(monkeypatch):
    import engine.providers.gemini_web as gw

    browser = object.__new__(gw.GeminiWebBrowser)
    browser.ui = {"gemini_url": "https://gemini.google.com/app"}

    class Page:
        url = "https://gemini.google.com/app"

        def __init__(self):
            self.navigations = []

        def goto(self, url, **kwargs):
            self.navigations.append(url)
            self.url = url

    page = Page()
    browser._page = page
    found = object()
    probes = {"count": 0}

    def prompt_box(timeout_ms=1200):
        probes["count"] += 1
        return found if probes["count"] >= 3 else None

    monkeypatch.setattr(browser, "_prompt_box", prompt_box)
    monkeypatch.setenv("GEMINI_WEB_COMPOSER_WAIT_SECONDS", "10")
    clock = {"now": 0.0}
    monkeypatch.setattr(gw.time, "time", lambda: clock["now"])
    monkeypatch.setattr(gw.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))

    assert browser.start_fresh_chat() is None
    assert page.navigations == ["https://gemini.google.com/app"]
    assert probes["count"] == 3


def test_fresh_chat_reports_composer_not_ready_without_submission(monkeypatch):
    import engine.providers.gemini_web as gw

    browser = object.__new__(gw.GeminiWebBrowser)
    browser.ui = {"gemini_url": "https://gemini.google.com/app"}

    class Page:
        url = "https://gemini.google.com/app"

        def goto(self, url, **kwargs):
            self.url = url

    browser._page = Page()
    monkeypatch.setattr(browser, "_prompt_box", lambda timeout_ms=1200: None)
    monkeypatch.setattr(browser, "_click_visible_new_chat", lambda: False)
    monkeypatch.setenv("GEMINI_WEB_COMPOSER_WAIT_SECONDS", "5")
    clock = {"now": 0.0}
    monkeypatch.setattr(gw.time, "time", lambda: clock["now"])
    monkeypatch.setattr(gw.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))

    with pytest.raises(gw.GeminiWebComposerNotReady, match="No prompt was submitted"):
        browser.start_fresh_chat()


def test_gemini_ask_refuses_retained_old_chat_before_filling_prompt(monkeypatch):
    import engine.providers.gemini_web as gw

    browser = object.__new__(gw.GeminiWebBrowser)
    browser._page = type("Page", (), {"url": "https://gemini.google.com/app/old-chat"})()
    monkeypatch.setattr(browser, "start_fresh_chat", lambda: None)
    monkeypatch.setattr(browser, "_fill_prompt", lambda prompt: (_ for _ in ()).throw(AssertionError("prompt filled")))

    with pytest.raises(gw.GeminiWebUIChanged, match="refusing to submit or delete"):
        browser.ask("draft this")


def test_composer_failure_is_not_retried_three_times(monkeypatch):
    import engine.planning.script_engine as script_engine

    calls = []

    def fail(*args, **kwargs):
        calls.append(True)
        raise script_engine.ScriptProviderError("Gemini Web is not ready: composer did not appear")

    monkeypatch.setattr(script_engine, "_provider_available", lambda provider: True)
    monkeypatch.setattr(script_engine, "_call_provider", fail)
    with pytest.raises(script_engine.ScriptProviderError, match="not ready"):
        script_engine.generate_script_plan(
            "A useful topic", "educational", 30, "warm", "en",
            provider="gemini-web", quality="high")
    assert len(calls) == 1


def test_gemini_web_auth_and_composer_errors_map_to_actionable_provider_error(monkeypatch):
    import engine.providers.gemini_web as gemini_web
    import engine.planning.script_engine as script_engine

    monkeypatch.setattr(
        gemini_web, "gemini_web_generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            gemini_web.GeminiWebComposerNotReady("check the visible composer")))
    with pytest.raises(script_engine.ScriptProviderError, match="check the visible composer"):
        script_engine._call_provider("gemini-web", "gemini-web", "system", "user")

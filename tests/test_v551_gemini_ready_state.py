def test_flow_state_exposes_ready_for_gemini_web():
    from engine.providers.base import FlowState
    assert FlowState.READY.value == "READY"


def test_gemini_post_connect_can_set_ready(monkeypatch):
    from engine.providers.base import FlowState
    from engine.providers.gemini_web import GeminiWebBrowser

    b = object.__new__(GeminiWebBrowser)
    b.state = FlowState.IDLE
    b.state_cb = None
    b.ui = {"gemini_url": "https://gemini.google.com/app"}

    class Page:
        url = "https://gemini.google.com/app"
        def goto(self, *a, **k):
            self.url = a[0]

    b._page = Page()
    monkeypatch.setattr(b, "_prompt_box", lambda timeout_ms=1200: object())
    assert b._post_connect(30) is True
    assert b.state is FlowState.READY

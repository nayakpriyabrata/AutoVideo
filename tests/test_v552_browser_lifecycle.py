import asyncio


def test_edge_async_bridge_works_inside_running_loop():
    from engine.audio.tts import _run_async_blocking

    async def add(a, b):
        await asyncio.sleep(0)
        return a + b

    async def outer():
        return _run_async_blocking(add, 2, 3)

    assert asyncio.run(outer()) == 5


def test_flow_provider_discards_half_started_bridge(monkeypatch):
    import engine.providers.flow_browser as fb

    calls = {"n": 0}

    class FakeBridge:
        def __init__(self, headless=False):
            self.headless = headless
            self._page = None
            self.closed = False

        def ensure_session(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("first launch failed")
            self._page = object()

        def close(self):
            self.closed = True
            self._page = None

    monkeypatch.setattr(fb, "FlowBrowser", FakeBridge)
    p = fb.FlowBrowserProvider(headless=True)

    try:
        p._ensure()
        assert False, "first launch should fail"
    except RuntimeError as e:
        assert "first launch failed" in str(e)
    assert p.bridge is None

    b = p._ensure()
    assert b is p.bridge
    assert b._page is not None
    assert calls["n"] == 2


def test_plan_only_help_is_truthful():
    from pathlib import Path
    text = Path("cli.py").read_text(encoding="utf-8")
    assert "Create the job configuration only" in text
    assert "plan-only created the job configuration only" in text

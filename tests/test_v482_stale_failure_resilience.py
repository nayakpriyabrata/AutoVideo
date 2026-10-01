from engine.providers.flow_browser import FlowBrowser


class _Page:
    def __init__(self, body):
        self.body = body
    def inner_text(self, sel):
        return self.body


def _browser(body, baseline=None):
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = _Page(body)
    b.ui = {"actions": {
        "quota_texts": [],
        "failure_texts": ["generation failed", "blocked", "Something went wrong"],
    }}
    b._agent_failure_baseline = baseline or {}
    return b


def test_v482_stale_failure_from_old_turn_is_ignored():
    body = "Old turn: generation failed. New turn: creating image now..."
    b = _browser(body, {"generation failed": 1, "blocked": 0, "something went wrong": 0})
    assert b.detect_failure() is None


def test_v482_new_failure_after_submit_is_detected():
    body = "Old turn: generation failed. New turn: generation failed."
    b = _browser(body, {"generation failed": 1, "blocked": 0, "something went wrong": 0})
    assert b.detect_failure() == "generation failed"


def test_v482_new_progress_after_new_failure_wins():
    body = "Old: generation failed. New: generation failed. Try again. creating image"
    b = _browser(body, {"generation failed": 1, "blocked": 0, "something went wrong": 0})
    assert b.detect_failure() is None

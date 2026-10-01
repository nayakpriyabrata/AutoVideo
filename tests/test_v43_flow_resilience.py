from pathlib import Path
from types import SimpleNamespace

from engine.providers.flow_browser import FlowBrowser


class TextLoc:
    def __init__(self, visible=True, on_click=None):
        self.visible = visible
        self.clicked = 0
        self.first = self
        self.on_click = on_click
    def is_visible(self, timeout=0):
        return self.visible
    def click(self, **kwargs):
        self.clicked += 1
        if self.on_click:
            self.on_click()
    def locator(self, selector):
        return self
    def count(self):
        return 1 if self.visible else 0
    def get_attribute(self, name):
        return None


class RowOnlyPage:
    def __init__(self, body="costing 7 credits"):
        self.body = body
        self.approve = TextLoc(True, self._approved)
    def _approved(self):
        self.body = "Generating video..."
        self.approve.visible = False
    def inner_text(self, sel):
        return self.body
    def get_by_role(self, role, name=None):
        return TextLoc(False)
    def get_by_text(self, text, exact=False):
        return self.approve if text == "Approve" else TextLoc(False)
    def wait_for_timeout(self, ms):
        pass
    def evaluate(self, js):
        return True


def test_v43_approval_clicks_nonsemantic_approve_row():
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = RowOnlyPage("Would you like me to kick off this 1 video generation, costing 7 credits?")
    b.ui = {"actions": {"agent_confirmation_buttons": ["Approve", "Always approve"]}}
    assert b.confirm_agent_generation(timeout_s=1, approval="once", max_credits=10)
    assert b._page.approve.clicked >= 1
    assert b.last_agent_confirmation["cost"] == 7


def test_v43_cached_project_exits_editor_before_reuse():
    b = FlowBrowser.__new__(FlowBrowser)
    b._project_ready = "P"
    b._page = SimpleNamespace(url="https://flow.google.com/project/x/edit/y")
    calls = {"done": 0}
    def leave(timeout_ms=0):
        calls["done"] += 1
        b._page.url = "https://flow.google.com/project/x"
        b._project_ready = None
        return True
    b.return_to_project = leave
    b._composer_visible = lambda timeout_ms=0: True
    b.dismiss_onboarding = lambda rounds=3: 0
    b.ensure_project("P")
    assert calls["done"] == 1


class FakeDownload:
    def __init__(self):
        self.saved = None
    def save_as(self, path):
        Path(path).write_bytes(b"fake-image")
        self.saved = path


class ExpectDownload:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.value = FakeDownload()
    def __enter__(self):
        return self
    def __exit__(self, typ, value, tb):
        if self.should_fail:
            raise TimeoutError("no direct download; menu opened")
        return False


class EmptyMedia:
    def count(self): return 0


class DownloadPage:
    def __init__(self):
        self.url = "https://flow.google.com/project/x/edit/y"
        self.calls = 0
    def locator(self, sel):
        return EmptyMedia()
    def expect_download(self, timeout=0):
        self.calls += 1
        return ExpectDownload(should_fail=self.calls == 1)
    def wait_for_timeout(self, ms): pass


def test_v43_download_uses_original_menu_then_exits_editor(tmp_path):
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = DownloadPage()
    b.ui = {"timeouts": {"download": 10}}
    button = TextLoc(True)
    option = TextLoc(True)
    b._resolve = lambda action, timeout_ms=0: button
    b._try_resolve = lambda action, timeout_ms=0: option if action == "download_original_option" else None
    exited = {"n": 0}
    b.return_to_project = lambda timeout_ms=0: exited.__setitem__("n", exited["n"] + 1) or True
    b.network_issue_detected = lambda err=None: False
    out = tmp_path / "frame.jpg"
    assert b.download_latest_asset(str(out)) == str(out)
    assert out.exists()
    assert button.clicked == 1
    assert option.clicked == 1
    assert exited["n"] == 1


def test_v43_network_error_classifier():
    assert FlowBrowser._looks_like_network_error("net::ERR_INTERNET_DISCONNECTED")
    assert FlowBrowser._looks_like_network_error("ERR_NETWORK_CHANGED")
    assert not FlowBrowser._looks_like_network_error("UI element not found: New project")


class NoApprovePage(RowOnlyPage):
    def __init__(self):
        super().__init__("Would you like me to kick off this 1 video generation, costing 7 credits?")
        self.approve.visible = False
    def get_by_text(self, text, exact=False):
        return TextLoc(False)


def test_v43_historical_credit_text_without_clickable_approval_does_not_block():
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = NoApprovePage()
    b.ui = {"actions": {"agent_confirmation_buttons": ["Approve", "Always approve"]}}
    assert not b.confirm_agent_generation(timeout_s=1, approval="once", max_credits=10)
    assert b.last_agent_confirmation["blocked"] is False
    assert "no clickable" in b.last_agent_confirmation["reason"]

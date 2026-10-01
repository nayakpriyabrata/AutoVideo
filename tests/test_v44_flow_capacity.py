from pathlib import Path

import pytest

from engine.providers.flow_browser import (
    FlowBrowser,
    FlowBrowserClosedError,
    FlowServiceBusy,
)


class Clickable:
    def __init__(self, on_click=None, visible=True):
        self.on_click = on_click
        self.visible = visible
        self.first = self
        self.clicked = 0

    def is_visible(self, timeout=0):
        return self.visible

    def click(self):
        self.clicked += 1
        if self.on_click:
            self.on_click()


class CapacityPage:
    def __init__(self, clears=True):
        self.body = "The agent is experiencing high demand. Please try again later. Try again"
        self.clears = clears
        self.retry = Clickable(self._retry)

    def _retry(self):
        if self.clears:
            self.body = "Generating image..."

    def inner_text(self, selector):
        return self.body

    def get_by_role(self, role, name=None):
        if role == "button":
            return self.retry
        return Clickable(visible=False)

    def get_by_text(self, text, exact=False):
        if text in ("Try again", "Retry"):
            return self.retry
        return Clickable(visible=False)

    def wait_for_timeout(self, ms):
        pass


def make_capacity_browser(clears=True):
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = CapacityPage(clears=clears)
    b.ui = {
        "actions": {
            "service_busy_texts": [
                "agent is experiencing high demand",
                "please try again later",
            ],
            "service_retry_buttons": ["Try again", "Retry"],
            "service_busy_retry_delays": [0, 0, 0],
            "failure_texts": ["Something went wrong", "generation failed"],
            "quota_texts": ["out of credits"],
        },
        "timeouts": {
            "generation": 10,
            "poll_interval": 0.01,
            "service_busy_wait": 5,
            "service_busy_retries": 3,
        },
    }
    b.state_cb = None
    b.state = None
    return b


def test_v44_detects_agent_high_demand_separately():
    b = make_capacity_browser()
    assert b.detect_service_busy() in {"agent is experiencing high demand", "please try again later"}
    # Generic failure detection must not classify the Try-again capacity card.
    assert b.detect_failure() is None


def test_v44_stale_capacity_message_is_ignored_when_newer_generation_started():
    b = make_capacity_browser(clears=False)
    b._page.body = (
        "The agent is experiencing high demand. Please try again later. Try again\n"
        "Generating image..."
    )
    assert b.detect_service_busy() is None


def test_v44_capacity_retry_clicks_try_again_without_normal_frame_retry():
    b = make_capacity_browser(clears=True)
    assert b.recover_service_busy(max_wait_s=5, max_retries=2) is True
    assert b._page.retry.clicked == 1
    assert b.detect_service_busy() is None


def test_v44_agent_wait_continues_after_capacity_recovery():
    b = make_capacity_browser(clears=True)
    b.media_asset_count = lambda: 1
    assert b.wait_for_agent_generation(
        before_assets=0,
        timeout_s=2,
        service_busy_wait_s=5,
        service_busy_retries=2,
    ) is True
    assert b._page.retry.clicked == 1


def test_v44_persistent_capacity_raises_dedicated_error():
    b = make_capacity_browser(clears=False)
    with pytest.raises(FlowServiceBusy):
        b.wait_for_agent_generation(
            before_assets=0,
            timeout_s=2,
            service_busy_wait_s=5,
            service_busy_retries=2,
        )
    assert b._page.retry.clicked == 2


def test_v44_target_closed_classifier():
    assert FlowBrowser._looks_like_browser_closed_error(
        "TargetClosedError: Page.wait_for_timeout: Target page, context or browser has been closed"
    )
    assert not FlowBrowser._looks_like_browser_closed_error("UI element not found: Download")


class EmptyMedia:
    def count(self):
        return 0


class ClosedDownloadContext:
    value = None

    def __enter__(self):
        return self

    def __exit__(self, typ, value, tb):
        raise RuntimeError("Target page, context or browser has been closed")


class ClosedDownloadPage:
    def __init__(self):
        self.url = "https://flow.google.com/project/x/edit/y"

    def locator(self, selector):
        return EmptyMedia()

    def expect_download(self, timeout=0):
        return ClosedDownloadContext()

    def wait_for_timeout(self, ms):
        raise RuntimeError("Target page, context or browser has been closed")

    def get_by_text(self, text, exact=False):
        return Clickable(visible=False)


def test_v44_download_surfaces_browser_closed_as_recoverable(tmp_path):
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = ClosedDownloadPage()
    b.ui = {"timeouts": {"download": 10}}
    b._resolve = lambda action, timeout_ms=0: Clickable()
    b._try_resolve = lambda action, timeout_ms=0: None
    b.return_to_project = lambda timeout_ms=0: False
    b.network_issue_detected = lambda err=None: False

    with pytest.raises(FlowBrowserClosedError):
        b.download_latest_asset(str(tmp_path / "frame.jpg"))

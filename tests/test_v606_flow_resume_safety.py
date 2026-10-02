"""Resume attaches to the existing Flow tab and keeps pending video diagnostics accurate."""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from engine.providers.flow_browser import FlowBrowser, FlowBrowserProvider, FlowRequestPending


class Page:
    def __init__(self, url="about:blank"):
        self.url = url
        self.closed = False
        self.goto_calls = []

    def is_closed(self):
        return self.closed

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        self.url = url


class Context:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.new_page_calls = 0

    def new_page(self):
        self.new_page_calls += 1
        page = Page()
        self.pages.append(page)
        return page


def attach_cdp(context):
    browser = FlowBrowser.__new__(FlowBrowser)
    cdp = SimpleNamespace(contexts=[context])
    browser._pw = SimpleNamespace(chromium=SimpleNamespace(
        connect_over_cdp=lambda *_args, **_kwargs: cdp))
    browser._isolated_worker = False
    browser._owns_page = False
    browser._owns_guard_page = False
    browser._guard_page = None
    browser._own_context = False
    browser._ctx = None
    browser._page = None
    browser._connect_cdp("http://127.0.0.1:9222")
    return browser


def test_resume_prefers_existing_flow_tab_over_first_blank_or_unrelated_tab():
    blank = Page("about:blank")
    mail = Page("https://mail.google.com/")
    project = Page("https://flow.google.com/project/saved-project")
    context = Context([blank, mail, project])

    browser = attach_cdp(context)

    assert browser._page is project
    assert browser._owns_page is False
    assert context.new_page_calls == 0
    assert blank.goto_calls == []
    assert mail.goto_calls == []


def test_resume_reuses_one_existing_blank_tab_instead_of_opening_another():
    mail = Page("https://mail.google.com/")
    blank = Page("about:blank")
    context = Context([mail, blank])

    browser = attach_cdp(context)

    assert browser._page is blank
    assert browser._owns_page is False
    assert context.new_page_calls == 0


def test_resume_opens_a_dedicated_tab_instead_of_navigating_an_unrelated_page():
    mail = Page("https://mail.google.com/")
    context = Context([mail])

    browser = attach_cdp(context)

    assert browser._page not in (mail,)
    assert browser._owns_page is False  # retain one reusable tab in the user's CDP context
    assert context.new_page_calls == 1
    assert mail.goto_calls == []

    opened_flow_tab = browser._page
    browser._set = lambda _state: None
    browser.close()
    assert not opened_flow_tab.closed


def test_post_connect_preserves_an_existing_flow_project_route():
    project = Page("https://flow.google.com/project/saved-project")
    browser = FlowBrowser.__new__(FlowBrowser)
    browser._page = project
    browser.ui = {"flow_url": "https://flow.google.com/"}
    browser._set = lambda _state: None

    assert browser._post_connect(visible_login_seconds=2) is True
    assert project.goto_calls == []
    assert project.url.endswith("/saved-project")


def test_post_connect_navigates_a_reused_blank_tab_to_flow():
    blank = Page("about:blank")
    browser = FlowBrowser.__new__(FlowBrowser)
    browser._page = blank
    browser.ui = {"flow_url": "https://flow.google.com/"}
    browser._set = lambda _state: None

    assert browser._post_connect(visible_login_seconds=2) is True
    assert blank.goto_calls == ["https://flow.google.com/"]


def test_recovery_does_not_spawn_duplicate_tab_when_exact_project_is_still_loading():
    project = Page("https://flow.google.com/project/saved-project")
    context = Context([project])
    browser = FlowBrowser.__new__(FlowBrowser)
    browser._ctx = context
    browser._page = None
    browser._owns_page = False
    browser._guard_page = None
    browser._owns_guard_page = False
    browser._project_url = "https://flow.google.com/project/saved-project"
    browser._isolated_worker = False
    browser._composer_visible = lambda _timeout: False

    assert browser.recover_project_page("https://flow.google.com/project/saved-project", timeout_ms=0) is False
    assert browser._page is project
    assert context.new_page_calls == 0


def test_pending_video_error_includes_provider_cause_and_video_specific_recovery(tmp_path):
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    provider.bridge = None
    output = tmp_path / "mini-reel.mp4"

    def submitted_video(_shot, _compiled, _refs, out_path, _vertical, dry_run=False):
        assert dry_run is False
        Path(str(out_path) + ".flow-request.json").write_text(json.dumps({
            "status": "pending", "kind": "video",
            "project_url": "https://flow.google.com/project/saved-project",
            "signature": "", "baseline": [],
        }), encoding="utf-8")
        return {"path": None, "error": "Flow Agent generation did not reach a completed video"}

    provider._generate_video_once = submitted_video
    shot = SimpleNamespace(shot_id="mini_reel_1", model="veo_fast")
    compiled = {"prompt": "one short video", "project": "Mini Reel"}

    with pytest.raises(FlowRequestPending) as caught:
        provider._guarded_generation_once(shot, compiled, {}, str(output), True, False, "video")

    message = str(caught.value)
    assert "Flow video request is saved" in message
    assert "Flow adapter reported: Flow Agent generation did not reach a completed video" in message
    assert "Do not manually associate a different MP4 or click Generate again" in message
    assert "No manual MP4 step is required for an image request" not in message
    assert Path(str(output) + ".recovery.json").is_file()


def test_pending_image_error_still_names_exact_image_recovery(tmp_path):
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    provider.bridge = None
    output = tmp_path / "frame.png"

    def submitted_image(_shot, _compiled, out_path, _vertical, dry_run=False):
        assert dry_run is False
        Path(str(out_path) + ".flow-request.json").write_text(json.dumps({
            "status": "pending", "kind": "image",
            "project_url": "https://flow.google.com/project/saved-project",
            "signature": "", "baseline": [],
        }), encoding="utf-8")
        return {"path": None, "error": "Flow image did not reach a completed state"}

    provider._generate_image_once = submitted_image
    shot = SimpleNamespace(shot_id="shot_1", model="veo_fast")
    compiled = {"prompt": "one still image", "project": "Production"}

    with pytest.raises(FlowRequestPending) as caught:
        provider._guarded_generation_once(shot, compiled, {}, str(output), True, False, "image")

    message = str(caught.value)
    assert "Flow image request is saved" in message
    assert "recover this exact image" in message
    assert "MP4" not in message

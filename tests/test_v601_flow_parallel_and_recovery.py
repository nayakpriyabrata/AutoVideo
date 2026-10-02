from types import SimpleNamespace as NS

from engine.providers.flow_browser import FlowBrowser, FlowBrowserClosedError


def test_parallel_cdp_worker_opens_own_tab_and_does_not_replace_user_tab():
    class Page:
        def __init__(self, url="about:blank"):
            self.url = url
            self.closed = False

        def is_closed(self):
            return self.closed

        def close(self):
            self.closed = True

    user_page = Page("https://flow.google.com/project/user")
    worker_page = Page()

    class Context:
        pages = [user_page]

        def new_page(self):
            self.pages.append(worker_page)
            return worker_page

        def close(self):
            raise AssertionError("worker must not close a shared CDP context")

    context = Context()
    browser = FlowBrowser.__new__(FlowBrowser)
    browser._pw = NS(chromium=NS(connect_over_cdp=lambda *a, **k: NS(contexts=[context])),
                     stop=lambda: None)
    browser._isolated_worker = True
    browser._owns_page = False
    browser._owns_guard_page = False
    browser._guard_page = None
    browser._own_context = False

    browser._connect_cdp("http://127.0.0.1:9222")
    assert browser._page is worker_page
    assert browser._page is not user_page
    assert browser._owns_page is True

    browser._set = lambda state: None
    browser.state = None
    browser.close()
    assert worker_page.closed
    assert not user_page.closed


def test_recover_worker_never_adopts_another_workers_flow_tab():
    other = NS(url="https://flow.google.com/project/other", is_closed=lambda: False)
    new_page = NS(url="about:blank", is_closed=lambda: False,
                  goto=lambda url, **kwargs: setattr(new_page, "url", url),
                  wait_for_timeout=lambda ms: None)

    class Context:
        pages = [other]

        def new_page(self):
            self.pages.append(new_page)
            return new_page

    browser = FlowBrowser.__new__(FlowBrowser)
    browser._ctx = Context()
    browser._isolated_worker = True
    browser._page = NS(is_closed=lambda: True)
    browser._owns_page = True
    browser._guard_page = None
    browser._project_url = None

    assert browser._adopt_live_flow_page("https://flow.google.com/project/worker")
    assert browser._page is new_page
    assert browser._page.url.endswith("/worker")
    assert browser._page is not other


def test_recovery_waits_for_exact_recorded_asset_not_any_gallery_tile():
    page = NS(wait_for_timeout=lambda ms: None)
    browser = FlowBrowser.__new__(FlowBrowser)
    browser._page = page
    scans = iter([
        [{"sig": "IMG|old|old|image|640|360"}],
        [],
        [{"sig": "IMG|target|new|image|640|360"}],
    ])
    browser.media_assets = lambda: next(scans)

    result = browser._wait_for_media_signature(
        "IMG|target|new|image|320|180", timeout_ms=1000)

    assert result["sig"] == "IMG|target|new|image|640|360"


def test_exact_recovery_times_out_without_substituting_a_different_tile():
    browser = FlowBrowser.__new__(FlowBrowser)
    browser._page = NS(wait_for_timeout=lambda ms: None)
    browser.media_assets = lambda: [{"sig": "IMG|other|old|image|640|360"}]

    assert browser._wait_for_media_signature(
        "IMG|expected|new|image|640|360", timeout_ms=0) is None


def test_media_gallery_browser_close_is_not_treated_as_asset_absence():
    browser = FlowBrowser.__new__(FlowBrowser)

    def fail():
        raise FlowBrowserClosedError("target page has been closed")

    browser.media_assets = fail
    try:
        browser._wait_for_media_signature("IMG|expected|new|image|640|360", timeout_ms=500)
    except FlowBrowserClosedError:
        pass
    else:
        raise AssertionError("browser closure must trigger recovery, not an absent-asset decision")


def test_parallel_flow_pending_request_never_falls_back_or_submits_elsewhere(
        monkeypatch, tmp_path):
    from pathlib import Path
    import engine.providers.flow_browser as flow_module
    import engine.providers.image_provider as image_module
    from engine.factory import Factory
    from engine.project.manifest import Shot
    from engine.providers.flow_browser import FlowRequestPending

    seen = {"free": 0, "paused": None}

    class Browser:
        def ensure_project(self, project, project_url=None):
            return None

        def current_project_url(self):
            return "https://flow.google.com/project/worker-1"

    class FlowProvider:
        def __init__(self, **kwargs):
            pass

        def _ensure(self):
            return Browser()

        def generate_image(self, *args, **kwargs):
            raise FlowRequestPending("recorded image download is pending")

        def close(self):
            pass

    class FreeProvider:
        def generate_image(self, *args, **kwargs):
            seen["free"] += 1
            raise AssertionError("pending Flow requests must not be replaced by free output")

    monkeypatch.setattr(flow_module, "FlowBrowserProvider", FlowProvider)
    monkeypatch.setattr(flow_module, "PROFILE_DIR", str(tmp_path / "no-profile"))
    monkeypatch.setattr(image_module, "ImageProvider", FreeProvider)

    factory = Factory(outputs=str(tmp_path / "outputs"), db_path=str(tmp_path / "jobs.db"))
    job = factory.create_job("pending parallel", profile="FLOW_ECONOMY", images_per_shot=1)
    manifest = factory.pm.load_manifest(job)
    manifest.shots = [Shot(shot_id="shot_001", compiled_prompt="one image")]
    factory.pm.save_manifest(manifest)
    factory._is_valid_image_file = lambda path: Path(path).is_file()

    def pause(_manifest, shot_id, error, project_url=""):
        seen["paused"] = (shot_id, project_url, str(error))
        raise RuntimeError("paused safely")

    factory._pause_pending_flow = pause
    refs = NS(add=lambda *args: None)

    import pytest
    with pytest.raises(RuntimeError, match="paused safely"):
        factory._generate_scene_images_parallel(
            manifest, factory.pm.dirs(job), refs, True, 1, lambda *args: None,
            {"flow_image_workers": 1}, 1)

    assert seen["free"] == 0
    assert seen["paused"][0] == "shot_001"
    assert seen["paused"][1] == "https://flow.google.com/project/worker-1"

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


def test_parallel_flow_pending_request_pauses_when_user_opts_in(
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
            {"flow_image_workers": 1, "flow_pause_on_unresolved_request": True}, 1)

    assert seen["free"] == 0
    assert seen["paused"][0] == "shot_001"
    assert seen["paused"][1] == "https://flow.google.com/project/worker-1"


def test_parallel_flow_pending_image_uses_free_fallback_by_default(
        monkeypatch, tmp_path):
    import json
    from pathlib import Path
    import engine.providers.flow_browser as flow_module
    import engine.providers.image_provider as image_module
    import engine.qc.video_qc as qc_module
    from engine.factory import Factory
    from engine.project.manifest import Shot
    from engine.providers.flow_browser import FlowRequestPending

    seen = {"free": 0, "paused": 0}
    project_url = "https://flow.google.com/project/worker-1"

    class Browser:
        def ensure_project(self, project, project_url=None):
            return None

        def current_project_url(self):
            return project_url

    class FlowProvider:
        def __init__(self, **kwargs):
            pass

        def _ensure(self):
            return Browser()

        def generate_image(self, _shot, compiled, out, _vertical, **_kwargs):
            Path(out + ".flow-request.json").write_text(json.dumps({
                "status": "pending", "kind": "image", "project_url": compiled["project_url"],
                "baseline": ["old-image"], "signature": "", "submitted_at": 1,
                "request_hash": "saved-request",
            }))
            raise FlowRequestPending("recorded image has no unique exact asset")

        def close(self):
            pass

    class FreeProvider:
        def generate_image(self, _shot, _compiled, out, _vertical, **_kwargs):
            seen["free"] += 1
            Path(out).write_bytes(b"free-image-placeholder")
            return {"path": out}

    monkeypatch.setattr(flow_module, "FlowBrowserProvider", FlowProvider)
    monkeypatch.setattr(flow_module, "PROFILE_DIR", str(tmp_path / "no-profile"))
    monkeypatch.setattr(image_module, "ImageProvider", FreeProvider)
    monkeypatch.setattr(qc_module, "score_image", lambda _path: {"overall": 1})

    factory = Factory(outputs=str(tmp_path / "outputs"), db_path=str(tmp_path / "jobs.db"))
    job = factory.create_job("default parallel fallback", profile="FLOW_ECONOMY",
                             images_per_shot=1, flow_pause_on_unresolved_request=False)
    manifest = factory.pm.load_manifest(job)
    manifest.shots = [Shot(shot_id="shot_001", compiled_prompt="one image")]
    factory.pm.save_manifest(manifest)
    factory._is_valid_image_file = lambda path: Path(path).is_file()
    factory._pause_pending_flow = lambda *_a, **_k: seen.__setitem__("paused", seen["paused"] + 1)

    factory._generate_scene_images_parallel(
        manifest, factory.pm.dirs(job), NS(add=lambda *args: None), True, 1,
        lambda *args: None, {"flow_image_workers": 1,
                            "flow_pause_on_unresolved_request": False}, 1)

    output = Path(factory.pm.dirs(job)["flow"]) / "shots" / "shot_001" / "images" / "img_01.jpg"
    archived = Path(str(output) + ".flow-request.fallback.json")
    assert seen == {"free": 1, "paused": 0}
    assert output.is_file() and archived.is_file()
    assert not Path(str(output) + ".flow-request.json").exists()
    assert json.loads(archived.read_text())["status"] == "abandoned_for_free_image_fallback"

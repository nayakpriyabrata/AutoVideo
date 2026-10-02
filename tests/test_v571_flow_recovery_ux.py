from __future__ import annotations

from pathlib import Path

import pytest

from engine.providers.flow_browser import FlowBrowser, FlowQuotaExceeded


class _Element:
    def __init__(self, name, page=None):
        self.name = name
        self.page = page
        self.first = self

    def is_visible(self, timeout=0):
        return True

    def is_enabled(self, timeout=0):
        return True

    def bounding_box(self):
        return {"x": 10, "y": 20 if self.name == "old" else 40,
                "width": 320, "height": 180}

    def click(self, **kwargs):
        if self.page is not None:
            self.page.clicked.append(self.name)
            if self.name == "720p" and getattr(self.page, "download_listener", None):
                self.page.download_listener(_Download())

    def hover(self, **kwargs):
        return None

    def evaluate(self, script):
        return False


class _Elements:
    def __init__(self, items):
        self.items = items

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class _Download:
    def save_as(self, path):
        Path(path).write_bytes(b"downloaded-video")


class _DownloadContext:
    value = _Download()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _DownloadPage:
    def __init__(self):
        self.url = "https://flow.google.com/project/test"
        self.clicked = []
        self.media = [_Element("old", self), _Element("video", self)]

    def locator(self, selector):
        return _Elements(self.media)

    def on(self, event, callback):
        assert event == "download"
        self.download_listener = callback

    def remove_listener(self, event, callback):
        self.download_listener = None

    def expect_download(self, timeout=0):
        return _DownloadContext()

    def wait_for_timeout(self, ms):
        return None


def test_v571_download_matches_the_same_video_signature_used_by_detection(tmp_path):
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = _DownloadPage()
    b._project_url = "https://flow.google.com/project/test"
    b.ui = {"timeouts": {"download": 10}}
    b.media_assets = lambda: [
        {"sig": "IMG|old|still|image|320|180", "dom_index": 0, "kind": "image"},
        {"sig": "IMG|new|poster|video|320|180", "dom_index": 1, "kind": "video"},
    ]
    b._resolve = lambda action, timeout_ms=0: _Element("download", b._page)
    b._try_resolve = lambda action, timeout_ms=0: None
    b._ensure_project_guard_page = lambda *a, **k: None
    b.return_to_project = lambda timeout_ms=0: True
    b.network_issue_detected = lambda err=None: False

    out = tmp_path / "recovered.mp4"
    result = b.download_latest_asset(
        str(out), preferred_signature="IMG|new|poster|video|320|180",
        before_signatures={"IMG|old|still|image|320|180"})

    assert result == str(out)
    assert out.exists()
    assert b._page.clicked[0] == "video"


def test_v572_download_uses_project_tile_menu_without_opening_viewer(tmp_path):
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = _DownloadPage()
    b._project_url = "https://flow.google.com/project/test"
    b.ui = {"timeouts": {"download": 10}}
    b.media_assets = lambda: [
        {"sig": "IMG|new|poster|video|320|180", "dom_index": 0, "kind": "video"},
    ]
    menu = _Element("download-row", b._page)
    option = _Element("720p", b._page)
    b._open_asset_tile_download_menu = lambda locator: True
    b._resolve = lambda action, timeout_ms=0: menu
    b._try_resolve = lambda action, timeout_ms=0: option if action == "download_original_option" else None
    b._ensure_project_guard_page = lambda *a, **k: None
    b.return_to_project = lambda timeout_ms=0: True
    b.network_issue_detected = lambda err=None: False

    out = tmp_path / "tile-download.mp4"
    result = b.download_latest_asset(
        str(out), preferred_signature="IMG|new|poster|video|320|180")

    assert result == str(out)
    assert out.exists()
    assert b._page.clicked == ["download-row", "720p"]


def test_v571_usage_limit_wins_over_generic_try_again_capacity_message():
    b = FlowBrowser.__new__(FlowBrowser)

    class Page:
        def inner_text(self, selector):
            return "You've reached your usage limit. Please try again later. Try again"

        def wait_for_timeout(self, ms):
            return None

    b._page = Page()
    b.ui = {
        "actions": {
            "quota_texts": ["you've reached your usage limit"],
            "service_busy_texts": ["please try again later"],
            "service_retry_buttons": ["Try again"],
            "service_busy_retry_delays": [0],
            "failure_texts": [],
        },
        "timeouts": {"generation": 10, "poll_interval": 0.01,
                     "service_busy_wait": 5, "service_busy_retries": 2},
    }
    b.state_cb = None
    b.recover_service_busy = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("hard usage limits must not enter capacity retries"))

    with pytest.raises(FlowQuotaExceeded):
        b.wait_for_agent_generation(before_assets=set(), timeout_s=2)


def test_v571_wait_detects_a_late_first_project_approval(monkeypatch):
    import engine.providers.flow_browser as module

    b = FlowBrowser.__new__(FlowBrowser)
    b.ui = {
        "actions": {"agent_confirmation_buttons": ["Approve", "Approve once"]},
        "timeouts": {"generation": 20, "poll_interval": 0.01},
    }
    b.state_cb = None
    b.detect_failure = lambda: None
    b.detect_service_busy = lambda: None
    b._set = lambda state: None

    class Page:
        def inner_text(self, selector):
            return "Waiting for approval"

        def wait_for_timeout(self, ms):
            return None

    b._page = Page()
    calls = {"approval": 0, "clock": 0}

    def clock():
        calls["clock"] += 1
        return float(calls["clock"])

    monkeypatch.setattr(module.time, "time", clock)

    def confirm(timeout_s=1, approval="once", max_credits=None):
        calls["approval"] += 1
        clicked = calls["approval"] >= 2
        b.last_agent_confirmation = {
            "clicked": "Approve" if clicked else None,
            "blocked": False,
            "cost": 7 if clicked else None,
        }
        return clicked

    b.confirm_agent_generation = confirm
    b.media_assets = lambda: ([{"sig": "old", "kind": "image"},
                               {"sig": "new", "kind": "image"}]
                              if calls["approval"] >= 2 else [{"sig": "old", "kind": "image"}])

    assert b.wait_for_agent_generation(
        before_assets={"old"}, timeout_s=20, approval="once",
        max_generation_credits=10)
    assert calls["approval"] >= 2
    assert b.last_agent_confirmation["clicked"] == "Approve"


def test_v571_progress_log_has_wall_clock_and_elapsed_time(tmp_path):
    from engine.progress import JobProgress

    progress = JobProgress(str(tmp_path))
    progress.emit("Flow wait", 55, "next attempt at 10:30:00")
    line = (tmp_path / "logs" / "runtime.log").read_text(encoding="utf-8")
    latest = (tmp_path / "logs" / "progress.json").read_text(encoding="utf-8")
    assert "T" in line and "[+00:00:00]" in line
    assert '"elapsed": "00:00:00"' in latest


def test_v571_factory_recovery_never_submits_a_generation(monkeypatch, tmp_path):
    import engine.providers.flow_browser as flow_module
    from engine.factory import Factory
    from engine.project.manifest import Shot

    f = Factory(outputs=str(tmp_path / "outputs"), db_path=str(tmp_path / "jobs.db"))
    job = f.create_job("recovery", profile="FLOW_ECONOMY", images_per_shot=0)
    m = f.pm.load_manifest(job)
    m.shots = [Shot(shot_id="shot_005", status="failed", compiled_prompt="existing video")]
    m.status = "paused"
    f.pm.save_manifest(m)
    f._remember_flow_project_url(job, "https://flow.google.com/project/abc-123")
    f._write_pause_state(job, "shot_005", "download interrupted",
                         kind="flow_download_or_ui",
                         baseline_signatures={"old-video-signature"})

    calls = {"rescues": 0, "baseline": None}

    class RecoveryOnlyProvider:
        def rescue_recent_project_video(self, project, out_path, **kwargs):
            calls["rescues"] += 1
            calls["baseline"] = kwargs.get("baseline_signatures")
            Path(out_path).write_bytes(b"existing-flow-video")
            return {"path": out_path, "project_url": kwargs["project_url"], "credits": 0}

        def current_project_url(self):
            return "https://flow.google.com/project/abc-123"

        def close(self):
            return None

    monkeypatch.setattr(flow_module, "FlowBrowserProvider", RecoveryOnlyProvider)
    monkeypatch.setattr(
        f, "associate_download",
        lambda job_id, shot_id, path: {
            "take": path, "qc": {"decision": "ACCEPT", "overall": 91}})

    result = f.recover_flow_video(job, shot_id="shot_005", wait_seconds=5)
    assert calls["rescues"] == 1
    assert calls["baseline"] == {"old-video-signature"}
    assert result["new_credits"] == 0
    assert result["accepted"] is True
    assert f.db.get(job)["status"] == "planned"


def test_v573_recovery_is_idempotent_for_an_already_accepted_shot(tmp_path):
    from engine.factory import Factory
    from engine.project.manifest import Shot

    f = Factory(outputs=str(tmp_path / "outputs"), db_path=str(tmp_path / "jobs.db"))
    job = f.create_job("already done", profile="FLOW_ECONOMY", images_per_shot=0)
    m = f.pm.load_manifest(job)
    m.shots = [Shot(shot_id="shot_005", status="accepted",
                    accepted_take=str(tmp_path / "accepted.mp4"))]
    f.pm.save_manifest(m)

    result = f.recover_flow_video(job, shot_id="shot_005")
    assert result["status"] == "already_accepted"
    assert result["new_credits"] == 0


def test_v571_parallel_image_workers_use_concurrent_isolated_projects(monkeypatch, tmp_path):
    import threading
    import engine.providers.flow_browser as flow_module
    import engine.qc.video_qc as qc_module
    from engine.factory import Factory
    from engine.project.manifest import Shot

    seen = {"projects": [], "assignments": {}, "active": 0,
            "max_active": 0, "rendezvous_enabled": True}
    lock = threading.Lock()
    rendezvous = threading.Barrier(2)

    class Browser:
        def __init__(self):
            self.project = ""

        def ensure_project(self, project, project_url=None):
            self.project = project
            with lock:
                seen["projects"].append(project)

        def current_project_url(self):
            project_id = self.project.rsplit("-", 1)[-1].lower()
            return f"https://flow.google.com/project/{project_id}"

    class Provider:
        def __init__(self, headless=False, profile_dir=None):
            self.profile_dir = profile_dir
            self.browser = Browser()

        def _ensure(self):
            return self.browser

        def generate_image(self, shot, compiled, out_path, vertical, dry_run=False):
            with lock:
                seen["assignments"][Path(out_path).name] = (
                    compiled.get("project"), compiled.get("project_url"))
                seen["active"] += 1
                seen["max_active"] = max(seen["max_active"], seen["active"])
            # Both workers must reach generation concurrently; a shared Playwright
            # page/project would make this test fail rather than merely look parallel.
            if seen["rendezvous_enabled"]:
                rendezvous.wait(timeout=5)
            Path(out_path).write_bytes(b"x" * 6001)
            with lock:
                seen["active"] -= 1
            return {"path": out_path, "project_url": compiled["project_url"]}

        def close(self):
            return None

    monkeypatch.setattr(flow_module, "FlowBrowserProvider", Provider)
    monkeypatch.setattr(flow_module, "PROFILE_DIR", str(tmp_path / "no-base-profile"))
    monkeypatch.setattr(qc_module, "score_image", lambda path: {"overall": 80})

    f = Factory(outputs=str(tmp_path / "outputs"), db_path=str(tmp_path / "jobs.db"))
    f._is_valid_image_file = lambda path: Path(path).is_file()
    job = f.create_job("parallel", profile="FLOW_ECONOMY", images_per_shot=2,
                       flow_image_workers=2)
    m = f.pm.load_manifest(job)
    m.shots = [Shot(shot_id="shot_001", compiled_prompt="same project")]
    f.pm.save_manifest(m)
    refs = type("Refs", (), {"add": lambda self, *args: None})()

    f._generate_scene_images_parallel(
        m, f.pm.dirs(job), refs, True, 2, lambda *args: None,
        {"flow_image_workers": 2}, 2)

    assert len(set(seen["projects"])) == 2
    assert len({url for _, url in seen["assignments"].values()}) == 2
    assert seen["max_active"] == 2
    assert all(project.endswith("worker-1") or project.endswith("worker-2")
               for project, _ in seen["assignments"].values())

    # Resume after one candidate was already saved. The missing output must keep
    # its original worker/project binding instead of shifting with the task list.
    original_assignment = seen["assignments"]["img_02.jpg"]
    D = f.pm.dirs(job)
    missing = Path(D["flow"]) / "shots" / "shot_001" / "images" / "img_02.jpg"
    missing.unlink()
    seen["rendezvous_enabled"] = False
    f._generate_scene_images_parallel(
        m, D, refs, True, 2, lambda *args: None,
        {"flow_image_workers": 2}, 2)
    assert seen["assignments"]["img_02.jpg"] == original_assignment


def test_v571_old_pause_without_baseline_refuses_to_guess_latest_tile(tmp_path):
    from engine.factory import Factory
    from engine.project.manifest import Shot

    f = Factory(outputs=str(tmp_path / "outputs"), db_path=str(tmp_path / "jobs.db"))
    job = f.create_job("old pause", profile="FLOW_ECONOMY", images_per_shot=0)
    m = f.pm.load_manifest(job)
    m.shots = [Shot(shot_id="shot_005", status="failed")]
    m.status = "paused"
    f.pm.save_manifest(m)
    f._remember_flow_project_url(job, "https://flow.google.com/project/abc-123")

    with pytest.raises(RuntimeError, match="could duplicate an earlier accepted shot"):
        f.recover_flow_video(job, shot_id="shot_005", wait_seconds=5)

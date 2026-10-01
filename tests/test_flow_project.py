"""Project entry + onboarding + assisted-diagnostics tests (no real browser)."""
import json
import os
import types

import pytest

from engine.providers.flow_browser import (
    FlowBrowser, FlowBrowserProvider, FlowUIChanged,
)


def test_onboarding_and_tab_candidates():
    import yaml
    ui = yaml.safe_load(open("config/flow_ui.yaml", encoding="utf-8"))
    acts = ui["actions"]
    assert len(acts.get("onboarding_dismiss", [])) >= 5
    tabs = acts["text_to_video_tab"]
    assert len(tabs) >= 4
    texts = " ".join(str(c) for c in tabs)
    assert "Text to video" in texts  # case variant present


class _FakeLoc:
    def __init__(self, name="x"):
        self.name = name
        self.clicked = 0

    def click(self):
        self.clicked += 1


def _bridge():
    b = FlowBrowser.__new__(FlowBrowser)
    b.ui = {"actions": {"onboarding_dismiss": ["Get started", "Continue"]}}
    b._project_ready = None
    return b


def test_select_video_mode_text_uses_new_type_picker():
    b = _bridge()
    calls = []

    def fake_try(action, timeout_ms=1500):
        calls.append(action)
        return _FakeLoc(action) if action == "generation_type_picker" else None

    def fake_resolve(action, timeout_ms=8000, fmt=None):
        calls.append(action)
        if action == "video_option":
            return _FakeLoc(action)
        raise FlowUIChanged("missing")

    b._try_resolve = fake_try
    b._resolve = fake_resolve
    b.select_video_mode("text")
    assert calls == ["generation_type_picker", "video_option"]


def test_select_video_mode_text_legacy_fallback_is_strict():
    b = _bridge()
    calls = []
    b._try_resolve = lambda action, timeout_ms=1500: None

    def fake_resolve(action, timeout_ms=8000, fmt=None):
        calls.append(action)
        raise FlowUIChanged("no legacy tab")

    b._resolve = fake_resolve
    with pytest.raises(FlowUIChanged):
        b.select_video_mode("text")
    assert calls == ["text_to_video_tab"]


def test_select_video_mode_frames_stays_strict():
    b = _bridge()

    def fake_resolve(action, timeout_ms=8000, fmt=None):
        raise FlowUIChanged("no tab")

    b._resolve = fake_resolve
    with pytest.raises(FlowUIChanged):
        b.select_video_mode("frames")


def test_ensure_project_reuses_ready_session():
    b = _bridge()
    b._project_ready = "P"
    b.dismiss_onboarding = lambda rounds=3: (_ for _ in ()).throw(AssertionError("should not run"))
    b.ensure_project("P")  # no-op


def test_ensure_project_reuses_visible_composer_without_project_lookup():
    b = _bridge()
    calls = []
    b.dismiss_onboarding = lambda rounds=3: calls.append(f"dismiss{rounds}") or 0
    b._composer_visible = lambda timeout_ms=1200: True
    b.open_project = lambda name: calls.append(f"open:{name}")
    b.create_project = lambda name: calls.append(f"create:{name}")
    b.ensure_project("MyProj")
    assert calls == ["dismiss3"]
    assert b._project_ready == "MyProj"


def test_ensure_project_open_then_create_fallback():
    b = _bridge()
    calls = []
    visible = iter([False, True])
    b.dismiss_onboarding = lambda rounds=3: calls.append(f"dismiss{rounds}") or 0
    b._composer_visible = lambda timeout_ms=1200: next(visible)
    b.enter_flow_app = lambda: False
    b.open_project = lambda name: calls.append(f"open:{name}")
    b.create_project = lambda name: calls.append(f"create:{name}")
    b.ensure_project("MyProj")
    assert "open:MyProj" in calls
    assert "create:MyProj" not in calls
    assert b._project_ready == "MyProj"

    b2 = _bridge()
    calls2 = []
    visible2 = iter([False, True])
    b2.dismiss_onboarding = lambda rounds=3: calls2.append(f"dismiss{rounds}") or 0
    b2._composer_visible = lambda timeout_ms=1200: next(visible2)
    b2.enter_flow_app = lambda: False

    def _open_fail(name):
        calls2.append(f"open:{name}")
        raise FlowUIChanged("not listed")

    b2.open_project = _open_fail
    b2.create_project = lambda name: calls2.append(f"create:{name}")
    b2.ensure_project("MyProj")
    assert "create:MyProj" in calls2 and b2._project_ready == "MyProj"


def test_generate_enters_project_and_snapshots_on_ui_failure(tmp_path):
    prov = FlowBrowserProvider()
    seen = {}

    class FakeBridge:
        def ensure_project(self, name):
            seen["project"] = name

        def select_video_mode(self, mode):
            raise FlowUIChanged("UI element not found: text_to_video_tab")

        def snapshot_failure(self, job, shot, err):
            seen["snap"] = (job, shot)
            return "/tmp/fake.png"

    prov._ensure = lambda: FakeBridge()
    shot = types.SimpleNamespace(shot_id="shot_001", model="veo_fast",
                                 gen_duration=8, visual_goal="cat")
    with pytest.raises(FlowUIChanged) as ei:
        prov.generate(shot, {"prompt": "p", "project": "AutoVideo-JOB1"}, {},
                      "/tmp/o.mp4", True, dry_run=False)
    assert seen["project"] == "AutoVideo-JOB1"
    assert seen["snap"] == ("AutoVideo-JOB1", "shot_001")
    assert "[snapshot:" in str(ei.value)


class _FakeEl:
    def __init__(self, t):
        self._t = t

    def inner_text(self):
        return self._t


class _FakeRole:
    def __init__(self, els):
        self._els = els

    def all(self):
        return self._els


class _FakePage:
    url = "https://flow.google.com/xyz"

    def screenshot(self, path):
        with open(path, "wb") as f:
            f.write(b"PNG")

    def inner_text(self, sel):
        return "Welcome to Flow\nNew project"

    def get_by_role(self, role):
        return _FakeRole([_FakeEl("Text to Video"), _FakeEl("Generate")])


def test_snapshot_failure_enrichment(tmp_path):
    b = FlowBrowser.__new__(FlowBrowser)
    b.log_dir = str(tmp_path)
    b._page = _FakePage()
    png = b.snapshot_failure("AutoVideo-JOB1", "shot_002", FlowUIChanged("nope"))
    assert png.endswith(".png") and os.path.exists(png)
    data = json.load(open(png[:-4] + ".json", encoding="utf-8"))
    assert "flow.google.com" in data["url"]
    assert "New project" in data["page_text"]
    assert "Generate" in data["buttons"]

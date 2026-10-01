import json
import os
from pathlib import Path

from engine.factory import Factory
from engine.project.manifest import ProductionManifest
from engine.providers.flow_browser import FlowBrowser, FlowBrowserProvider


class _Ctx:
    def __init__(self):
        self.closed = 0
    def close(self):
        self.closed += 1


class _PW:
    def __init__(self):
        self.stopped = 0
    def stop(self):
        self.stopped += 1


def test_v49_close_does_not_kill_unowned_cdp_context():
    b = FlowBrowser.__new__(FlowBrowser)
    ctx = _Ctx(); pw = _PW()
    b._ctx = ctx
    b._pw = pw
    b._page = object()
    b._cdp = object()
    b._guard_page = None
    b._own_context = False
    b.state_cb = None
    b.state = None
    b.close()
    assert ctx.closed == 0
    assert pw.stopped == 1
    assert b._ctx is None


def test_v49_close_owned_context_closes_it():
    b = FlowBrowser.__new__(FlowBrowser)
    ctx = _Ctx(); pw = _PW()
    b._ctx = ctx; b._pw = pw; b._page = object(); b._cdp = None
    b._guard_page = None; b._own_context = True; b.state_cb = None; b.state = None
    b.close()
    assert ctx.closed == 1
    assert pw.stopped == 1


def test_v49_provider_prefers_soft_page_recovery():
    class B:
        def __init__(self):
            self.soft = 0; self.ensure = 0
        def recover_project_page(self, project_url=None):
            self.soft += 1
            return True
        def ensure_project(self, project, project_url=None):
            self.ensure += 1
            return True
    b = B()
    p = FlowBrowserProvider.__new__(FlowBrowserProvider)
    p.bridge = b
    p._ensure = lambda: b
    hard = {"n": 0}
    p.close = lambda: hard.__setitem__("n", hard["n"] + 1)
    assert p.recover_browser("AutoVideo-job", "https://flow.google.com/project/abc") is True
    assert b.soft == 1
    assert b.ensure == 1
    assert hard["n"] == 0


def test_v49_external_same_topic_frame_reuse_across_release_folders(tmp_path, monkeypatch):
    parent = tmp_path
    current = parent / "AutoVideoAI-v4.9"
    old = parent / "AutoVideoAI-v4.8.2"
    current.mkdir(); (current / "outputs").mkdir()
    jobroot = old / "outputs" / "20260924-old"
    (jobroot / "storyboard").mkdir(parents=True)
    from PIL import Image
    Image.new("RGB", (64, 64), "white").save(jobroot / "storyboard" / "shot_001_open.jpg", "JPEG")
    manifest = {
        "job_id": "20260924-old", "topic": "How develop a winner mindset",
        "aspect": "16:9", "shots": [{"shot_id": "shot_001", "actual_provider": "image"}]
    }
    (jobroot / "production_manifest.json").write_text(json.dumps(manifest))
    (jobroot / "settings.json").write_text(json.dumps({
        "flow_project_url": "https://flow.google.com/project/abc"
    }))
    monkeypatch.chdir(current)
    f = Factory(outputs=str(current / "outputs"), db_path=str(current / "data" / "jobs.db"))
    m = ProductionManifest(job_id="new", topic="How develop a winner mindset", aspect="16:9")
    got = f._previous_project_frame(m, "https://flow.google.com/project/abc",
                                    "shot_001", "opening frame", "topic")
    assert got and got.endswith("shot_001_open.jpg")

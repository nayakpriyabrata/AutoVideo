from pathlib import Path

from engine.factory import Factory
from engine.providers.flow_browser import FlowBrowser


def test_v46_flow_frame_cache_is_exact(monkeypatch, tmp_path):
    f = Factory(outputs=str(tmp_path / "out"), db_path=str(tmp_path / "jobs.db"))
    monkeypatch.setattr(f, "_flow_frame_cache_dir", lambda url: str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    src = tmp_path / "frame.jpg"
    from PIL import Image
    Image.new("RGB", (64, 64), "white").save(src, "JPEG")
    url = "https://flow.google.com/project/abc-123"
    assert f._flow_frame_cache_put(url, "same prompt", False, "opening frame", str(src), "job1")
    hit = f._flow_frame_cache_get(url, "same prompt", False, "opening frame")
    assert hit and Path(hit).exists()
    assert f._flow_frame_cache_get(url, "different prompt", False, "opening frame") is None
    assert f._flow_frame_cache_get(url, "same prompt", True, "opening frame") is None


def test_v46_upload_alias_depends_on_bytes(tmp_path):
    a = tmp_path / "shot_001_open.jpg"
    b = tmp_path / "other.jpg"
    a.write_bytes(b"abc")
    b.write_bytes(b"abc")
    aa = FlowBrowser._media_upload_alias(str(a))
    bb = FlowBrowser._media_upload_alias(str(b))
    assert aa.startswith("AV_") and bb.startswith("AV_")
    assert aa.split("_")[1] == bb.split("_")[1]
    b.write_bytes(b"abcd")
    assert FlowBrowser._media_upload_alias(str(b)).split("_")[1] != aa.split("_")[1]


class _NoText:
    def is_visible(self, timeout=0): return False
    @property
    def first(self): return self


class _ProgressPage:
    def inner_text(self, selector):
        return "I'm going to generate a 4-second video interpolation between your two tech studio frames."
    def get_by_role(self, *a, **k): return _NoText()
    def get_by_text(self, *a, **k): return _NoText()
    def wait_for_timeout(self, ms): return None


def test_v46_agent_progress_without_approval_is_not_blocked():
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = _ProgressPage()
    b.ui = {"actions": {"agent_confirmation_buttons": ["Approve", "Always approve"]}}
    b.network_issue_detected = lambda err=None: False
    assert not b.confirm_agent_generation(timeout_s=1, approval="once", max_credits=10)
    assert b.last_agent_confirmation["blocked"] is False
    assert "already started" in b.last_agent_confirmation["reason"]

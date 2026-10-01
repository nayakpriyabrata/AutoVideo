from pathlib import Path
import shutil
import subprocess
import pytest

from engine.providers.flow_browser import FlowBrowser, FlowBrowserProvider


class _ButtonSet:
    def __init__(self, names):
        self.names = list(names)
        self.first = self
    def count(self):
        return len(self.names)
    def nth(self, i):
        return _OneButton(self.names[i])


class _OneButton:
    def __init__(self, name):
        self.name = name
        self.first = self
    def is_visible(self, timeout=0):
        return True
    def is_enabled(self, timeout=0):
        return True
    def click(self, **kwargs):
        return None


class ProgressPage:
    def __init__(self):
        self.body = (
            "Would you like me to kick off this generation, costing 7 credits? "
            "Approve Always approve Reject\n"
            "I'm going to generate a 4-second video interpolation between your two tech studio frames."
        )
    def inner_text(self, sel):
        return self.body
    def get_by_role(self, role, name=None):
        # A generic Generate control elsewhere in the page must not be treated as
        # the credit approval for this Agent turn.
        names = ["Generate"]
        matched = [n for n in names if name.search(n)] if name else names
        return _ButtonSet(matched)
    def get_by_text(self, text, exact=False):
        return _ButtonSet([])
    def wait_for_timeout(self, ms):
        pass
    def evaluate(self, js):
        return True


def test_v47_generation_progress_beats_stale_confirmation_and_generic_button():
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = ProgressPage()
    b.ui = {"actions": {"agent_confirmation_buttons": [
        "Approve", "Always approve", "Generate", "Continue", "Yes"
    ]}}
    assert b.confirm_agent_generation(timeout_s=1, approval="once", max_credits=10) is False
    assert b.last_agent_confirmation["blocked"] is False
    assert "generation already started" in b.last_agent_confirmation["reason"]


def test_v47_downloaded_flow_asset_must_really_be_video(tmp_path):
    jpg = tmp_path / "wrong.mp4"
    jpg.write_bytes(b"\xff\xd8\xff" + b"x" * 6000)
    assert FlowBrowserProvider._is_valid_video_file(str(jpg)) is False

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    mp4 = tmp_path / "ok.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=10",
                    "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert FlowBrowserProvider._is_valid_video_file(str(mp4)) is True

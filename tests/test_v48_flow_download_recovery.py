from pathlib import Path
import shutil
import subprocess
import pytest

from engine.providers.flow_browser import FlowBrowser, FlowBrowserProvider, FlowBrowserClosedError


class _FakeDownload:
    def __init__(self, path):
        self._path = str(path)
    def path(self):
        return self._path


def test_v48_salvage_playwright_download(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    src = tmp_path / "src.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=10",
                    "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dst = tmp_path / "dst.mp4"
    out = FlowBrowser._salvage_playwright_download(_FakeDownload(src), str(dst))
    assert out == str(dst)
    assert dst.exists()
    assert FlowBrowserProvider._is_valid_video_file(str(dst)) is True


def test_v48_download_after_browser_recovery_uses_signature_and_baseline(tmp_path):
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    calls = []

    class _Recovered:
        def ensure_project(self, project, project_url=None):
            calls.append(("ensure", project, project_url))
        def download_latest_asset(self, out_path, preferred_signature=None, before_signatures=None):
            calls.append(("download", preferred_signature, before_signatures))
            Path(out_path).write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 6000)
            return out_path

    recovered = _Recovered()
    provider.recover_browser = lambda project, project_url=None: True
    provider._ensure = lambda: recovered
    out = tmp_path / "ok.mp4"
    res = provider._download_after_browser_recovery(
        "AutoVideo-job", str(out),
        project_url="https://flow.google.com/project/abc",
        preferred_signature="sig-1",
        before_signatures={"old-a", "old-b"},
        attempts=1,
    )
    assert res == str(out)
    assert calls[0] == ("ensure", "AutoVideo-job", "https://flow.google.com/project/abc")
    assert calls[1] == ("download", "sig-1", {"old-a", "old-b"})


def test_v48_download_after_browser_recovery_raises_when_recovery_fails(tmp_path):
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    provider.recover_browser = lambda project, project_url=None: False
    provider._ensure = lambda: None
    try:
        provider._download_after_browser_recovery("AutoVideo-job", str(tmp_path / "x.mp4"), attempts=1)
    except FlowBrowserClosedError:
        pass
    else:
        raise AssertionError("expected FlowBrowserClosedError")

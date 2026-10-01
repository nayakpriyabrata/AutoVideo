"""WSL browser routing + CDP bool helper + pollinations retry (no real browser)."""
import json
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

import engine.providers.flow_browser as fb
from engine.providers.flow_browser import FlowBrowser, cdp_is_live


def _browser(bcfg):
    b = FlowBrowser.__new__(FlowBrowser)
    b.bcfg = bcfg
    return b


def test_wsl_skips_windows_exe(monkeypatch):
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    b = _browser({"mode": "auto", "channel": "chrome",
                  "executable": "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"})
    kinds = [o["kind"] for o in b._launch_options()]
    assert "exe" not in kinds and "bundled" in kinds
    assert any("not launchable from WSL" in s for s in b._launch_skipped)


def test_channel_skipped_in_wsl_without_native_chrome(monkeypatch):
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    monkeypatch.setattr(fb, "has_native_linux_chrome", lambda: False)
    monkeypatch.setattr(fb, "find_system_chrome", lambda: None)
    b = _browser({"mode": "auto", "channel": "chrome", "executable": ""})
    assert [o["kind"] for o in b._launch_options()] == ["bundled"]
    assert any("no native Linux Chrome" in s for s in b._launch_skipped)


def test_channel_kept_in_wsl_with_native_chrome(monkeypatch):
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    monkeypatch.setattr(fb, "has_native_linux_chrome", lambda: True)
    monkeypatch.setattr(fb, "find_system_chrome", lambda: None)
    b = _browser({"mode": "auto", "channel": "chrome", "executable": ""})
    assert [o["kind"] for o in b._launch_options()][0] == "channel"


def test_default_profile_dir_wsl_vs_native(monkeypatch, tmp_path):
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    monkeypatch.setenv("HOME", str(tmp_path))
    p = fb.default_profile_dir()
    assert p.startswith(str(tmp_path)) and "autovideoai" in p and "/mnt/" not in p
    monkeypatch.setattr(fb, "is_wsl", lambda: False)
    assert fb.default_profile_dir().endswith(".flow-profile")


def test_missing_shared_libs_parsing(monkeypatch):
    import subprocess as _sp

    class _R:
        stdout = ("libnss3.so => not found\n"
                  "libatk.so => /lib/x.so\n"
                  "libfoo.so.1 => not found\n")
        stderr = ""

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _R())
    assert fb.missing_shared_libs("/fake/chrome") == ["libfoo.so.1", "libnss3.so"]


def test_short_browser_error_keeps_logs():
    e = RuntimeError("BrowserType.launch_persistent_context: Target page closed\n"
                     "Browser logs:\n[ERROR:gpu_init.cc(123)] GPU process crashed\nline2")
    s = fb.short_browser_error(e)
    assert "Target page closed" in s and "GPU process crashed" in s


def test_short_browser_error_without_logs():
    assert fb.short_browser_error(ValueError("plain")) == "plain"
    assert fb.short_browser_error(ValueError("x" * 500)) == "x" * 160


def test_browser_test_verdict_branches():
    v = fb.browser_test_verdict
    headed_ok = [{"name": "h1", "headed": True, "ok": True, "detail": ""},
                 {"name": "hl", "headed": False, "ok": True, "detail": ""}]
    assert "WORKS (h1)" in v(headed_ok)
    xserver = [{"name": "h1", "headed": True, "ok": False,
                "detail": "closed | logs: without having a XServer running"},
               {"name": "hl", "headed": False, "ok": True, "detail": ""}]
    assert "wsl --shutdown" in v(xserver) and "CDP" in v(xserver)
    gpuish = [{"name": "h1", "headed": True, "ok": False, "detail": "GPU crashed"},
              {"name": "hl", "headed": False, "ok": True, "detail": ""}]
    assert "HEADLESS" in v(gpuish)
    dead = [{"name": "h1", "headed": True, "ok": False, "detail": "x"},
            {"name": "hl", "headed": False, "ok": False, "detail": "y"}]
    assert "Even headless failed" in v(dead)


def test_launch_fix_hint_branches(monkeypatch):
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    h = fb.launch_fix_hint(["bundled: closed | logs: without having a XServer running"])
    assert "wsl --shutdown" in h and "curl http://127.0.0.1:9222/json/version" in h
    h2 = fb.launch_fix_hint(["bundled: something else"])
    assert "XServer" not in h2 and "chrome-debug.bat" in h2
    monkeypatch.setattr(fb, "is_wsl", lambda: False)
    assert "chrome-debug.bat" not in fb.launch_fix_hint(["x"])


def test_windows_launchers_cover_cdp_flow():
    bat = open("chrome-debug.bat", encoding="utf-8").read()
    assert "--remote-debugging-port=9222" in bat
    assert "curl -s -m 5 http://127.0.0.1:9222/json/version" in bat  # self-check
    chk = open("check-cdp.bat", encoding="utf-8").read()
    for needle in ("json/version", "netstat", "Get-CimInstance", "wsl --version",
                   ".wslconfig"):
        assert needle in chk


def test_doctor_reports_wslg(monkeypatch):
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    monkeypatch.setattr(fb, "find_system_chrome", lambda: None)
    monkeypatch.setattr(fb, "probe_cdp", lambda u, timeout=3: {"ok": False, "error": "refused"})
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    rep = fb.doctor_report()
    assert "WSLg display: DISPLAY=:0" in rep


def test_native_keeps_explicit_exe(monkeypatch):
    monkeypatch.setattr(fb, "is_wsl", lambda: False)
    b = _browser({"mode": "auto", "channel": "chrome",
                  "executable": "C:/Program Files/Google/Chrome/Application/chrome.exe"})
    kinds = [o["kind"] for o in b._launch_options()]
    assert "exe" in kinds


def test_wsl_skips_detected_windows_chrome(monkeypatch):
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    monkeypatch.setattr(fb, "find_system_chrome",
                        lambda: "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe")
    b = _browser({"mode": "auto", "channel": "chrome", "executable": ""})
    kinds = [o["kind"] for o in b._launch_options()]
    assert "exe" not in kinds


class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"Browser": "Chrome/140.0",
                           "webSocketDebuggerUrl": "ws://x"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_cdp_is_live_bool():
    srv = _serve()
    try:
        assert cdp_is_live(f"http://127.0.0.1:{srv.server_port}") is True
    finally:
        srv.shutdown()
    assert cdp_is_live("http://127.0.0.1:9") is False  # refused -> False, no raise
    assert bool({"ok": False}) is True  # the pitfall: never `if probe_cdp()`


def test_doctor_wsl_chrome_lines(monkeypatch):
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    monkeypatch.setattr(fb, "find_system_chrome",
                        lambda: "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe")
    monkeypatch.setattr(fb, "probe_cdp", lambda u, timeout=3: {"ok": False, "error": "refused"})
    rep = fb.doctor_report()
    assert "Windows Chrome visible from WSL" in rep
    assert "launchable system chrome: none" in rep
    assert "WSL hint" in rep


def test_pollinations_url_model_param():
    from engine.visuals import _pollinations_url
    assert "model=flux" in _pollinations_url("cat", 720, 1280, 1)
    assert "model=" not in _pollinations_url("cat", 720, 1280, 1, model=None)


def test_pollinations_retries_before_fallback(monkeypatch, tmp_path):
    import engine.visuals as vis
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    calls = []

    def fake_download(url, path, timeout=90, quiet=False):
        calls.append(url)
        if len(calls) < 3:
            return False
        with open(path, "wb") as f:
            f.write(b"x" * 6000)
        return True

    monkeypatch.setattr(vis, "_download", fake_download)
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)
    r = vis.get_visuals(["a cat"], "cats", str(tmp_path), True)
    assert r["source"] == "pollinations"
    assert len(calls) == 3
    assert "model=" not in calls[-1]  # last attempt drops the model alias


def test_real_launcher_prefers_native_wayland_on_wsl(monkeypatch, tmp_path):
    """Regression: browser-test Wayland PASS must be usable by flow-open/flow-direct."""
    monkeypatch.setattr(fb, "is_wsl", lambda: True)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    calls = []

    class FakePage:
        pass

    class FakeCtx:
        pages = [FakePage()]
        def close(self):
            pass

    class FakeChromium:
        def launch_persistent_context(self, profile, **kwargs):
            calls.append((profile, kwargs))
            return FakeCtx()

    class FakePW:
        chromium = FakeChromium()

    b = FlowBrowser(ui_cfg_path=str(Path(__file__).resolve().parent.parent / "config" / "flow_ui.yaml"), profile_dir=str(tmp_path / "profile"))
    b._pw = FakePW()
    b._launch_persistent({"kind": "bundled"})

    assert calls, "launcher was not invoked"
    _profile, kwargs = calls[0]
    assert "--ozone-platform=wayland" in kwargs["args"]
    assert kwargs["env"]["WAYLAND_DISPLAY"] == "wayland-0"
    assert "DISPLAY" not in kwargs["env"]
    assert b.active_browser.endswith("[wayland]")

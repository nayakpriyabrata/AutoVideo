"""Path translation + CDP probe + doctor tests (no real browser)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from engine.providers.flow_browser import (to_windows_path, is_windows_exe, is_wsl,
                                           probe_cdp, doctor_report)


def test_windows_path_translation():
    assert to_windows_path("/mnt/c/Users/x/AutoVideoAI") == "C:\\Users\\x\\AutoVideoAI"
    assert to_windows_path("/mnt/d/data") == "D:\\data"
    assert to_windows_path("/home/user/x") is None
    assert to_windows_path("relative/dir") is None or isinstance(to_windows_path("relative/dir"), (str, type(None)))


def test_is_windows_exe():
    assert is_windows_exe("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe")
    assert is_windows_exe("C:/Program Files/Google/Chrome/Application/chrome.exe")
    assert not is_windows_exe("/usr/bin/google-chrome")
    assert not is_windows_exe("")


def test_is_wsl_bool():
    assert isinstance(is_wsl(), bool)


class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/json/version":
            body = json.dumps({"Browser": "Chrome/120.0", "webSocketDebuggerUrl": "ws://x"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


def test_probe_cdp_local_server():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        ok = probe_cdp(f"http://127.0.0.1:{port}")
        assert ok["ok"] and ok["browser"] == "Chrome/120.0" and ok["ws"]
        bad = probe_cdp("http://127.0.0.1:9", timeout=1)
        assert not bad["ok"]
    finally:
        srv.shutdown()


def test_doctor_report_runs(workdir):
    out = doctor_report()
    for k in ("Python", "playwright", "bundled chromium", "system chrome", "profile dir", "CDP http://localhost:9222"):
        assert k in out

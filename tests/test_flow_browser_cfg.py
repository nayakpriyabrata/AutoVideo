"""Browser resolution tests (no real browser launched)."""
import os
from pathlib import Path
from engine.providers.flow_browser import FlowBrowser, find_system_chrome, resolve_browser_cfg


def _repo_ui():
    return str(Path(__file__).resolve().parent.parent / "config" / "flow_ui.yaml")


def test_resolve_defaults_and_env(workdir, monkeypatch):
    ui = {"browser": {"mode": "auto", "channel": "chrome"}}
    assert resolve_browser_cfg(ui)["mode"] == "auto"
    monkeypatch.setenv("FLOW_BROWSER_MODE", "cdp")
    monkeypatch.setenv("FLOW_CDP_URL", "http://localhost:9222")
    cfg = resolve_browser_cfg(ui)
    assert cfg["mode"] == "cdp" and cfg["cdp_url"] == "http://localhost:9222"


def test_user_settings_overlay(workdir):
    os.makedirs("config", exist_ok=True)
    open("config/user_settings.yaml", "w").write("browser:\n  mode: system\n  channel: msedge\n")
    cfg = resolve_browser_cfg({"browser": {"mode": "auto", "channel": "chrome"}})
    assert cfg["mode"] == "system" and cfg["channel"] == "msedge"


def test_launch_option_order(monkeypatch):
    import engine.providers.flow_browser as fb
    monkeypatch.setattr(fb, "is_wsl", lambda: False)  # native-OS expectation
    b = FlowBrowser(ui_cfg_path=_repo_ui())
    b.bcfg = {"mode": "auto", "channel": "chrome"}
    kinds = [o["kind"] for o in b._launch_options()]
    assert kinds[0] == "channel" and kinds[-1] == "bundled"  # system first, bundled last
    b.bcfg = {"mode": "system", "channel": "chrome"}
    assert "bundled" not in [o["kind"] for o in b._launch_options()]
    b.bcfg = {"mode": "bundled"}
    assert [o["kind"] for o in b._launch_options()] == ["bundled"]
    b.bcfg = {"mode": "cdp", "cdp_url": "http://localhost:9222"}
    assert b._launch_options() == []  # cdp attaches, never launches


def test_find_system_chrome_safe():
    r = find_system_chrome()
    assert r is None or (isinstance(r, str) and os.path.exists(r))

import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from engine.providers.flow_browser import FlowBrowser, FlowBrowserProvider, FlowRequestPending


@pytest.mark.parametrize("submenu", [False, True])
def test_tile_download_listens_before_direct_or_submenu_click(tmp_path, monkeypatch, submenu):
    events = {}
    out = tmp_path / "image.jpg"
    download = NS(save_as=lambda path: Path(path).write_bytes(b"downloaded bytes"))
    page = NS(on=lambda event, cb: events.update({event: cb}),
              remove_listener=lambda event, cb: events.pop(event),
              wait_for_timeout=lambda ms: None)
    trigger = lambda **kw: events["download"](download)
    button = NS(click=(lambda **kw: None) if submenu else trigger)
    browser = object.__new__(FlowBrowser)
    browser._page = page
    def option(*args, **kw):
        assert submenu, "immediate image download must not wait for a nonexistent submenu"
        return NS(click=trigger)
    monkeypatch.setattr(browser, "_try_resolve", option)
    assert browser._download_from_tile_button(button, str(out)) == str(out)
    assert out.read_bytes() == b"downloaded bytes"
    assert not events


@pytest.mark.parametrize("kind", ["image", "video"])
def test_pending_request_survives_provider_restart_without_resubmitting(tmp_path, monkeypatch, kind):
    out = str(tmp_path / ("take.jpg" if kind == "image" else "take.mp4"))
    url = "https://flow.google.com/project/0c4d2cc7-88d0-4fe6-b349-71beb08d3925"
    comp = {"prompt": "A useful scene", "project": "test", "project_url": url}
    shot = NS(shot_id="shot_001", model="omni_draft")
    first = object.__new__(FlowBrowserProvider)
    submissions = []
    def submit(*a, **k):
        first._record_submission(out, url, {"old"}, kind)
        first._record_asset(out, "new")
        submissions.append(1)
        raise RuntimeError("page closed during download")
    monkeypatch.setattr(first, "_generate_video_once" if kind == "video" else "_generate_image_once", submit)
    with pytest.raises(FlowRequestPending, match="Generation is blocked"):
        first._guarded_generation(shot, comp, {}, out, False, False, kind)
    assert json.loads(Path(out + ".flow-request.json").read_text())["signature"] == "new"
    second = object.__new__(FlowBrowserProvider)
    def download(path, **kw):
        assert kw["preferred_signature"] == "new"
        assert kw["before_signatures"] == {"old"}
        Path(path).write_bytes(b"validated test asset")
    bridge = NS(ensure_project=lambda *a, **kw: None, download_latest_asset=download)
    monkeypatch.setattr(second, "_ensure", lambda: bridge)
    monkeypatch.setattr(second, "_asset_valid", lambda path, kind: Path(path).exists())
    monkeypatch.setattr(second, "_generate_video_once" if kind == "video" else "_generate_image_once",
                        lambda *a, **kw: pytest.fail("paid resubmission"))
    result = second._guarded_generation(shot, comp, {}, out, False, False, kind)
    assert result["credits"] == 0 and submissions == [1]
    assert json.loads(Path(out + ".flow-request.json").read_text())["status"] == "downloaded"
    comp["prompt"] = "Different prompt"
    with pytest.raises(FlowRequestPending):
        second._guarded_generation(shot, comp, {}, out, False, False, kind)


def test_unknown_pending_asset_never_clicks_retry_or_approval(tmp_path, monkeypatch):
    b = object.__new__(FlowBrowserProvider)
    out = str(tmp_path / "image.jpg")
    comp = {"prompt": "test", "project_url": "https://flow.google.com/project/0c4d2cc7-88d0-4fe6-b349-71beb08d3925"}
    shot = NS(shot_id="shot_001", model="image")
    def submit(*a, **k):
        b._record_submission(out, comp["project_url"], {"old"}, "image")
        raise RuntimeError("interrupted before completion")
    monkeypatch.setattr(b, "_generate_image_once", submit)
    with pytest.raises(FlowRequestPending):
        b.generate_image(shot, comp, out, False)
    monkeypatch.setattr(b, "_ensure", lambda: NS(
        ensure_project=lambda *a, **k: None,
        media_assets=lambda: [{"sig": "a", "kind": "image"}, {"sig": "b", "kind": "image"}]))
    with pytest.raises(FlowRequestPending):
        b.generate_image(shot, comp, out, False)

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from engine.providers.flow_browser import FlowBrowserProvider, FlowRequestPending, FlowUIChanged

URL = "https://flow.google.com/project/7134b084-e9f0-4b5b-ae5b-9609fb3d1f93"
SIGNATURE = "IMG|https://media.example/asset-123.jpg|Frame|image|640|360"


def pending_failure(tmp_path, monkeypatch, with_bridge=True):
    provider = object.__new__(FlowBrowserProvider)
    output = str(tmp_path / "shot_002_open.jpg")
    compiled = {"prompt": "Useful scene", "project": "saved-project", "project_url": URL}
    shot = NS(shot_id="shot_002", model="image")
    calls = []
    if with_bridge:
        provider.bridge = NS(media_assets=lambda: [{"sig": SIGNATURE, "src": "https://media.example/asset-123.jpg"}])
    def fail(*a, **k):
        calls.append("submitted")
        provider._record_submission(output, URL, {"old"}, "image")
        provider._record_asset(output, SIGNATURE)
        raise FlowUIChanged("The recorded asset is not visible")
    monkeypatch.setattr(provider, "_generate_image_once", fail)
    monkeypatch.setattr(provider, "_ensure", lambda: pytest.fail("diagnostics must not launch a browser"))
    return provider, output, compiled, shot, calls


def test_first_failed_download_has_a_diagnostic_and_retains_original_request(tmp_path, monkeypatch):
    provider, output, compiled, shot, calls = pending_failure(tmp_path, monkeypatch)
    with pytest.raises(FlowRequestPending, match="Generation is blocked"):
        provider.generate_image(shot, compiled, output, False)
    request = json.loads(Path(output + ".flow-request.json").read_text())
    diagnostic = json.loads(Path(output + ".recovery.json").read_text())
    assert request["status"] == "pending" and request["signature"] == SIGNATURE
    assert diagnostic["expected_signature"] == SIGNATURE
    assert diagnostic["asset_snapshot_source"] == "current_page"
    assert diagnostic["visible_assets_available"] is True
    assert diagnostic["new_generations"] == 0 and calls == ["submitted"]
    # Retrying the pending request may inspect/download, never submit again.
    bridge = NS(ensure_project=lambda *a, **k: None, media_assets=provider.bridge.media_assets,
                download_latest_asset=lambda *a, **k: (_ for _ in ()).throw(FlowUIChanged("not visible")))
    monkeypatch.setattr(provider, "_ensure", lambda: bridge)
    before = Path(output + ".flow-request.json").read_bytes()
    with pytest.raises(FlowRequestPending):
        provider.generate_image(shot, compiled, output, False)
    assert calls == ["submitted"] and Path(output + ".flow-request.json").read_bytes() == before


def test_diagnostic_without_a_live_bridge_is_explicitly_marked_unavailable(tmp_path, monkeypatch):
    provider, output, compiled, shot, calls = pending_failure(tmp_path, monkeypatch, with_bridge=False)
    with pytest.raises(FlowRequestPending):
        provider.generate_image(shot, compiled, output, False)
    diagnostic = json.loads(Path(output + ".recovery.json").read_text())
    assert diagnostic["asset_snapshot_source"] == "unavailable"
    assert diagnostic["visible_assets_available"] is False and diagnostic["visible_assets"] == []
    assert calls == ["submitted"]


def test_diagnostic_write_failure_does_not_mask_pause_or_claim_nonexistent_file(tmp_path, monkeypatch):
    provider, output, compiled, shot, calls = pending_failure(tmp_path, monkeypatch)
    def fail_write(*a):
        raise PermissionError("diagnostic folder is read-only")
    monkeypatch.setattr(provider, "_record_failure_diagnostic", fail_write)
    with pytest.raises(FlowRequestPending, match="Recovery diagnostic unavailable") as error:
        provider.generate_image(shot, compiled, output, False)
    assert "recorded asset is not visible" in str(error.value)
    assert Path(output + ".flow-request.json").exists() and calls == ["submitted"]

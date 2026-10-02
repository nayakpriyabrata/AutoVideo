import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from engine.factory import Factory
from engine.providers.flow_browser import FlowBrowserProvider, FlowRequestPending


FLOW_URL = "https://flow.google.com/project/test-project"


def _request_hash(shot_id, prompt, vertical=False):
    return hashlib.sha256(json.dumps(
        ["image", shot_id, prompt, vertical], sort_keys=True).encode()).hexdigest()


def test_blank_signature_downloads_the_only_exact_fresh_image_without_submission(tmp_path):
    output = str(tmp_path / "shot_007_close.jpg")
    shot = NS(shot_id="shot_007", model="image")
    prompt = "A red kite over the sea"
    signature = "IMG|https://media.example/assets/new-image|Frame|image|640|360"
    downloads = []
    submitted = []

    class Bridge:
        _page = NS(wait_for_timeout=lambda _ms: None)

        def ensure_project(self, *_args, **_kwargs):
            pass

        def current_project_url(self):
            return FLOW_URL

        def media_assets(self):
            return [
                {"kind": "image", "sig": "old-image"},
                {"kind": "image", "sig": signature},
            ]

        def download_latest_asset(self, path, preferred_signature=None, before_signatures=None):
            downloads.append((preferred_signature, before_signatures))
            Path(path).write_bytes(b"validated-by-test")
            return path

    provider = object.__new__(FlowBrowserProvider)
    provider._ensure = lambda: Bridge()
    provider._asset_valid = lambda path, _kind: Path(path).is_file()
    provider._generate_image_once = lambda *_a, **_k: submitted.append(True)
    provider._save_request(output, {
        "status": "pending", "kind": "image", "project_url": FLOW_URL,
        "baseline": ["old-image"], "signature": "", "submitted_at": time.time(),
        "request_hash": _request_hash(shot.shot_id, prompt),
    })

    result = provider.generate_image(shot, {"prompt": prompt, "project_url": FLOW_URL},
                                     output, vertical=False)

    saved = json.loads(Path(output + ".flow-request.json").read_text())
    assert result["path"] == output
    assert downloads == [(signature, {"old-image"})]
    assert saved["signature"] == signature and saved["status"] == "downloaded"
    assert submitted == []


def test_ambiguous_gallery_does_not_choose_a_different_asset(tmp_path):
    provider = object.__new__(FlowBrowserProvider)

    class Bridge:
        _page = NS(wait_for_timeout=lambda _ms: None)

        def media_assets(self):
            return [
                {"kind": "image", "sig": "new-image-a"},
                {"kind": "image", "sig": "new-image-b"},
            ]

    request = {"baseline": ["old-image"]}
    assert provider._identify_single_fresh_asset(
        Bridge(), request, "image", timeout_ms=0) == ""


def test_pause_preference_is_off_by_default_and_persisted_per_job(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    factory = Factory(outputs=str(tmp_path / "outputs"), db_path=str(tmp_path / "jobs.db"))

    default_job = factory.create_job("default recovery policy", profile="FLOW_ECONOMY", dry_run=True)
    opt_in_job = factory.create_job("pause recovery policy", profile="FLOW_ECONOMY", dry_run=True,
                                    flow_pause_on_unresolved_request=True)

    assert factory._settings(default_job)["flow_pause_on_unresolved_request"] is False
    assert factory._settings(opt_in_job)["flow_pause_on_unresolved_request"] is True

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "user_settings.yaml").write_text(
        "flow_pause_on_unresolved_request: true\n")
    global_job = factory.create_job("global pause default", profile="FLOW_ECONOMY", dry_run=True)
    disabled_job = factory.create_job("per-job pause off", profile="FLOW_ECONOMY", dry_run=True,
                                      flow_pause_on_unresolved_request=False)
    assert factory._settings(global_job)["flow_pause_on_unresolved_request"] is True
    assert factory._settings(disabled_job)["flow_pause_on_unresolved_request"] is False
    assert factory.set_flow_pause_on_unresolved_request(default_job, True) is True
    assert factory._settings(default_job)["flow_pause_on_unresolved_request"] is True


def test_abandoned_fallback_is_not_mislabeled_or_regenerated_by_flow(tmp_path):
    output = tmp_path / "shot_007_close.jpg"
    archive = Path(str(output) + ".flow-request.fallback.json")
    archive.write_text(json.dumps({"status": "abandoned_for_free_image_fallback"}))
    output.write_bytes(b"committed-free-fallback")
    submissions = []

    provider = object.__new__(FlowBrowserProvider)
    provider._asset_valid = lambda path, _kind: Path(path).is_file()
    provider._generate_image_once = lambda *_a, **_k: submissions.append("submitted")
    shot = NS(shot_id="shot_007", model="image")
    compiled = {"prompt": "A red kite", "flow_image_auto_regenerate": False}

    result = provider.generate_image(shot, compiled, str(output), vertical=False)
    assert result["provider"] == "image" and submissions == []

    output.unlink()
    with pytest.raises(FlowRequestPending, match="free image fallback"):
        provider.generate_image(shot, compiled, str(output), vertical=False)
    assert submissions == []

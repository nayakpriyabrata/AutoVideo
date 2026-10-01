import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from engine.support_report import (
    MAX_JSON_BYTES, build_support_report, redact, resolve_job_dir, write_support_report,
)

URL = "https://media.example/assets/7134b084-e9f0-4b5b-ae5b-9609fb3d1f93?id=asset-123&X-Goog-Signature=signed-secret&token=query-secret"
SIGNATURE = f"IMG|{URL}|Frame|image|640|360"


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def job(root):
    root.mkdir(parents=True, exist_ok=True)
    save(root / "production_manifest.json", {"job_id": "saved-job", "status": "paused", "profile": "STORYBOARD_ECONOMY",
                                              "narration": "PRIVATE SCRIPT", "shots": [
        {"shot_id": "shot_002", "status": "planned", "provider": "flow", "media_strategy": "image"}]})
    save(root / "pause_state.json", {"shot_id": "shot_002", "reason": "Recorded asset is not visible", "signature": SIGNATURE})
    save(root / "settings.json", {"api_key": "settings-secret", "password": "another-secret"})
    (root / ".env").write_text("GROQ_API_KEY=env-secret")
    media = root / "storyboard" / "shot_002_open.jpg"
    save(Path(str(media) + ".flow-request.json"), {"status": "pending", "kind": "image", "signature": SIGNATURE,
                                                 "baseline": [], "Authorization": "Bearer header-secret"})
    save(Path(str(media) + ".recovery.json"), {"expected_signature": SIGNATURE,
          "visible_assets": [{"src": URL, "cookie": "cookie-secret", "alt": "Frame"},
                             {"src": "data:image/png;base64,PRIVATEPICTUREBYTES"}]})
    media.write_bytes(b"PRIVATE MEDIA BYTES")
    runtime = root / "logs" / "runtime.log"
    runtime.parent.mkdir(exist_ok=True)
    runtime.write_text("old line\n" * 100 + f"Download failed {URL}\nAuthorization: Bearer runtime-secret\n")
    return root


def test_report_is_read_only_excludes_private_inputs_and_redacts_evidence(tmp_path):
    root = job(tmp_path / "job")
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    report = build_support_report(root, tail_lines=2)
    text = json.dumps(report)
    for secret in ("settings-secret", "another-secret", "env-secret", "header-secret", "cookie-secret",
                   "signed-secret", "query-secret", "runtime-secret", "PRIVATE SCRIPT", "PRIVATE MEDIA BYTES", "PRIVATEPICTUREBYTES"):
        assert secret not in text
    assert "asset-123" in text and "7134b084-e9f0-4b5b-ae5b-9609fb3d1f93" in text
    assert "MEDIA OMITTED" in text
    assert report["pending_request_count"] == 1
    assert report["pending_requests"][0]["local_asset"]["exists"]
    assert report["new_generation_requests"] == 0 and len(report["runtime_tail"]) == 2
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.parametrize("data", [
    {"api_key": "a", "refresh_token": "b", "Cookie": "c"},
    {"nested": [{"Authorization": "Bearer secret", "password": "p"}]},
    "GROQ_API_KEY=key-secret ACCESS_TOKEN=token-secret",
    "Authorization: Bearer bare-secret\nCookie: session=cookie-secret; other=more-secret",
    "https://person:password@host.example/file?id=asset-123&signature=signed-secret#access_token=fragment-secret",
])
def test_known_credentials_are_redacted(data):
    text = json.dumps(redact(data))
    for secret in ("key-secret", "token-secret", "bare-secret", "cookie-secret", "more-secret", "signed-secret", "fragment-secret"):
        assert secret not in text
    if isinstance(data, dict):
        assert "[REDACTED]" in text
    assert "person:password@" not in text


def test_report_skips_downloaded_journals_and_marks_large_unknown_requests(tmp_path):
    root = job(tmp_path / "job")
    save(root / "storyboard" / "done.jpg.flow-request.json", {"status": "downloaded"})
    (root / "storyboard" / "large.jpg.flow-request.json").write_text("x" * (MAX_JSON_BYTES + 1))
    report = build_support_report(root)
    assert report["flow_request_count"] == 3 and report["pending_request_count"] == 2
    assert any("size limit" in json.dumps(row) for row in report["pending_requests"])


def test_report_never_follows_external_file_symlinks(tmp_path):
    root = job(tmp_path / "job")
    external = tmp_path / "private.txt"
    external.write_text("external-secret")
    runtime = root / "logs" / "runtime.log"
    runtime.unlink()
    runtime.symlink_to(external)
    (root / "storyboard" / "external.jpg.flow-request.json").symlink_to(external)
    assert "external-secret" not in json.dumps(build_support_report(root))


def test_export_does_not_overwrite_existing_files(tmp_path):
    root = job(tmp_path / "job")
    path = write_support_report(root)
    assert path.parent == root / "logs" and json.loads(path.read_text())["schema_version"] == 1
    manifest = root / "production_manifest.json"
    original = manifest.read_bytes()
    with pytest.raises(FileExistsError):
        write_support_report(root, manifest)
    assert manifest.read_bytes() == original


@pytest.mark.parametrize("job_id", ["..", "../secrets", "/absolute/path", "a/b", "a\\b", ""])
def test_job_id_cannot_escape_output_root(tmp_path, job_id):
    with pytest.raises(ValueError):
        resolve_job_dir(tmp_path, job_id)


def test_unicode_job_id_is_supported(tmp_path):
    assert resolve_job_dir(tmp_path, "job-ଓଡ଼ିଆ").parent == tmp_path.resolve()


def test_missing_job_does_not_create_directories(tmp_path):
    root = tmp_path / "missing"
    with pytest.raises(ValueError, match="manifest"):
        build_support_report(root)
    assert not root.exists()


def test_cli_diagnostic_export_never_constructs_factory(tmp_path, monkeypatch, capsys):
    import cli
    import engine.factory as factory
    root = job(tmp_path / "outputs" / "saved-job")
    monkeypatch.setattr(factory, "Factory", lambda *a, **k: pytest.fail("Factory/provider must not be started"))
    cli.main_v3(["support-report", "saved-job", "--outputs-root", str(root.parent)])
    assert len(list((root / "logs").glob("support-report-*.json"))) == 1
    assert "No browser opened" in capsys.readouterr().out


def test_pause_reason_is_printed_redacted_and_saved_privately(tmp_path, monkeypatch, capsys):
    from engine.factory import Factory
    factory = object.__new__(Factory)
    factory.pm = NS(load_manifest=lambda job: NS(accepted_count=lambda: 0, shots=[]),
                    job_dir=lambda job: str(tmp_path), log=lambda *a: None)
    monkeypatch.setenv("AUTOVIDEO_RUNTIME_LOG", str(tmp_path / "logs" / "runtime.log"))
    reason = f"Recorded asset is not visible {URL}; Authorization: Bearer pause-secret"
    state = factory._write_pause_state("saved-job", "shot_002", reason, project_url="https://flow.google.com/project/test")
    printed = capsys.readouterr().out
    assert "[PAUSED]" in printed and "support-report saved-job" in printed
    assert "pause-secret" not in printed and "signed-secret" not in printed
    assert state["reason"] == reason  # Private evidence is retained, not rewritten.
    assert "[PAUSED]" in (tmp_path / "logs" / "runtime.log").read_text()

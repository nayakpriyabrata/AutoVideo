import json


def test_v3_content_cli_commands_emit_json_without_external_services(tmp_path, monkeypatch, capsys):
    import engine.factory as factory_module
    import cli

    # These commands only use local file operations. Avoid constructing the full
    # video factory so this regression test cannot start workers or providers.
    monkeypatch.setattr(factory_module, "Factory", lambda: object())

    source_file = tmp_path / "source.txt"
    source_file.write_text("A permitted example article about clear writing.", encoding="utf-8")
    inbox_root = tmp_path / "inbox"
    cli.main_v3([
        "source-import", "--text-file", str(source_file), "--title", "Writing",
        "--output-root", str(inbox_root),
    ])
    source = json.loads(capsys.readouterr().out)
    assert source["title"] == "Writing"
    assert source["text"].startswith("A permitted example")

    character_root = tmp_path / "characters"
    cli.main_v3([
        "character-create", "--name", "Juniper Fox",
        "--description", "An original fictional fox with russet fur and a blue scarf.",
        "--original-confirmed", "--library-root", str(character_root),
    ])
    character = json.loads(capsys.readouterr().out)
    assert character["original_confirmed"] is True
    assert character["type"] == "original-fictional-character"

    template_path = tmp_path / "template.json"
    cli.main_v3([
        "longform-template", "--topic", "How to build a reading habit",
        "--language", "en", "--output", str(template_path),
    ])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    assert template["topic"] == "How to build a reading habit"


def test_v3_metrics_import_loads_json_without_external_services(tmp_path, monkeypatch, capsys):
    import engine.factory as factory_module
    import cli

    monkeypatch.setattr(factory_module, "Factory", lambda: object())
    rows = [{
        "account_id": "owned-channel", "destination": "youtube_short", "language": "en",
        "post_id": "post-001", "measured_at": "2026-10-02T10:00:00Z",
        "metrics": {"views": 120, "watch_time_seconds": 95},
    }]
    source = tmp_path / "metrics.json"
    source.write_text(json.dumps(rows), encoding="utf-8")
    output = tmp_path / "imported-metrics.json"

    cli.main_v3(["metrics-import", str(source), "--output", str(output)])

    result = json.loads(capsys.readouterr().out)
    assert result == {"rows": 1, "source": "manual-owned-account-export"}
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["rows"] == rows


def test_v3_create_config_and_flow_project_commands_use_shared_json_module(tmp_path, monkeypatch, capsys):
    import engine.factory as factory_module
    import engine.providers.flow_browser as flow_browser
    import engine.studio_config as studio_config
    import cli

    job_dir = tmp_path / "job"
    job_dir.mkdir()
    settings_path = job_dir / "settings.json"
    settings_path.write_text(json.dumps({"preserved": True}), encoding="utf-8")
    config = {
        "topic": "A small reading habit", "video_type": "shorts", "aspect": "9:16",
        "theme": "clean", "production_mode": "legacy", "config_source": "test",
        "plan_only": False,
    }
    monkeypatch.setattr(studio_config, "load_video_config", lambda _path: config)
    monkeypatch.setattr(studio_config, "config_to_factory_kwargs", lambda _config: {})
    fake_factory = type("FakeFactory", (), {
        "pm": type("ProjectManager", (), {"job_dir": lambda _self, _job: str(job_dir)})(),
        "create_job": lambda _self, **_kwargs: "job-config",
    })()
    monkeypatch.setattr(factory_module, "Factory", lambda: fake_factory)

    cli.main_v3(["create-config", str(tmp_path / "video.yaml"), "--plan-only"])
    capsys.readouterr()
    configured = json.loads(settings_path.read_text(encoding="utf-8"))
    assert configured["preserved"] is True
    assert configured["theme"] == "clean"
    assert configured["studio_production_mode"] == "legacy"

    monkeypatch.setattr(flow_browser.FlowBrowser, "normalize_project_url", lambda url: url)
    logs = []
    fake_factory.pm.log = lambda *args: logs.append(args)
    fake_factory.db = type("Database", (), {"upsert": lambda _self, *args, **kwargs: None})()
    flow_url = "https://flow.google.com/project/abc123"
    cli.main_v3(["flow-project", "job-config", flow_url])
    assert "Bound job-config" in capsys.readouterr().out
    bound = json.loads(settings_path.read_text(encoding="utf-8"))
    assert bound["flow_project_url"] == flow_url
    assert logs


def test_v3_review_and_delivery_json_commands_are_offline(tmp_path, monkeypatch, capsys):
    import engine.clip_recreation as clip_recreation
    import engine.factory as factory_module
    import engine.production as production
    import engine.publishing as publishing
    import cli

    fake_factory = type("FakeFactory", (), {
        "pm": type("ProjectManager", (), {"job_dir": lambda _self, _job: str(tmp_path)})(),
    })()
    monkeypatch.setattr(factory_module, "Factory", lambda: fake_factory)
    monkeypatch.setattr(
        clip_recreation, "create_recreation_job",
        lambda _factory, clip, character_id, **_kwargs: {"clip": clip, "character_id": character_id},
    )
    monkeypatch.setattr(
        clip_recreation, "approve_recreation",
        lambda _factory, job_id: {"job_id": job_id, "approved": True},
    )
    monkeypatch.setattr(
        publishing, "export_delivery",
        lambda video, folder, destination, **_kwargs: {
            "video": video, "folder": folder, "destination": destination,
        },
    )
    monkeypatch.setattr(production, "init_review", lambda root: {"root": root, "state": "ready"})
    monkeypatch.setattr(
        production, "check_job",
        lambda root, model, budget, _callback: {"root": root, "model": model, "budget": budget},
    )
    monkeypatch.setattr(production, "stage_repairs", lambda root, plan: {"root": root, "plan": plan})

    cli.main_v3(["recreate-clip", "source.mp4", "--character-id", "fox-01"])
    assert json.loads(capsys.readouterr().out) == {"clip": "source.mp4", "character_id": "fox-01"}

    cli.main_v3(["approve-recreation", "recreation-01"])
    assert json.loads(capsys.readouterr().out) == {"job_id": "recreation-01", "approved": True}

    cli.main_v3([
        "export-delivery", "render.mp4", "--folder", str(tmp_path / "delivery"),
        "--destination", "youtube_short",
    ])
    exported = json.loads(capsys.readouterr().out)
    assert exported["video"] == "render.mp4"
    assert exported["destination"] == "youtube_short"

    cli.main_v3(["production-init", "job-01"])
    assert json.loads(capsys.readouterr().out)["state"] == "ready"

    cli.main_v3(["production-check", "job-01"])
    assert json.loads(capsys.readouterr().out)["budget"] == 0

    cli.main_v3(["production-repair", "job-01", "--plan", "repair.json"])
    assert json.loads(capsys.readouterr().out)["plan"] == "repair.json"

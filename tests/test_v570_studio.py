from __future__ import annotations
import json
from pathlib import Path


def test_reels_config_defaults_and_explicit_theme_override(tmp_path):
    from engine.studio_config import load_video_config, config_to_factory_kwargs
    p = tmp_path / "reel.yaml"
    p.write_text("topic: Discipline\nproduction_mode: reels_pro\ntheme: cooking\nflow_image_workers: 3\ntone: calm\n",
                 encoding="utf-8")
    cfg = load_video_config(str(p))
    assert cfg["video_type"] == "shorts"
    assert cfg["aspect"] == "9:16"
    assert cfg["duration"] == 45
    assert cfg["caption_display"] == "full"
    assert cfg["tone"] == "calm"  # explicit input beats theme default
    kwargs = config_to_factory_kwargs(cfg)
    assert kwargs["production_mode"] == "youtube_pro"
    assert kwargs["flow_image_workers"] == 3
    assert kwargs["gemini_chat_cleanup"] == "delete-after-read"


def test_config_rejects_unknown_keys(tmp_path):
    from engine.studio_config import load_video_config
    p = tmp_path / "bad.yaml"
    p.write_text("topic: test\nflow_workerz: 3\n", encoding="utf-8")
    try:
        load_video_config(str(p))
    except ValueError as e:
        assert "flow_workerz" in str(e)
    else:
        raise AssertionError("unknown keys must not be ignored")


def test_progress_writes_shared_log_and_latest_json(tmp_path):
    from engine.progress import JobProgress
    seen = []
    p = JobProgress(str(tmp_path), lambda stage, pct, info="": seen.append((stage, pct, info)))
    p.emit("Rendering", 42.25, "12s / 30s")
    log = (tmp_path / "logs" / "runtime.log").read_text(encoding="utf-8")
    latest = json.loads((tmp_path / "logs" / "progress.json").read_text(encoding="utf-8"))
    assert "42.25%" in log and "12s / 30s" in log
    assert latest["percent"] == 42.25 and seen[-1][0] == "Rendering"


def test_ffmpeg_progress_parser_reports_timeline(monkeypatch, tmp_path):
    from engine.render import ffmpeg_renderer as fr

    class Stdout:
        def __init__(self):
            self.lines = iter(["out_time_ms=5000000\n", "progress=end\n"])
        def readline(self):
            return next(self.lines, "")
        def close(self):
            pass

    class Proc:
        returncode = 0
        stdout = Stdout()
        def wait(self, timeout=None): return 0
        def kill(self): pass

    monkeypatch.setattr(fr.subprocess, "Popen", lambda *a, **k: Proc())
    seen = []
    result = fr._run_ffmpeg_progress(["ffmpeg", "out.mp4"], 10.0,
                                     lambda pct, detail: seen.append((pct, detail)))
    assert result.returncode == 0
    assert seen[0][0] == 50 and seen[-1][0] == 100

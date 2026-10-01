from types import SimpleNamespace


def test_recovery_graph_loops_short_motion_instead_of_freezing(tmp_path):
    from engine.render.ffmpeg_renderer import build_ffmpeg_cmd

    segments = [{"src": str(tmp_path / "short.mp4"), "in": 0,
                 "dur": 4.0, "freeze": 8.0, "trans_out": "cut"}]
    cmd, meta = build_ffmpeg_cmd(
        segments, str(tmp_path / "voice.mp3"), str(tmp_path / "out.mp4"),
        W=320, H=180, encoder="libx264", use_loudnorm=False,
        safe_concat=True, loop_short_segments=True)
    assert "-stream_loop" in cmd
    assert "tpad=stop_mode=clone" not in meta["filter_complex"]
    assert meta["loop_short_segments"] is True
    assert meta["total"] == 12.0


def test_headline_filename_is_meaningful_portable_and_unique():
    from engine.clipping import _headline_filename

    used = set()
    one = _headline_filename("Unlock Your Future: 3 Mindset Shifts!", 1, used)
    two = _headline_filename("Unlock Your Future: 3 Mindset Shifts!", 2, used)
    assert one == "unlock-your-future-3-mindset-shifts.mp4"
    assert two == "unlock-your-future-3-mindset-shifts-2.mp4"
    assert len(one) <= 80


def test_clip_qc_distinguishes_technical_pass_from_editorial_approval(monkeypatch, tmp_path):
    import json
    import engine.clipping as clipping
    from engine.render import ffmpeg_renderer

    video = tmp_path / "lesson.mp4"
    video.write_bytes(b"x" * 4096)
    probe = {"format": {"duration": "30.0"}, "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
        {"codec_type": "audio", "codec_name": "aac"},
    ]}

    def run(cmd, timeout=0):
        if cmd[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout=json.dumps(probe), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(clipping, "_run", run)
    monkeypatch.setattr(ffmpeg_renderer, "_black_duration_ratio", lambda *a, **k: 0.0)
    monkeypatch.setattr(ffmpeg_renderer, "_freeze_metrics",
                        lambda *a, **k: {"ratio": 0.01, "longest": 0.4})
    qc = clipping._clip_qc_report(str(video), 30.0, 92, 80)
    assert qc["decision"] == "PASS"
    assert qc["ready_to_publish"] is False
    assert qc["technical_passed"] is True
    assert qc["editorial_review_required"] is True
    assert qc["quality_score"] >= 90
    assert "virality" in qc["score_label"]


def test_clip_qc_blocks_decode_errors(monkeypatch, tmp_path):
    import json
    import engine.clipping as clipping
    from engine.render import ffmpeg_renderer

    video = tmp_path / "broken.mp4"
    video.write_bytes(b"x" * 4096)
    probe = {"format": {"duration": "30.0"}, "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
        {"codec_type": "audio", "codec_name": "aac"},
    ]}

    def run(cmd, timeout=0):
        if cmd[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout=json.dumps(probe), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="corrupt decoded frame")

    monkeypatch.setattr(clipping, "_run", run)
    monkeypatch.setattr(ffmpeg_renderer, "_black_duration_ratio", lambda *a, **k: 0.0)
    monkeypatch.setattr(ffmpeg_renderer, "_freeze_metrics",
                        lambda *a, **k: {"ratio": 0.0, "longest": 0.0})
    qc = clipping._clip_qc_report(str(video), 30.0, 90, 60)
    assert qc["decision"] == "BLOCK"
    assert "decodes_cleanly" in qc["blocking_issues"]

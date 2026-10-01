from pathlib import Path
from types import SimpleNamespace


def test_long_alignment_falls_back_to_full_duration():
    from engine.captions import align_words_to_script
    script = " ".join(f"word{i}" for i in range(120))
    # A bad ASR response anchors only a tiny beginning of a five-minute track.
    asr = [{"word": "word0", "start": 0.0, "end": .2},
           {"word": "word119", "start": 91.0, "end": 92.0}]
    out = align_words_to_script(script, asr, 300.0)
    assert out[-1]["end"] == 300.0
    assert len(out) == 120


def test_professional_stock_query_stays_in_domain():
    from engine.planning.economy_storyboard import _stock_query
    shot = SimpleNamespace(
        narration="In a high stakes meeting, speak clearly under pressure.",
        visual_goal="Three communication steps", environment="", subject="")
    query = _stock_query(shot)
    assert "professional" in query and "office" in query
    assert not any(x in query for x in ("party", "casino", "dance"))


def test_youtube_download_prefers_h264(monkeypatch, tmp_path):
    import engine.clipping as clipping
    seen = {}
    monkeypatch.setattr(clipping.shutil, "which", lambda name: "/usr/bin/yt-dlp")

    def run(cmd, timeout=0):
        seen["cmd"] = cmd
        (tmp_path / "source.mp4").write_bytes(b"video")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(clipping, "_run", run)
    clipping.resolve_input("https://youtube.com/watch?v=test", str(tmp_path), True)
    selector = seen["cmd"][seen["cmd"].index("-f") + 1]
    assert "vcodec^=avc1" in selector


def test_freeze_metrics_parses_long_stuck_span(monkeypatch, tmp_path):
    import engine.render.ffmpeg_renderer as renderer
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 2048)
    report = "lavfi.freezedetect.freeze_duration: 172.5\n"
    monkeypatch.setattr(renderer.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=report))
    result = renderer._freeze_metrics(str(video), 302.0)
    assert result["longest"] == 172.5
    assert result["ratio"] > .5


def test_list_video_gets_progress_agenda_and_recap():
    from engine.project.manifest import ProductionManifest, Shot
    from engine.render.graphics import plan_overlays
    phrases = [
        "Step one: pause before answering.",
        "Step two: structure the core message.",
        "Step three: finish with a clear action.",
    ]
    shots = [
        Shot(shot_id=f"shot_{i+1:03d}", voice_start=i*20, voice_end=(i+1)*20,
             duration_target=20, narration=text)
        for i, text in enumerate(phrases)
    ]
    manifest = ProductionManifest(job_id="x", topic="3 steps to speak clearly",
                                  target_seconds=60, aspect="16:9",
                                  width=1280, height=720, shots=shots)
    kinds = [e.kind for e in plan_overlays(manifest, {})]
    assert kinds.count("progress_list") == 3
    assert "recap" in kinds

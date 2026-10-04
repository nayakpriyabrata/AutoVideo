import json
import subprocess
from types import SimpleNamespace

import pytest


def test_fit_dimensions_match_landscape_and_portrait_source(tmp_path, ffmpeg_binary, ffmpeg_media):
    from engine.clipping import fit_output_dimensions

    landscape = fit_output_dimensions(ffmpeg_media["video"])
    assert landscape == (320, 180)

    portrait_path = tmp_path / "portrait.mp4"
    created = subprocess.run(
        [ffmpeg_binary, "-y", "-v", "error", "-f", "lavfi", "-i",
         "testsrc2=size=180x320:rate=24", "-t", "1", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(portrait_path)],
        capture_output=True, text=True, timeout=30)
    assert created.returncode == 0, created.stderr
    assert fit_output_dimensions(str(portrait_path)) == (180, 320)


def test_fit_dimensions_apply_rotation_and_cap_large_sources(monkeypatch):
    import engine.clipping as clipping

    probe = {"streams": [{
        "width": 3840, "height": 2160, "sample_aspect_ratio": "1:1",
        "side_data_list": [{"rotation": "90"}],
    }]}
    monkeypatch.setattr(clipping, "_run", lambda *_a, **_k: SimpleNamespace(
        returncode=0, stdout=json.dumps(probe), stderr=""))
    assert clipping._video_display_dimensions("source.mp4") == (2160.0, 3840.0)
    assert clipping.fit_output_dimensions("source.mp4") == (1080, 1920)


def test_clip_qc_accepts_matching_landscape_dimensions(monkeypatch, tmp_path):
    import engine.clipping as clipping
    from engine.render import ffmpeg_renderer

    video = tmp_path / "landscape.mp4"
    video.write_bytes(b"x" * 4096)
    probe = {"format": {"duration": "30.0"}, "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
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
    qc = clipping._clip_qc_report(
        str(video), 30.0, 92, 80, expected_dimensions=(1920, 1080))
    assert qc["decision"] == "PASS"
    assert qc["checks"]["framing_dimensions_match"] is True
    assert qc["media"]["expected_width"] == 1920
    assert qc["media"]["expected_height"] == 1080


@pytest.mark.parametrize("width,height", [(320, 180), (180, 320)])
def test_clip_studio_fit_render_keeps_source_orientation(
        width, height, tmp_path, ffmpeg_binary, monkeypatch):
    import cv2
    from engine.clipping import create_highlight_clips
    from engine.render.ffmpeg_renderer import has_subtitles_filter

    if not has_subtitles_filter():
        pytest.skip("FFmpeg subtitle filter unavailable")
    source = tmp_path / f"source-{width}x{height}.mp4"
    made = subprocess.run(
        [ffmpeg_binary, "-y", "-v", "error", "-f", "lavfi", "-i",
         f"testsrc2=size={width}x{height}:rate=24", "-t", "3", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(source)],
        capture_output=True, text=True, timeout=30)
    assert made.returncode == 0, made.stderr

    words = [
        {"word": word, "start": 0.2 + index * 0.32, "end": 0.4 + index * 0.32}
        for index, word in enumerate(("A", "useful", "idea", "can", "help", "many", "people", "today."))
    ]
    monkeypatch.setattr("engine.clipping._duration", lambda _path: 3.0)
    monkeypatch.setattr("engine.clipping.fit_output_dimensions", lambda _path: (width, height))
    monkeypatch.setattr("engine.clipping._transcribe_in_chunks", lambda *_a, **_k: words)
    monkeypatch.setattr("engine.clipping.rank_highlights", lambda *_a, **_k: [{
        "start": 0.0, "end": 3.0, "duration": 3.0, "score": 90,
        "title": "A useful idea helps people", "text": "A useful idea can help many people today.",
        "ranking": "local",
    }])
    monkeypatch.setattr("engine.clipping._clip_qc_report", lambda *_a, **_k: {
        "decision": "PASS", "quality_score": 90, "ready_to_publish": False,
        "checks": {}, "blocking_issues": [], "review_issues": [],
    })

    result = create_highlight_clips(
        str(source), str(tmp_path / "clips"), count=1, min_seconds=1, max_seconds=3,
        source_rights="own_content", ranking_provider="local", framing="fit")
    capture = cv2.VideoCapture(result["outputs"][0])
    actual = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
              int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    capture.release()
    assert actual == (width, height)
    assert result["highlights"][0]["output_orientation"] == (
        "portrait" if height > width else "landscape")

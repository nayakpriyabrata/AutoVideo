import json
import os
import shutil

import pytest


def test_clip_broll_search_uses_highlight_orientation(tmp_path, ffmpeg_media, monkeypatch):
    from engine import broll

    output_dir = tmp_path / "clips"
    output_dir.mkdir()
    original = output_dir / "landscape-highlight.mp4"
    original.write_bytes(open(ffmpeg_media["video"], "rb").read())
    captions = output_dir / "caption.ass"
    captions.write_text("[Script Info]\n", encoding="utf-8")
    seen = {}

    def no_stock_found(slots, _assets_dir, vertical):
        seen["vertical"] = vertical
        seen["slot"] = slots[0]
        for slot in slots:
            slot["status"] = "not_found"
            slot["search_error"] = "test: no stock source called"
        return slots

    monkeypatch.setattr(broll, "_fetch_candidates", no_stock_found)
    result = {
        "source": ffmpeg_media["video"],
        "selection_report": str(output_dir / "selection-1.json"),
        "highlights": [{
            "output": str(original), "title": "Landscape footage",
            "text": "The full landscape scene stays visible.", "start": 0.0,
            "duration": 4.0, "framing": "fit", "face_center_x": 0.5,
            "caption_ass_path": str(captions),
        }],
    }
    _review_path, review = broll.prepare_clip_studio_review(
        result, max_candidates=1, default_duration=1.0)

    assert seen["vertical"] is False
    assert seen["slot"]["output_width"] == 320
    assert seen["slot"]["output_height"] == 180
    assert len(review["candidates"]) == 1
    assert review["candidates"][0]["status"] == "not_found"


@pytest.mark.parametrize("width,height", [(320, 180), (180, 320)])
def test_fit_clip_broll_composite_keeps_source_dimensions(
        tmp_path, ffmpeg_media, ffmpeg_binary, width, height):
    import subprocess
    from engine.broll import _render_clip_studio_cutaway
    from engine.render.captions_ass import build_captions
    from engine.render.ffmpeg_renderer import has_subtitles_filter

    if not has_subtitles_filter():
        pytest.skip("FFmpeg subtitle filter unavailable")
    if (width, height) == (320, 180):
        source = ffmpeg_media["video"]
    else:
        source_path = tmp_path / "portrait-source.mp4"
        created = subprocess.run(
            [ffmpeg_binary, "-y", "-v", "error", "-f", "lavfi", "-i",
             f"testsrc2=size={width}x{height}:rate=24", "-t", "4", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", str(source_path)],
            capture_output=True, text=True, timeout=30, check=False)
        assert created.returncode == 0, created.stderr
        source = str(source_path)
    original = tmp_path / f"fit-highlight-{width}x{height}.mp4"
    attached = subprocess.run([
        ffmpeg_binary, "-y", "-v", "error", "-i", source,
        "-i", ffmpeg_media["voice"], "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(original),
    ], capture_output=True, text=True, timeout=30, check=False)
    assert attached.returncode == 0, attached.stderr
    aspect = "9:16" if height > width else "16:9"
    captions = build_captions(
        [{"word": "Full scene remains visible", "start": 0.5, "end": 1.5}],
        str(tmp_path / f"fit-caption-{width}x{height}"), template="OPUS", aspect=aspect,
        W=width, H=height, duration=4.0)
    candidate = {
        "candidate_id": f"fit_clip_{width}x{height}", "source_video": source,
        "clip_output": str(original), "path": source,
        "caption_ass_path": captions["ass"], "source_start": 0.0,
        "clip_duration": 4.0, "start": 1.0, "duration": 1.0,
        "framing": "fit", "face_center_x": 0.5,
        "output_width": width, "output_height": height,
    }
    output = _render_clip_studio_cutaway(candidate)
    probe = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error",
         "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "json", output], capture_output=True, text=True, timeout=20, check=False)
    assert probe.returncode == 0, probe.stderr
    dimensions = json.loads(probe.stdout)["streams"][0]
    assert (dimensions["width"], dimensions["height"]) == (width, height)
    assert os.path.isfile(output) and output != str(original)

import json
import os
import subprocess
from types import SimpleNamespace

import pytest


def test_stock_review_requires_rights_and_exact_file_approval(tmp_path):
    from engine.broll import approved_video_overlays, save_review, sha256_file

    media = tmp_path / "stock.mp4"
    media.write_bytes(b"exact approved bytes")
    review_path = tmp_path / "broll_review.json"
    review_path.write_text(json.dumps({
        "schema_version": 1,
        "workflow": "production",
        "candidates": [{
            "candidate_id": "gap_01", "status": "ready", "path": str(media),
            "sha256": sha256_file(media), "start": 2.0, "duration": 1.5,
            "approved": False, "rights_reviewed": False,
        }],
    }), encoding="utf-8")

    assert approved_video_overlays(str(review_path), 10.0) == []
    saved = save_review(str(review_path), {
        "gap_01": {"start": 3.0, "duration": 2.0, "approved": True,
                   "rights_reviewed": False},
    })
    assert saved["candidates"][0]["approved"] is False
    assert approved_video_overlays(str(review_path), 10.0) == []

    save_review(str(review_path), {
        "gap_01": {"start": 3.0, "duration": 2.0, "approved": True,
                   "rights_reviewed": True},
    })
    overlays = approved_video_overlays(str(review_path), 10.0)
    assert len(overlays) == 1
    assert overlays[0]["start"] == 3.0 and overlays[0]["end"] == 5.0
    assert overlays[0]["path"] == str(media)

    media.write_bytes(b"replacement media changed after approval")
    with pytest.raises(ValueError, match="changed or disappeared"):
        approved_video_overlays(str(review_path), 10.0)


def test_stock_review_rejects_out_of_timeline_cutaways(tmp_path):
    from engine.broll import approved_video_overlays, save_review, sha256_file

    media = tmp_path / "stock.mp4"
    media.write_bytes(b"exact approved bytes")
    review_path = tmp_path / "broll_review.json"
    review_path.write_text(json.dumps({
        "schema_version": 1, "workflow": "production",
        "candidates": [{"candidate_id": "gap_01", "status": "ready",
                         "path": str(media), "sha256": sha256_file(media),
                         "start": 9.0, "duration": 2.0,
                         "approved": True, "rights_reviewed": True}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the final timeline"):
        approved_video_overlays(str(review_path), 10.0)


def test_job_candidate_slots_follow_scene_boundaries_and_are_spread():
    from engine.broll import _job_slots

    shots = [
        SimpleNamespace(shot_id=f"shot_{i:03d}", voice_start=(i - 1) * 4.0,
                        voice_end=i * 4.0, subject=f"subject{i}", visual_goal=f"action{i}",
                        environment="garden", narration=f"Scene {i} shows sunlight.", stock_query="")
        for i in range(1, 7)
    ]
    manifest = SimpleNamespace(shots=shots, aspect="9:16")
    factory = SimpleNamespace(
        pm=SimpleNamespace(load_manifest=lambda _job: manifest),
    )
    slots, vertical = _job_slots(factory, "job-1", max_candidates=2, default_duration=2.0)
    assert vertical is True
    assert len(slots) == 2
    assert all("between" in x["label"].lower() for x in slots)
    assert slots[0]["start"] < slots[1]["start"]
    assert all(x["duration"] == 2.0 and x["query"] for x in slots)


def test_clip_studio_stock_suggestions_are_unapproved_and_keep_original(tmp_path, ffmpeg_media, monkeypatch):
    from engine.broll import prepare_clip_studio_review, load_review
    from engine.providers.stock_provider import StockProvider

    stock_path = ffmpeg_media["video"]
    monkeypatch.setattr(StockProvider, "_pick_local",
                        classmethod(lambda cls, query, excluded=None: stock_path))
    output_dir = tmp_path / "clips"
    output_dir.mkdir()
    original = output_dir / "highlight.mp4"
    original.write_bytes(open(ffmpeg_media["video"], "rb").read())
    ass = output_dir / "caption.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    result = {
        "source": ffmpeg_media["video"],
        "selection_report": str(output_dir / "selection-123.json"),
        "highlights": [{
            "output": str(original), "title": "Sunlight and growth",
            "text": "Plants need sunlight to grow well.", "start": 0.0,
            "duration": 4.0, "framing": "fit", "face_center_x": 0.5,
            "caption_ass_path": str(ass),
        }],
    }
    review_path, review = prepare_clip_studio_review(result, max_candidates=1, default_duration=1.0)
    loaded = load_review(review_path)
    candidate = loaded["candidates"][0]
    assert candidate["status"] == "ready"
    assert candidate["approved"] is False
    assert candidate["rights_reviewed"] is False
    assert candidate["decision"] == "pending"
    assert "sunlight" in candidate["query"].lower()
    assert "growth" in candidate["query"].lower()
    assert candidate["clip_output"] == str(original)
    assert candidate["path"] != candidate["clip_output"]
    assert os.path.isfile(candidate["path"])
    assert review["workflow"] == "clip_studio"


def test_ffmpeg_graph_places_video_cutaway_without_changing_duration(tmp_path, ffmpeg_media):
    from engine.render.ffmpeg_renderer import build_ffmpeg_cmd

    stock = tmp_path / "stock.mp4"
    stock.write_bytes(open(ffmpeg_media["video"], "rb").read())
    segments = [{"src": ffmpeg_media["video"], "in": 0.0, "dur": 4.0,
                 "freeze": 0.0, "hard_cut": True}]
    cmd, meta = build_ffmpeg_cmd(
        segments, None, str(tmp_path / "out.mp4"), W=320, H=180, fps=24,
        encoder="libx264", use_loudnorm=False, safe_concat=True,
        video_overlays=[{"path": str(stock), "start": 1.0, "end": 3.0, "in": 0.0}],
    )
    graph = meta["filter_complex"]
    assert meta["total"] == 4.0
    assert meta["video_overlays"] == 1
    assert str(stock) in cmd
    assert "enable='between(t,1.000,3.000)'" in graph
    assert "eof_action=pass" in graph
    assert "[aout]" not in graph


def test_ffmpeg_renders_broll_as_video_only_layer(tmp_path, ffmpeg_media, ffmpeg_binary):
    from engine.render.ffmpeg_renderer import render_ffmpeg
    import cv2
    import numpy as np

    stock = tmp_path / "hue-shifted-stock.mp4"
    transformed = subprocess.run([
        ffmpeg_binary, "-y", "-v", "error", "-i", ffmpeg_media["video"],
        "-vf", "hue=h=150", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(stock),
    ], capture_output=True, text=True, timeout=30)
    assert transformed.returncode == 0, transformed.stderr
    out = tmp_path / "with-cutaway.mp4"
    result = render_ffmpeg(
        [{"src": ffmpeg_media["video"], "in": 0.0, "dur": 4.0,
          "freeze": 0.0, "hard_cut": True}],
        None, str(out), W=320, H=180, fps=24, quality="preview",
        encoder="libx264", use_loudnorm=False, safe_concat=True,
        video_overlays=[{"path": str(stock), "start": 1.0, "end": 3.0, "in": 0.0}],
    )
    assert os.path.isfile(result["video"])
    assert result["total"] == 4.0
    assert result["video_overlays"] == 1
    assert result["audio_present"] is False

    def frame_at(path, seconds):
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = cap.read()
        cap.release()
        assert ok
        return frame.astype(np.int16)

    source_frame = frame_at(ffmpeg_media["video"], 1.5)
    edited_frame = frame_at(result["video"], 1.5)
    assert np.mean(np.abs(source_frame - edited_frame)) > 15, "approved B-roll was not visible at its placement"
    before_frame = frame_at(ffmpeg_media["video"], 0.8)
    before_output = frame_at(result["video"], 0.8)
    assert np.mean(np.abs(before_frame - before_output)) < 35, "B-roll replaced video outside its approved window"


def test_clip_studio_cutaway_reencodes_picture_but_keeps_original_audio(tmp_path, ffmpeg_media, ffmpeg_binary):
    from engine.broll import _render_clip_studio_cutaway
    from engine.render.captions_ass import build_captions
    from engine.render.ffmpeg_renderer import has_subtitles_filter

    if not has_subtitles_filter():
        pytest.skip("FFmpeg subtitle filter unavailable")
    source = ffmpeg_media["video"]
    original = tmp_path / "highlight-with-audio.mp4"
    attached = subprocess.run([
        ffmpeg_binary, "-y", "-v", "error", "-i", source,
        "-i", ffmpeg_media["voice"], "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(original),
    ], capture_output=True, text=True, timeout=30)
    assert attached.returncode == 0, attached.stderr
    captions = build_captions(
        [{"word": "A useful idea", "start": 0.5, "end": 1.5}],
        str(tmp_path / "caption"), template="OPUS", aspect="9:16",
        W=1080, H=1920, duration=4.0)
    candidate = {
        "candidate_id": "clip_01", "source_video": source,
        "clip_output": str(original), "path": source,
        "caption_ass_path": captions["ass"], "source_start": 0.0,
        "clip_duration": 4.0, "start": 1.0, "duration": 1.0,
        "framing": "fit", "face_center_x": 0.5,
    }
    before = original.read_bytes()
    output = _render_clip_studio_cutaway(candidate)
    assert os.path.isfile(output) and output != str(original)
    assert original.read_bytes() == before
    decoded = subprocess.run([ffmpeg_binary, "-hide_banner", "-i", output,
                              "-t", "0.1", "-f", "null", "-"],
                             capture_output=True, text=True, timeout=20)
    assert decoded.returncode == 0, decoded.stderr
    assert "Video:" in decoded.stderr and "Audio:" in decoded.stderr

def test_broll_review_blocks_pending_suggestions_until_explicit_approve_or_skip(tmp_path):
    from engine.broll import sha256_file, save_review, validate_review_decisions

    media = tmp_path / "candidate.mp4"
    media.write_bytes(b"candidate bytes for exact identity")
    report_path = tmp_path / "broll_review.json"
    report_path.write_text(json.dumps({
        "schema_version": 1,
        "workflow": "production",
        "candidates": [{
            "candidate_id": "gap_01", "status": "ready", "path": str(media),
            "sha256": sha256_file(media), "start": 1.0, "duration": 1.0,
            "approved": False, "rights_reviewed": False, "decision": "pending",
        }, {
            "candidate_id": "gap_02", "status": "not_found", "path": "",
            "search_error": "No matching stock video.", "approved": False,
            "rights_reviewed": False, "decision": "pending",
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="Explicitly approve or skip every suggestion"):
        validate_review_decisions(str(report_path), workflow="production")

    saved = save_review(str(report_path), {
        "gap_01": {"decision": "approve", "rights_reviewed": True,
                   "start": 1.0, "duration": 1.0},
        "gap_02": {"decision": "skip"},
    })
    assert [x["decision"] for x in saved["candidates"]] == ["approved", "skipped"]
    assert validate_review_decisions(str(report_path), workflow="production")["workflow"] == "production"


def test_clip_studio_apply_requires_each_suggestion_decision_to_be_saved(tmp_path):
    from engine.broll import apply_clip_studio_review

    review_path = tmp_path / "clip_review.json"
    review_path.write_text(json.dumps({
        "schema_version": 1, "workflow": "clip_studio",
        "candidates": [{"candidate_id": "clip_01", "status": "not_found",
                         "path": "", "decision": "pending", "approved": False,
                         "rights_reviewed": False}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="Explicitly approve or skip every suggestion"):
        apply_clip_studio_review(str(review_path))


def test_stock_search_failure_is_recorded_without_exposing_request_details(tmp_path, monkeypatch):
    import engine.broll as broll
    from engine.providers.stock_provider import StockProvider

    monkeypatch.setattr(StockProvider, "_pick_local", classmethod(lambda cls, query, excluded=None: None))
    monkeypatch.setattr("engine.stock_video.get_stock_videos", lambda *a, **k: {
        "clips": [], "metadata": [],
        "errors": ["No matching API stock video; check PEXELS_API_KEY/PIXABAY_API_KEY and network access."],
    })
    candidates = broll._fetch_candidates(
        [{"candidate_id": "cut_01", "query": "sunlight plants"}], str(tmp_path), True)
    assert candidates[0]["status"] == "not_found"
    assert "PEXELS_API_KEY/PIXABAY_API_KEY" in candidates[0]["search_error"]
    assert "token=" not in candidates[0]["search_error"]

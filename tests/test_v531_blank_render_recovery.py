from pathlib import Path

from engine.render.ffmpeg_renderer import build_ffmpeg_cmd


def _segments(tmp_path: Path):
    # Build-only tests do not need real media to exist.
    return [
        {"src": str(tmp_path / "a.mp4"), "in": 0, "dur": 4.0, "freeze": 0, "trans_out": "dissolve"},
        {"src": str(tmp_path / "b.mp4"), "in": 0, "dur": 4.0, "freeze": 0, "trans_out": "cut"},
        {"src": str(tmp_path / "c.mp4"), "in": 0, "dur": 4.0, "freeze": 0, "trans_out": "fadeout"},
    ]


def test_primary_xfade_graph_is_preserved(tmp_path):
    cmd, meta = build_ffmpeg_cmd(
        _segments(tmp_path), str(tmp_path / "voice.m4a"), str(tmp_path / "out.mp4"),
        W=640, H=360, encoder="libx264", use_loudnorm=False,
    )
    graph = meta["filter_complex"]
    assert "xfade=" in graph
    assert not meta["safe_concat"]


def test_safe_concat_graph_has_no_xfade(tmp_path):
    cmd, meta = build_ffmpeg_cmd(
        _segments(tmp_path), str(tmp_path / "voice.m4a"), str(tmp_path / "out.mp4"),
        W=640, H=360, encoder="libx264", use_loudnorm=False, safe_concat=True,
    )
    graph = meta["filter_complex"]
    assert "concat=n=3:v=1:a=0" in graph
    assert "trim=duration=" in graph
    assert graph.count("setpts=PTS-STARTPTS") >= 3
    assert "xfade=" not in graph
    assert meta["safe_concat"] is True

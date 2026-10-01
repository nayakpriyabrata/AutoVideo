import pytest
from pathlib import Path


def _words(seconds=120):
    out = []
    for i in range(seconds * 2):
        token = "secret" if 50 <= i < 80 else "practice"
        if i % 16 == 15:
            token += "."
        out.append({"word": token, "start": i * .5, "end": i * .5 + .42})
    return out


def test_highlight_ranker_returns_spaced_complete_windows():
    from engine.clipping import rank_highlights
    clips = rank_highlights(_words(), 120, count=3, min_seconds=20, max_seconds=35)
    assert 1 <= len(clips) <= 3
    assert all(20 <= c["duration"] <= 36 for c in clips)
    for a, b in zip(clips, clips[1:]):
        assert a["end"] <= b["start"] or b["end"] <= a["start"]


def test_url_input_requires_rights_confirmation(tmp_path):
    from engine.clipping import resolve_input
    with pytest.raises(RuntimeError, match="rights-confirmed"):
        resolve_input("https://www.youtube.com/watch?v=example", str(tmp_path), False)


def test_local_input_needs_no_rights_flag(tmp_path):
    from engine.clipping import resolve_input
    p = tmp_path / "mine.mp4"
    p.write_bytes(b"x")
    assert resolve_input(str(p), str(tmp_path), False) == str(p.resolve())


def test_url_uses_python_module_when_user_bin_is_not_on_path(monkeypatch, tmp_path):
    import engine.clipping as clipping
    seen = {}
    monkeypatch.setattr(clipping.shutil, "which", lambda name: None)
    monkeypatch.setattr(clipping.importlib.util, "find_spec", lambda name: object())

    def run(cmd, timeout=0):
        seen["cmd"] = cmd
        (tmp_path / "source.mp4").write_bytes(b"video")
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(clipping, "_run", run)
    out = clipping.resolve_input("https://youtube.com/watch?v=test", str(tmp_path), True)
    assert out.endswith("source.mp4")
    assert seen["cmd"][:3] == [clipping.sys.executable, "-m", "yt_dlp"]


def test_long_speech_is_transcribed_as_small_chunks_with_offsets(monkeypatch, tmp_path):
    import engine.clipping as clipping
    import engine.captions as captions
    calls = []

    def run(cmd, timeout=0):
        Path(cmd[-1]).write_bytes(b"x" * 1024)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    def words(path, **kwargs):
        calls.append(path)
        return [{"word": "hello.", "start": 1.0, "end": 1.5}]

    monkeypatch.setattr(clipping, "_run", run)
    monkeypatch.setattr(captions, "get_word_timestamps", words)
    result = clipping._transcribe_in_chunks("long.mp4", str(tmp_path), 650, "auto", lambda *a: None)
    assert len(calls) == 3
    assert [w["start"] for w in result] == [1.0, 301.0, 601.0]

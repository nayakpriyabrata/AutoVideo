import json
from types import SimpleNamespace

import pytest


def test_pixabay_music_source_records_page_license_creator_and_hash(tmp_path, monkeypatch):
    import engine.audio.music_provider as provider

    calls = []

    def fake_run(command, capture_output, text, timeout):
        calls.append(command)
        output_path = command[-1]
        with open(output_path, "wb") as handle:
            handle.write(b"soft-music-bytes" * 4000)
        with open(output_path + ".source.json", "w", encoding="utf-8") as handle:
            json.dump({"media_url": "https://cdn.example/track.mp3?token=private",
                       "page_url": "https://pixabay.com/music/example-track/"}, handle)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "source": "pixabay-browser", "license": "Pixabay Content License",
            "page_url": "https://pixabay.com/music/example-track/",
            "creator": "Example Artist", "asset_name": "Soft Piano",
            "asset_id": "track-42", "query": "soft piano ambient",
        }), stderr="")

    monkeypatch.setattr(provider.subprocess, "run", fake_run)
    monkeypatch.setattr(provider, "pick_music", lambda mood: (_ for _ in ()).throw(AssertionError("Pixabay mode must not silently choose local music")))
    result = provider.ensure_background_music("soft piano ambient", str(tmp_path), mode="pixabay")

    assert calls and calls[0][3] == "music"
    assert result["source"] == "pixabay-browser"
    assert result["page_url"].startswith("https://pixabay.com/music/")
    assert result["creator"] == "Example Artist"
    assert result["license"] == "Pixabay Content License"
    assert len(result["sha256"]) == 64
    assert "token=private" not in json.dumps(result)
    assert not (tmp_path / (result["path"].split("/")[-1] + ".source.json")).exists()


def test_pixabay_search_failure_is_actionable_and_removes_temporary_artifacts(tmp_path, monkeypatch):
    import engine.audio.music_provider as provider

    def failed_search(command, **kwargs):
        assert kwargs["timeout"] == 240
        output_path = command[-1]
        with open(output_path, "wb") as handle:
            handle.write(b"partial audio")
        with open(output_path + ".part", "wb") as handle:
            handle.write(b"partial download")
        with open(output_path + ".source.json", "w", encoding="utf-8") as handle:
            handle.write('{"media_url":"https://cdn.pixabay.com/audio/track.mp3?token=private"}')
        return SimpleNamespace(
            returncode=2, stdout="",
            stderr=("AUTOVIDEO_MEDIA_SEARCH=no_track_results\n"
                    "https://cdn.pixabay.com/audio/track.mp3?token=private"),
        )

    monkeypatch.setattr(provider.subprocess, "run", failed_search)
    result = provider.ensure_background_music("soft ambient instrumental", str(tmp_path), mode="pixabay")

    assert result["path"] is None
    assert "Try a concrete term" in result["error"]
    assert "token=private" not in result["error"]
    assert list(tmp_path.iterdir()) == []


def test_pixabay_search_timeout_is_actionable_and_cleans_partial_file(tmp_path, monkeypatch):
    import engine.audio.music_provider as provider

    def timed_out(command, **kwargs):
        output_path = command[-1]
        with open(output_path + ".part", "wb") as handle:
            handle.write(b"partial download")
        raise provider.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(provider.subprocess, "run", timed_out)
    result = provider.ensure_background_music("soft ambient instrumental", str(tmp_path), mode="pixabay")

    assert result["path"] is None
    assert "four-minute" in result["error"]
    assert list(tmp_path.iterdir()) == []


def test_enabled_internet_music_is_fetched_before_source_processing(tmp_path, monkeypatch):
    import engine.clipping as clipping
    import engine.audio.music_provider as music_provider

    source_stage = []
    music_calls = []
    music = tmp_path / "downloaded.mp3"
    music.write_bytes(b"fresh music")

    def fetch(mood, workdir, mode="auto"):
        music_calls.append((mood, mode))
        return {"path": str(music), "source": "pixabay-browser",
                "license": "Pixabay Content License", "page_url": "https://pixabay.com/music/test/",
                "sha256": "a" * 64}

    def stop_at_source(*args, **kwargs):
        source_stage.append(True)
        raise RuntimeError("source stage reached")

    monkeypatch.setattr(music_provider, "ensure_background_music", fetch)
    monkeypatch.setattr(clipping, "resolve_input", stop_at_source)
    with pytest.raises(RuntimeError, match="source stage reached"):
        clipping.create_highlight_clips(
            "owned.mp4", str(tmp_path / "out"), source_rights="own_content",
            background_music_enabled=True, background_music_source="pixabay",
            music_mood="soft piano", music_license="none")
    assert music_calls == [("soft piano", "pixabay")]
    assert source_stage == [True]


def test_local_music_source_page_is_preserved_without_acknowledgement(tmp_path, monkeypatch):
    import engine.clipping as clipping

    source = tmp_path / "source.mp4"
    music = tmp_path / "track.mp3"
    source.write_bytes(b"video")
    music.write_bytes(b"my user selected audio")
    reached = []
    monkeypatch.setattr(clipping, "resolve_input",
                        lambda *a, **k: (reached.append(True), (_ for _ in ()).throw(RuntimeError("stop")))[1])
    with pytest.raises(RuntimeError, match="stop"):
        clipping.create_highlight_clips(
            str(source), str(tmp_path / "out"), source_rights="own_content",
            background_music_enabled=True, background_music=str(music),
            background_music_source="local", background_music_source_url="YouTube Audio Library: track credit",
            music_license="none")
    assert reached

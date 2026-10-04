def test_pixabay_audio_search_does_not_mistake_thumbnails_for_tracks():
    from engine.providers.web_media_helper import _extract_media_urls

    class Page:
        def evaluate(self, _script, _kind):
            return [
                "https://cdn.pixabay.com/audio/2026/08/03/16-02-59_200x200.jpg",
                "https://cdn.pixabay.com/audio/2026/08/03/soft-ambient.mp3?download=1",
                "https://evil.example/audio/hidden.mp3",
                "http://cdn.pixabay.com/audio/insecure.mp3",
                "https://pixabay.com/music/soft-piano.mp3",
            ]

    urls = _extract_media_urls(Page(), "music")
    assert urls == [
        "https://cdn.pixabay.com/audio/2026/08/03/soft-ambient.mp3?download=1",
        "https://pixabay.com/music/soft-piano.mp3",
    ]


def test_music_item_page_extraction_ignores_search_and_tag_links():
    from engine.providers.web_media_helper import _music_result_pages

    class Locator:
        def evaluate_all(self, _script):
            return [
                "/music/search/soft-piano/",
                "/music/search/genre/ambient/",
                "/music/ambient-soft-piano-123456/",
                "https://pixabay.com/music/calm-background-987654/",
                "https://evil.example/music/wrong-111/",
                "/music/ambient-soft-piano-123456/",
            ]

    class Page:
        def locator(self, _selector):
            return Locator()

    assert _music_result_pages(Page()) == [
        "https://pixabay.com/music/ambient-soft-piano-123456/",
        "https://pixabay.com/music/calm-background-987654/",
    ]


def test_media_download_rejects_image_payload_and_cleans_partial_file(tmp_path, monkeypatch):
    from engine.providers import web_media_helper as helper

    class Response:
        url = "https://cdn.pixabay.com/audio/thumb.jpg"
        headers = {"content-type": "image/jpeg", "content-length": "40000"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, _size):
            yield b"x" * 40000

    monkeypatch.setattr(helper.requests, "get", lambda *a, **k: Response())
    target = tmp_path / "music.mp3"
    assert helper._download(
        "https://cdn.pixabay.com/audio/thumb.jpg", str(target),
        "https://pixabay.com/music/example-123/", kind="music") is False
    assert not target.exists()
    assert not (tmp_path / "music.mp3.part").exists()


def test_media_download_requires_valid_audio_bytes_and_accepts_mp3(tmp_path, monkeypatch):
    from engine.providers import web_media_helper as helper

    class Response:
        def __init__(self, url, content_type, data):
            self.url = url
            self.headers = {"content-type": content_type, "content-length": str(len(data))}
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, _size):
            yield self.data

    audio_url = "https://cdn.pixabay.com/audio/soft-piano.mp3"
    audio_data = b"ID3" + b"a" * 40000
    monkeypatch.setattr(
        helper.requests, "get",
        lambda url, **_kwargs: Response(url, "audio/mpeg", audio_data))
    target = tmp_path / "music.mp3"
    assert helper._download(
        audio_url, str(target), "https://pixabay.com/music/example-123/", kind="music") is True
    assert target.read_bytes() == audio_data

    image_data = b"not-audio" * 5000
    monkeypatch.setattr(
        helper.requests, "get",
        lambda url, **_kwargs: Response(url, "application/octet-stream", image_data))
    rejected = tmp_path / "bad.mp3"
    assert helper._download(
        audio_url, str(rejected), "https://pixabay.com/music/example-123/", kind="music") is False
    assert not rejected.exists()


def test_music_search_status_translates_without_echoing_raw_errors():
    from engine.audio.music_provider import _safe_browser_search_error

    message = _safe_browser_search_error(
        "AUTOVIDEO_MEDIA_SEARCH=browser_install_missing\n"
        "https://cdn.pixabay.com/audio/track.mp3?token=private")
    assert "playwright install chromium" in message
    assert "token=private" not in message

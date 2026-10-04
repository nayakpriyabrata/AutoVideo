"""Regressions for Flow Agent type selection and safe pending-video recovery."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json

import engine.providers.flow_browser as flow_module
from engine.providers.flow_browser import (
    FlowBrowser,
    FlowBrowserProvider,
    FlowUIChanged,
    media_signature_kind,
)


class _Clock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def monotonic(self):
        return self.now

    def advance_ms(self, milliseconds):
        self.now += max(0, int(milliseconds)) / 1000.0


class _Locator:
    def __init__(self):
        self.clicks = 0

    def click(self):
        self.clicks += 1


class _Keyboard:
    def press(self, _key):
        return None


def _wait_browser(clock, asset_supplier):
    browser = FlowBrowser.__new__(FlowBrowser)
    browser.ui = {"timeouts": {"generation": 20, "poll_interval": 0.01}, "actions": {}}
    browser.state_cb = None
    browser.detect_failure = lambda: None
    browser.detect_service_busy = lambda: None
    browser._set = lambda _state: None
    browser._page = SimpleNamespace(
        inner_text=lambda _selector: "done",
        wait_for_timeout=clock.advance_ms,
    )
    browser.media_assets = asset_supplier
    return browser


def test_agent_preparation_selects_visible_video_type_before_prompt():
    browser = FlowBrowser.__new__(FlowBrowser)
    browser.detect_editor_mode = lambda: "agent"
    picker, video_option = _Locator(), _Locator()
    browser._try_resolve = lambda action, timeout_ms=0: (
        picker if action == "generation_type_picker" else None)
    browser._resolve = lambda action, timeout_ms=0: (
        video_option if action == "video_option" else (_ for _ in ()).throw(
            AssertionError(f"unexpected action: {action}")))
    browser._page = SimpleNamespace(wait_for_timeout=lambda _ms: None, keyboard=_Keyboard())

    assert browser.prepare_text_video("16:9", "Gemini Omni Flash 360p", 8, 1) == "agent"
    assert picker.clicks == 1
    assert video_option.clicks == 1


def test_visible_type_picker_without_video_option_fails_before_submission():
    browser = FlowBrowser.__new__(FlowBrowser)
    browser.detect_editor_mode = lambda: "agent"
    browser._try_resolve = lambda action, timeout_ms=0: _Locator() if action == "generation_type_picker" else None
    browser._resolve = lambda action, timeout_ms=0: (_ for _ in ()).throw(
        FlowUIChanged("Video option is missing"))
    browser._page = SimpleNamespace(wait_for_timeout=lambda _ms: None, keyboard=_Keyboard())

    try:
        browser.prepare_text_video("9:16", "Gemini Omni Flash 360p", 8, 1)
    except FlowUIChanged as error:
        assert "prompt was not submitted" in str(error)
    else:
        raise AssertionError("must not send a video prompt while the visible picker is unresolved")


def test_video_wait_never_completes_on_a_fresh_image_only(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(flow_module, "time", clock)
    browser = _wait_browser(clock, lambda: [
        {"sig": "old", "kind": "image"},
        {"sig": "fresh-still", "kind": "image"},
    ])

    completed = browser.wait_for_agent_generation(
        before_assets={"old"}, timeout_s=12, required_kind="video",
        video_ready_grace_s=5,
    )

    assert completed is False
    assert browser.last_generated_asset_signature is None


def test_video_wait_keeps_polling_after_still_until_explicit_video_is_stable(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(flow_module, "time", clock)

    def assets():
        found = [
            {"sig": "old", "kind": "image"},
            {"sig": "fresh-still", "kind": "image"},
        ]
        if clock.now >= 6:
            found.append({"sig": "fresh-video", "kind": "video"})
        return found

    browser = _wait_browser(clock, assets)

    assert browser.wait_for_agent_generation(
        before_assets={"old"}, timeout_s=20, required_kind="video",
        video_ready_grace_s=5,
    ) is True
    assert browser.last_generated_asset_signature == "fresh-video"


def test_stable_fresh_video_does_not_wait_for_stale_page_wide_busy_text(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(flow_module, "time", clock)
    browser = _wait_browser(clock, lambda: [
        {"sig": "old", "kind": "image"},
        {"sig": "fresh-video", "kind": "video"},
    ])
    # Flow's conversation history can retain these words after the current
    # request is done. They must not block an exact, stable video tile forever.
    browser._page.inner_text = lambda _selector: (
        "Previous request pending; earlier generation in progress. New clip is ready.")

    assert browser.wait_for_agent_generation(
        before_assets={"old"}, timeout_s=8, required_kind="video",
    ) is True
    assert browser.last_generated_asset_signature == "fresh-video"
    assert 3.0 <= clock.now <= 4.0


def test_flow_signature_classifier_recognizes_material_play_arrow_but_not_a_still():
    assert FlowBrowser._classify_media_kind(
        "IMG", "https://media.google/opaque-still", "", "", False, False, False
    ) == "image"
    assert FlowBrowser._classify_media_kind(
        "IMG", "https://media.google/opaque-video", "", "play_arrow", False, False, False
    ) == "video"
    assert FlowBrowser._classify_media_kind(
        "IMG", "https://media.google/clip.mp4?signature=hidden", "", "", False, False, False
    ) == "video"


def test_gallery_video_tile_ignores_queue_text_from_a_separate_flow_chat_message():
    queue_message = "Your video has been scheduled and is waiting in a high-demand queue."
    raw_tile = {
        "src": "https://media.google/generated-clip",
        "alt": "",
        "tag": "IMG",
        "dom_index": 0,
        "width": 320,
        "height": 180,
        "hint": queue_message,  # broad ancestor diagnostic includes the side-panel chat
        "tile_hint": "play_arrow 360p",
        "queue_context": False,  # not in this gallery tile's own card
        "hasPlay": True,
        "hasResolution": True,
        "hasVideoNode": False,
    }
    browser = FlowBrowser.__new__(FlowBrowser)
    browser._page = SimpleNamespace(evaluate=lambda _script: [raw_tile])

    asset = browser.media_assets()[0]

    assert asset["kind"] == "video"
    assert "|video|" in asset["sig"]


def test_queue_message_local_to_its_thumbnail_keeps_that_tile_pending():
    queue_message = "Your video has been scheduled and is waiting in a high-demand queue."
    raw_tile = {
        "src": "https://media.google/queued-thumb",
        "alt": "",
        "tag": "IMG",
        "dom_index": 0,
        "width": 320,
        "height": 180,
        "hint": queue_message,
        "tile_hint": queue_message + " play_arrow 360p",
        "queue_context": True,
        "hasPlay": True,
        "hasResolution": True,
        "hasVideoNode": False,
    }
    browser = FlowBrowser.__new__(FlowBrowser)
    browser._page = SimpleNamespace(evaluate=lambda _script: [raw_tile])

    assert browser.media_assets()[0]["kind"] == "pending"


def test_resume_rejects_saved_image_signature_and_downloads_only_unique_fresh_video(tmp_path):
    project_url = "https://flow.google.com/project/saved-project"
    image_sig = "IMG|https://media.google/still|still|image|320|180"
    video_sig = "VIDEO|https://media.google/clip|preview|video|320|180"
    assets = [
        {"sig": "old", "kind": "image"},
        {"sig": image_sig, "kind": "image"},
        {"sig": video_sig, "kind": "video"},
    ]

    class _Bridge:
        def __init__(self):
            self.downloads = []

        def ensure_project(self, _project, project_url=None):
            assert project_url == project_url_expected

        def media_assets(self):
            return list(assets)

        def download_latest_asset(self, out_path, preferred_signature=None, before_signatures=None):
            self.downloads.append((preferred_signature, set(before_signatures or set())))
            Path(out_path).write_bytes(b"validated-video")
            return out_path

    project_url_expected = project_url
    bridge = _Bridge()
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    provider.bridge = bridge
    provider._ensure = lambda: bridge
    provider._asset_valid = lambda path, kind: (
        kind == "video" and Path(path).is_file()
        and Path(path).read_bytes() == b"validated-video")
    provider._generate_video_once = lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("pending recovery must never submit another generation"))

    shot = SimpleNamespace(shot_id="shot_017", model="omni_draft")
    compiled = {"prompt": "exact pending video prompt", "project": "Flow job",
                "project_url": project_url}
    request_hash = hashlib.sha256(json.dumps(
        ["video", shot.shot_id, compiled["prompt"], True], sort_keys=True
    ).encode()).hexdigest()
    output = tmp_path / "take.mp4"
    journal = Path(str(output) + ".flow-request.json")
    journal.write_text(json.dumps({
        "status": "pending", "kind": "video", "project_url": project_url,
        "baseline": ["old"], "signature": image_sig,
        "request_hash": request_hash,
    }), encoding="utf-8")

    result = provider._guarded_generation_once(
        shot, compiled, {}, str(output), True, False, "video")

    saved = json.loads(journal.read_text(encoding="utf-8"))
    assert result["path"] == str(output)
    assert saved["status"] == "downloaded"
    assert saved["signature"] == video_sig
    assert saved["rejected_signatures"] == [image_sig]
    assert saved["signature_kind_rejected"] == "image"
    assert bridge.downloads == [(video_sig, {"old"})]
    assert output.read_bytes() == b"validated-video"


def test_resume_with_only_the_saved_still_remains_pending_without_download_or_regeneration(tmp_path):
    project_url = "https://flow.google.com/project/saved-project"
    image_sig = "IMG|https://media.google/still|still|image|320|180"
    assets = [
        {"sig": "old", "kind": "image"},
        {"sig": image_sig, "kind": "image"},
    ]

    class _Bridge:
        def __init__(self):
            self.downloads = []
            self._page = SimpleNamespace(wait_for_timeout=lambda _ms: None)

        def ensure_project(self, _project, project_url=None):
            assert project_url == project_url_expected

        def media_assets(self):
            return list(assets)

        def download_latest_asset(self, *args, **kwargs):
            self.downloads.append((args, kwargs))
            raise AssertionError("an image must not be downloaded as the pending video")

    project_url_expected = project_url
    bridge = _Bridge()
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    provider.bridge = bridge
    provider._ensure = lambda: bridge
    provider._asset_valid = lambda path, kind: False
    provider._generate_video_once = lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("pending recovery must never submit another generation"))

    shot = SimpleNamespace(shot_id="shot_017", model="omni_draft")
    compiled = {"prompt": "exact pending video prompt", "project": "Flow job",
                "project_url": project_url, "flow_image_signature_wait_ms": 10}
    request_hash = hashlib.sha256(json.dumps(
        ["video", shot.shot_id, compiled["prompt"], True], sort_keys=True
    ).encode()).hexdigest()
    output = tmp_path / "take.mp4"
    journal = Path(str(output) + ".flow-request.json")
    journal.write_text(json.dumps({
        "status": "pending", "kind": "video", "project_url": project_url,
        "baseline": ["old"], "signature": image_sig,
        "request_hash": request_hash,
    }), encoding="utf-8")

    from engine.providers.flow_browser import FlowRequestPending
    try:
        provider._guarded_generation_once(shot, compiled, {}, str(output), True, False, "video")
    except FlowRequestPending as error:
        assert "Generation is blocked to avoid spending again" in str(error)
        assert "no recovery click submitted" in str(error)
    else:
        raise AssertionError("a still-only project cannot complete a pending video request")

    saved = json.loads(journal.read_text(encoding="utf-8"))
    diagnostic = json.loads(Path(str(output) + ".recovery.json").read_text(encoding="utf-8"))
    assert saved["signature"] == ""
    assert saved["rejected_signatures"] == [image_sig]
    assert bridge.downloads == []
    assert diagnostic["new_generations"] == 0
    assert diagnostic["visible_assets_available"] is True


def test_viewer_image_download_falls_back_to_exact_download_url_after_target_close(tmp_path, monkeypatch):
    import io
    from PIL import Image
    import requests

    image_data = io.BytesIO()
    Image.new("RGB", (320, 180), "navy").save(image_data, format="PNG")
    png_bytes = image_data.getvalue()
    url = "https://download.google/asset.png?signature=not-logged"
    requested_urls = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, _size):
            yield png_bytes

    class _Session:
        trust_env = True

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, requested_url, **_kwargs):
            requested_urls.append(requested_url)
            return _Response()

    monkeypatch.setattr(requests, "Session", _Session)

    class _Download:
        def __init__(self):
            self.url = url

        def path(self):
            return None

        def save_as(self, _path):
            raise RuntimeError("TargetClosedError: target page closed during save_as")

    class _Element:
        first = None

        def __init__(self):
            self.first = self

        def is_visible(self, timeout=0):
            return True

        def bounding_box(self):
            return {"x": 0, "y": 0, "width": 320, "height": 180}

        def click(self, **_kwargs):
            return None

    class _Elements:
        def __init__(self, element):
            self.element = element

        def count(self):
            return 1

        def nth(self, _index):
            return self.element

    class _DownloadContext:
        value = _Download()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class _Page:
        url = "https://flow.google.com/project/test"

        def locator(self, _selector):
            return _Elements(_Element())

        def expect_download(self, timeout=0):
            return _DownloadContext()

        def wait_for_timeout(self, _ms):
            return None

    browser = FlowBrowser.__new__(FlowBrowser)
    browser._page = _Page()
    browser._project_url = "https://flow.google.com/project/test"
    browser.ui = {"timeouts": {"download": 10}}
    browser.media_assets = lambda: [{
        "sig": "IMG|https://media.google/still|still|image|320|180",
        "src": "https://media.google/still", "kind": "image", "dom_index": 0,
    }]
    browser._open_asset_tile_download_menu = lambda _locator: False
    browser._resolve = lambda action, timeout_ms=0: _Element()
    browser._try_resolve = lambda action, timeout_ms=0: None
    browser._ensure_project_guard_page = lambda *args, **kwargs: None
    browser.return_to_project = lambda timeout_ms=0: True
    browser.network_issue_detected = lambda _error=None: False

    output = tmp_path / "saved-still.png"
    result = browser.download_latest_asset(
        str(output), preferred_signature="IMG|https://media.google/still|still|image|320|180")

    assert result == str(output)
    assert requested_urls == [url]
    with Image.open(output) as recovered:
        assert recovered.size == (320, 180)
        recovered.verify()


def test_signature_kind_parser_ignores_untyped_or_malformed_values():
    assert media_signature_kind("IMG|https://media.google/still|still|image|320|180") == "image"
    assert media_signature_kind("VIDEO|https://media.google/clip|preview|video|320|180") == "video"
    assert media_signature_kind("opaque-signature") is None
    assert media_signature_kind("IMG|src|alt|unknown|320|180") is None


def test_queued_flow_thumbnail_is_pending_not_a_completed_image_or_video():
    queue_text = "Your video has been scheduled and is waiting in a high-demand queue."

    assert FlowBrowser._classify_media_kind(
        "IMG", "https://media.google/opaque-thumb", queue_text, "", False, True, False
    ) == "pending"
    assert FlowBrowser._classify_media_kind(
        "IMG", "https://media.google/opaque-thumb", "", queue_text, False, True, False
    ) == "pending"
    assert FlowBrowser._classify_media_kind(
        "IMG", "https://media.google/preview.mp4", queue_text, "", True, True, False
    ) == "pending"
    assert FlowBrowser._classify_media_kind(
        "VIDEO", "https://media.google/clip.mp4", queue_text, "", True, True, True
    ) == "video"
    assert media_signature_kind(
        "IMG|https://media.google/opaque-thumb|queue|pending|320|180"
    ) == "pending"


def test_initial_queue_observation_is_persisted_in_request_journal(tmp_path):
    output = tmp_path / "take.mp4"
    journal = Path(str(output) + ".flow-request.json")
    journal.write_text(json.dumps({
        "status": "pending", "kind": "video", "project_url": "https://flow.google.com/project/test",
        "baseline": ["older"], "signature": "",
    }), encoding="utf-8")
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)

    provider._record_queue_observation(str(output), elapsed_s=43)

    saved = json.loads(journal.read_text(encoding="utf-8"))
    assert saved["queue_detected"] is True
    assert saved["queue_wait_elapsed_s"] == 43
    assert saved["last_queue_observed_at"] > 0


def test_video_wait_stays_bounded_on_fresh_high_demand_queue_card(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(flow_module, "time", clock)
    browser = _wait_browser(clock, lambda: [
        {"sig": "old", "kind": "image"},
        {"sig": "fresh-queued-thumbnail", "kind": "pending"},
    ])
    browser._page.inner_text = lambda _selector: (
        "Your video has been scheduled and is waiting in a high-demand queue.")

    completed = browser.wait_for_agent_generation(
        before_assets={"old"}, timeout_s=8, required_kind="video",
        video_ready_grace_s=5,
    )

    assert completed is False
    assert browser.last_agent_queue_observed is True
    assert browser.last_agent_queue_elapsed_s >= 7
    assert browser.last_generated_asset_signature is None


def test_resume_with_fresh_queue_card_preserves_request_without_download_or_regeneration(tmp_path):
    project_url = "https://flow.google.com/project/saved-project"
    queued_sig = (
        "IMG|https://media.google/queued-thumb|scheduled queue card|pending|320|180")
    assets = [
        {"sig": "old", "kind": "image"},
        {"sig": queued_sig, "kind": "pending"},
    ]

    class _Bridge:
        _page = SimpleNamespace(wait_for_timeout=lambda _ms: None)

        def __init__(self):
            self.downloads = []

        def ensure_project(self, _project, project_url=None):
            assert project_url == project_url_expected

        def media_assets(self):
            return list(assets)

        def download_latest_asset(self, *args, **kwargs):
            self.downloads.append((args, kwargs))
            raise AssertionError("a queued thumbnail is not a downloadable video")

    project_url_expected = project_url
    bridge = _Bridge()
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    provider.bridge = bridge
    provider._ensure = lambda: bridge
    provider._asset_valid = lambda _path, _kind: False
    provider._generate_video_once = lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("queue recovery must never submit a duplicate generation"))

    shot = SimpleNamespace(shot_id="shot_017", model="omni_draft")
    compiled = {"prompt": "exact pending video prompt", "project": "Flow job",
                "project_url": project_url, "flow_image_signature_wait_ms": 0}
    request_hash = hashlib.sha256(json.dumps(
        ["video", shot.shot_id, compiled["prompt"], True], sort_keys=True
    ).encode()).hexdigest()
    output = tmp_path / "take.mp4"
    journal = Path(str(output) + ".flow-request.json")
    journal.write_text(json.dumps({
        "status": "pending", "kind": "video", "project_url": project_url,
        "baseline": ["old"], "signature": queued_sig,
        "request_hash": request_hash,
    }), encoding="utf-8")

    from engine.providers.flow_browser import FlowRequestPending
    try:
        provider._guarded_generation_once(
            shot, compiled, {}, str(output), True, False, "video")
    except FlowRequestPending as error:
        assert "still shows only its high-demand queue card" in str(error)
    else:
        raise AssertionError("a queued thumbnail cannot complete the saved video request")

    saved = json.loads(journal.read_text(encoding="utf-8"))
    assert saved["queue_detected"] is True
    assert saved["signature"] == ""
    assert saved["signature_kind_rejected"] == "queued-thumbnail"
    assert saved["rejected_signatures"] == [queued_sig]
    assert bridge.downloads == []

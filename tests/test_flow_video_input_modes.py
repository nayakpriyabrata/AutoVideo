"""Flow prompt-only clips must not accidentally inherit storyboard frame inputs."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import hashlib
import json

from engine.providers.flow_browser import FlowBrowserProvider


class _Bridge:
    def __init__(self):
        self.attached = []
        self.filled = []
        self.submitted = []
        self.last_agent_confirmation = {"clicked": True, "cost": 0}
        self.project_url = "https://flow.google.com/project/mode-test"

    def ensure_project(self, _project, project_url=None):
        if project_url:
            self.project_url = project_url

    def current_project_url(self):
        return self.project_url

    def prepare_text_video(self, **_kwargs):
        return "agent"

    def attach_agent_media(self, paths, reuse_existing=True):
        self.attached.append((list(paths), reuse_existing))
        return len(paths)

    def media_asset_signatures(self):
        return {"baseline"}

    def fill_text_video_prompt(self, prompt, strategy, **kwargs):
        self.filled.append((prompt, strategy, kwargs))

    def submit_prepared_text_video(self, strategy):
        self.submitted.append(strategy)

    def confirm_agent_generation(self, **_kwargs):
        return True

    def wait_for_agent_generation(self, **_kwargs):
        # The test ends before any download; the observed prompt and attachments
        # are the behavior under test.
        return False


def _provider(bridge):
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    provider.bridge = bridge
    provider._ensure = lambda: bridge
    provider._record_submission = lambda *_args, **_kwargs: None
    provider._record_asset = lambda *_args, **_kwargs: None
    provider._last_video_shot_id = ""
    provider._last_video_request_at = 0.0
    provider._last_video_baseline = set()
    provider._last_video_project_url = ""
    return provider


def test_prompt_only_mode_skips_all_storyboard_and_master_reference_uploads(tmp_path):
    opening = tmp_path / "opening.jpg"
    closing = tmp_path / "closing.jpg"
    character = tmp_path / "character.jpg"
    for path in (opening, closing, character):
        path.write_bytes(b"reference")
    bridge = _Bridge()
    provider = _provider(bridge)
    shot = SimpleNamespace(shot_id="shot_001", model="omni_draft", gen_duration=8,
                           visual_goal="a cinematic scene", negative="no captions")
    refs = {"start": str(opening), "end": str(closing), "character": str(character)}

    result = provider._generate_video_once(
        shot,
        {"prompt": "Create an eight-second action clip", "project": "mode test",
         "flow_video_mode": "prompt", "flow_video_recovery_wait_seconds": 0},
        refs, str(tmp_path / "clip.mp4"), False)

    assert result["path"] is None
    assert bridge.attached == []
    assert bridge.filled[0][0] == "Create an eight-second action clip"
    assert bridge.submitted == ["agent"]


def test_frames_mode_still_attaches_exact_opening_and_closing_references(tmp_path):
    opening = tmp_path / "opening.jpg"
    closing = tmp_path / "closing.jpg"
    opening.write_bytes(b"opening-reference")
    closing.write_bytes(b"closing-reference")
    bridge = _Bridge()
    provider = _provider(bridge)
    shot = SimpleNamespace(shot_id="shot_002", model="omni_draft", gen_duration=8,
                           visual_goal="a continuous scene", negative="no text")

    provider._generate_video_once(
        shot,
        {"prompt": "Frame-guided action", "project": "mode test",
         "flow_video_mode": "frames", "flow_video_recovery_wait_seconds": 0},
        {"start": str(opening), "end": str(closing)},
        str(tmp_path / "clip.mp4"), False)

    assert bridge.attached == [([str(opening), str(closing)], True)]


def test_prompt_mode_has_distinct_journal_identity_but_frames_keeps_legacy_hash(tmp_path):
    provider = FlowBrowserProvider.__new__(FlowBrowserProvider)
    seen = []

    def generate_once(*_args, **_kwargs):
        seen.append(provider._active_request_hash)
        return {"path": None, "provider": "flow"}

    provider._generate_video_once = generate_once
    shot = SimpleNamespace(shot_id="shot_003", model="omni_draft")
    prompt = "same approved scene prompt"
    output = str(tmp_path / "clip.mp4")

    for mode in ("frames", "prompt"):
        provider._guarded_generation_once(
            shot, {"prompt": prompt, "flow_video_mode": mode}, {}, output,
            True, False, "video")

    legacy_hash = hashlib.sha256(json.dumps(
        ["video", shot.shot_id, prompt, True], sort_keys=True).encode()).hexdigest()
    assert seen[0] == legacy_hash
    assert seen[1] != legacy_hash

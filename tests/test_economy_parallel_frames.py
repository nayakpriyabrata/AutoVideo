"""Storyboard Economy Flow-worker regressions: concurrency without breaking continuity."""
from __future__ import annotations

from pathlib import Path
from threading import Lock
from types import SimpleNamespace
import hashlib
import time

from PIL import Image


def _shot(shot_id, *, coverage="primary", provider="image", environment="shared studio"):
    return SimpleNamespace(
        shot_id=shot_id,
        status="planned",
        environment=environment,
        coverage=coverage,
        provider=provider,
        model="omni_draft" if provider == "flow" else "image",
        negative="no text, no watermark",
        subject="the same protagonist",
        subject_action=f"performs the action for {shot_id}",
        visual_goal=f"cinematic storyboard moment for {shot_id}",
        narration=f"Narration for {shot_id}",
        camera_framing="medium shot",
        lighting="soft studio light",
        media_strategy="flow_video" if provider == "flow" else "image_motion",
    )


class _Refs:
    def __init__(self):
        self.values = {"character": [], "location": [], "start": [], "end": []}

    def get(self, role):
        return list(self.values.get(role, []))

    def add(self, role, path, _name=""):
        self.values.setdefault(role, []).append(path)


class _ProjectLog:
    def __init__(self):
        self.events = []

    def log(self, job_id, event, data):
        self.events.append((job_id, event, data))

    def update_shot(self, _job_id, _shot):
        return None


class _Browser:
    def __init__(self, project_url):
        self.project_url = project_url

    def ensure_project(self, project, project_url=None):
        self.project_url = project_url or (
            "https://flow.google.com/project/" + project.lower().replace(" ", "-"))

    def current_project_url(self):
        return self.project_url


class _MainFlow:
    def close(self):
        return None


class _NoFreeImages:
    pass


def test_economy_flow_workers_parallelize_independent_frames_and_keep_linked_pairs(
        monkeypatch, tmp_path):
    import engine.providers.flow_browser as flow_module
    from engine.factory import Factory

    activity = {"active": 0, "maximum": 0, "lock": Lock(), "generated": []}

    class WorkerFlow:
        def __init__(self, profile_dir=None, **_kwargs):
            self.profile_dir = profile_dir
            self.browser = _Browser("")

        def _ensure(self):
            return self.browser

        def generate_image(self, shot, compiled, out_path, _vertical, dry_run=False):
            assert dry_run is False
            assert compiled["project_url"].startswith("https://flow.google.com/project/")
            with activity["lock"]:
                activity["active"] += 1
                activity["maximum"] = max(activity["maximum"], activity["active"])
            try:
                time.sleep(0.08)
                digest = hashlib.sha256(compiled["prompt"].encode()).digest()
                Image.new("RGB", (96, 96), tuple(digest[:3])).save(out_path, format="JPEG")
                activity["generated"].append((shot.shot_id, compiled["prompt"], list(compiled["reference_paths"])))
                return {"path": out_path, "provider": "flow", "project_url": compiled["project_url"]}
            finally:
                with activity["lock"]:
                    activity["active"] -= 1

        @staticmethod
        def is_browser_closed_error(_error):
            return False

        @staticmethod
        def is_transient_network_error(_error):
            return False

        def close(self):
            return None

    monkeypatch.setattr(flow_module, "FlowBrowserProvider", WorkerFlow)
    monkeypatch.setattr(flow_module, "PROFILE_DIR", str(tmp_path / "missing-profile"))
    monkeypatch.setattr(flow_module, "resolve_browser_cfg",
                        lambda _cfg: {"mode": "bundled", "cdp_url": ""})

    factory = Factory.__new__(Factory)
    factory.pm = _ProjectLog()
    factory.db = None
    factory._providers = lambda: {"flow": _MainFlow(), "image": _NoFreeImages()}

    root = tmp_path / "job"
    storyboard = root / "storyboard"
    flow_dir = root / "flow"
    storyboard.mkdir(parents=True)
    flow_dir.mkdir()
    shots = [
        _shot("shot_001", provider="flow"),
        _shot("shot_002", provider="image"),
        _shot("shot_003", coverage="insert", provider="flow"),
    ]
    manifest = SimpleNamespace(
        job_id="economy-parallel-test",
        profile="STORYBOARD_ECONOMY",
        target_seconds=45,
        aspect="16:9",
        topic="continuity test",
        shots=shots,
    )
    directories = {"root": str(root), "storyboard": str(storyboard), "flow": str(flow_dir)}
    settings = {
        "frame_source": "flow",
        "flow_image_workers": 2,
        "flow_reuse_project_media": False,
        "flow_project_url": "https://flow.google.com/project/main-project",
        "flow_frame_retries": 1,
        "flow_capacity_wait_seconds": 1,
        "flow_capacity_retries": 0,
    }
    refs = _Refs()

    factory._generate_economy_frames(
        manifest, directories, refs, False, settings, {}, lambda *_args: None)

    assert activity["maximum"] >= 2, "independent Flow frames should overlap across worker projects"
    open_1 = storyboard / "shot_001_open.jpg"
    close_1 = storyboard / "shot_001_close.jpg"
    open_2 = storyboard / "shot_002_open.jpg"
    close_2 = storyboard / "shot_002_close.jpg"
    open_3 = storyboard / "shot_003_open.jpg"
    close_3 = storyboard / "shot_003_close.jpg"
    assert all(path.is_file() for path in (open_1, close_1, open_2, close_2, open_3, close_3))
    assert hashlib.sha256(open_2.read_bytes()).digest() == hashlib.sha256(close_1.read_bytes()).digest(), (
        "a continuity-linked opening must be the exact previous closing frame")
    for open_path, close_path in ((open_1, close_1), (open_3, close_3)):
        assert hashlib.sha256(open_path.read_bytes()).digest() != hashlib.sha256(close_path.read_bytes()), (
            "each selected Flow-video scene must retain a distinct first/last-frame pair")
    assert shots[1].opening_frame == str(open_2)
    assert shots[1].closing_frame == str(close_2)
    assert any(event == "economy_parallel_frame" for _, event, _ in factory.pm.events)
    assert any(path.name.startswith("economy-worker-")
               for path in (root / ".flow-workers").iterdir())

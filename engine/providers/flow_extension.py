"""Client for the AutoVideoAI Chrome companion extension.

This does not log into Google and does not use Google/Veo APIs. The extension
runs in the user's existing Chrome/Flow tab and receives local commands over
127.0.0.1 only.
"""
from __future__ import annotations
import time
import requests

class FlowExtensionClient:
    def __init__(self, base_url="http://127.0.0.1:8765"):
        self.base = base_url.rstrip("/")

    def health(self):
        return requests.get(self.base + "/health", timeout=3).json()

    def enqueue_scene(self, prompt: str, aspect="9:16", model_hint="", auto_generate=True,
                      project_name="", metadata=None):
        r = requests.post(self.base + "/enqueue", json={"command": "run_scene", "payload": {
            "prompt": prompt, "aspect": aspect, "model_hint": model_hint,
            "auto_generate": bool(auto_generate), "project_name": project_name,
            "metadata": metadata or {},
        }}, timeout=5)
        r.raise_for_status()
        return r.json()["id"]

    def wait(self, task_id: str, timeout=900, poll=2):
        end = time.time() + timeout
        while time.time() < end:
            r = requests.get(f"{self.base}/result/{task_id}", timeout=5).json().get("result")
            if r:
                return r
            time.sleep(poll)
        raise TimeoutError(f"Flow extension task {task_id} timed out")

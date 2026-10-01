"""ComfyUI provider - local Wan/LTX/etc via workflow presets (free, GPU)."""
from __future__ import annotations
import os
import json
import time
import requests
from .base import VideoProvider, ProviderStatus

PRESET_FILES = {
    "wan_t2v": "assets/comfy/wan_t2v_api.json",
    "wan_i2v": "assets/comfy/wan_i2v_api.json",
    "wan_control": "assets/comfy/wan_control_api.json",
    "ltx_t2v": "assets/comfy/ltx_t2v_api.json",
    "ltx_i2v": "assets/comfy/ltx_i2v_api.json",
    "ltx_multikeyframe": "assets/comfy/ltx_multikeyframe_api.json",
}


class ComfyProvider(VideoProvider):
    name = "comfy"

    def __init__(self):
        self.base = os.getenv("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")

    def status(self) -> ProviderStatus:
        try:
            r = requests.get(f"{self.base}/system_stats", timeout=5)
            if r.status_code == 200:
                return ProviderStatus(True, f"ComfyUI at {self.base}")
        except Exception as e:
            return ProviderStatus(False, f"ComfyUI not reachable at {self.base}: {e}")
        return ProviderStatus(False, f"ComfyUI bad status at {self.base}")

    def check_hardware(self, need_gb: int = 8) -> dict:
        try:
            import torch
            if not torch.cuda.is_available():
                return {"ok": False, "reason": "no CUDA GPU (CPU-only local video is impractical)"}
            gb = torch.cuda.get_device_properties(0).total_memory / 1e9
            return {"ok": gb >= need_gb, "vram_gb": round(gb, 1)}
        except ImportError:
            return {"ok": True, "reason": "torch not installed locally; ComfyUI may run elsewhere"}

    def _workflow(self, model: str) -> str:
        path = PRESET_FILES.get(model, PRESET_FILES["wan_t2v"])
        path = os.getenv("COMFY_WORKFLOW", path) if model == "wan_t2v" else path
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Missing ComfyUI preset {path}. In ComfyUI (Dev Mode): Save (API Format) -> {path}. "
                f"Placeholders: {{{{PROMPT}}}} {{{{NEGATIVE_PROMPT}}}} {{{{WIDTH}}}} {{{{HEIGHT}}}} "
                f"{{{{FRAMES}}}} {{{{SEED}}}} {{{{START_IMAGE}}}} {{{{END_IMAGE}}}}")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def generate(self, shot, compiled: dict, refs: dict, out_path: str,
                 vertical: bool, dry_run: bool = False) -> dict:
        model = shot.model if shot.model in PRESET_FILES else "wan_t2v"
        if dry_run:
            return {"path": None, "provider": "comfy", "model": model, "seed": None,
                    "credits": 0, "dry_run": True, "log": f"DRY RUN: would queue {model}"}
        st = self.status()
        if not st.available:
            return {"path": None, "provider": "comfy", "model": model, "seed": None,
                    "credits": 0, "dry_run": False, "error": st.reason}
        W, H = (720, 1280) if vertical else (1280, 720)
        wf = self._workflow(model)
        seed = 1000 + int(shot.shot_id.split("_")[-1])
        subs = {"{{PROMPT}}": compiled.get("prompt", ""), "{{NEGATIVE_PROMPT}}": compiled.get("negative", ""),
                "{{WIDTH}}": str(W), "{{HEIGHT}}": str(H),
                "{{FRAMES}}": str(int((shot.gen_duration or 6) * 16)),
                "{{SEED}}": str(seed),
                "{{START_IMAGE}}": refs.get("start", "") or refs.get("storyboard", "") or "",
                "{{END_IMAGE}}": refs.get("end", "") or ""}
        for k, v in subs.items():
            wf = wf.replace(k, v.replace('"', "'") if k in ("{{PROMPT}}", "{{NEGATIVE_PROMPT}}") else v)
        # upload start image if referenced
        if subs["{{START_IMAGE}}"] and os.path.exists(subs["{{START_IMAGE}}"]):
            with open(subs["{{START_IMAGE}}"], "rb") as f:
                requests.post(f"{self.base}/upload/image", files={"image": f}, timeout=60)
        r = requests.post(f"{self.base}/prompt", json={"prompt": json.loads(wf)}, timeout=30)
        r.raise_for_status()
        pid = r.json()["prompt_id"]
        deadline = time.time() + 40 * 60
        found = None
        while time.time() < deadline:
            time.sleep(10)
            try:
                hist = requests.get(f"{self.base}/history/{pid}", timeout=30).json().get(pid, {})
            except Exception:
                continue
            for node in (hist.get("outputs") or {}).values():
                for g in (node.get("gifs") or []) + (node.get("videos") or []):
                    found = (g.get("filename"), g.get("subfolder", ""), g.get("type", "output"))
            if found:
                break
        if not found:
            return {"path": None, "provider": "comfy", "model": model, "seed": seed,
                    "credits": 0, "dry_run": False, "error": "ComfyUI timed out"}
        fn, sub, typ = found
        dl = requests.get(f"{self.base}/view", params={"filename": fn, "subfolder": sub, "type": typ}, timeout=300)
        with open(out_path, "wb") as f:
            f.write(dl.content)
        return {"path": out_path, "provider": "comfy", "model": model, "seed": seed,
                "credits": 0, "dry_run": False, "log": f"comfy:{pid}"}

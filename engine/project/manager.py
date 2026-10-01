"""ProjectManager - isolated job folders, atomic manifest IO, resume support."""
from __future__ import annotations
import os
import json
import uuid
import datetime
from .manifest import ProductionManifest, Shot

SUBDIRS = ["narration", "storyboard", "references", "flow", "flow/shots",
           "downloads", "local", "stock", "captions", "audio", "qc", "render", "logs"]


def get_project_dirs(job_dir: str) -> dict[str, str]:
    return {"root": job_dir, **{d.replace("/", "_"): os.path.join(job_dir, d) for d in SUBDIRS}}


class ProjectManager:
    def __init__(self, outputs_root: str = "outputs"):
        self.root = os.path.abspath(outputs_root)
        os.makedirs(self.root, exist_ok=True)

    def new_job_id(self, topic: str) -> str:
        slug = "".join(c if c.isalnum() else "-" for c in topic.lower())[:24].strip("-") or "video"
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{slug}-{uuid.uuid4().hex[:4]}"

    def create(self, manifest: ProductionManifest) -> dict[str, str]:
        job_dir = os.path.join(self.root, manifest.job_id)
        os.makedirs(job_dir, exist_ok=True)
        for d in SUBDIRS:
            os.makedirs(os.path.join(job_dir, d), exist_ok=True)
        self.save_manifest(manifest)
        return get_project_dirs(job_dir)

    def job_dir(self, job_id: str) -> str:
        return os.path.join(self.root, job_id)

    def dirs(self, job_id: str) -> dict[str, str]:
        return get_project_dirs(self.job_dir(job_id))

    # ---- manifest IO (atomic) ----
    def manifest_path(self, job_id: str) -> str:
        return os.path.join(self.job_dir(job_id), "production_manifest.json")

    def save_manifest(self, m: ProductionManifest):
        p = self.manifest_path(m.job_id)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(m.model_dump_json(indent=2))
        os.replace(tmp, p)

    def load_manifest(self, job_id: str) -> ProductionManifest:
        with open(self.manifest_path(job_id), encoding="utf-8") as f:
            return ProductionManifest.model_validate_json(f.read())

    def update_shot(self, job_id: str, shot: Shot):
        m = self.load_manifest(job_id)
        for i, s in enumerate(m.shots):
            if s.shot_id == shot.shot_id:
                m.shots[i] = shot
                break
        else:
            m.shots.append(shot)
        self.save_manifest(m)
        return m

    def log(self, job_id: str, event: str, data: dict | None = None):
        p = os.path.join(self.job_dir(job_id), "generation_log.json")
        try:
            with open(p, encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []
        log.append({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                    "event": event, **(data or {})})
        with open(p, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2)

    def list_jobs(self) -> list[str]:
        if not os.path.isdir(self.root):
            return []
        return sorted([d for d in os.listdir(self.root)
                       if os.path.isfile(os.path.join(self.root, d, "production_manifest.json"))],
                      reverse=True)

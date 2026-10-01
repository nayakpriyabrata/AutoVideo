"""Reference manager - character/location/product/style/first/last frames + FFmpeg extraction."""
from __future__ import annotations
import os
import json
import shutil
import subprocess

KINDS = ("character", "location", "product", "style", "storyboard", "start", "end")


def _ffmpeg() -> str:
    for c in ("ffmpeg",):
        p = shutil.which(c)
        if p:
            return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


class ReferenceManager:
    def __init__(self, refs_dir: str):
        self.dir = refs_dir
        os.makedirs(refs_dir, exist_ok=True)
        self.reg_path = os.path.join(refs_dir, "refs.json")
        try:
            with open(self.reg_path, encoding="utf-8") as f:
                self.reg = json.load(f)
        except Exception:
            self.reg = {}

    def _save(self):
        with open(self.reg_path, "w", encoding="utf-8") as f:
            json.dump(self.reg, f, indent=2)

    def add(self, kind: str, src_path: str, name: str | None = None) -> str:
        assert kind in KINDS, f"kind must be one of {KINDS}"
        dst = os.path.join(self.dir, (name or f"{kind}_{len(self.reg)}.jpg"))
        shutil.copy(src_path, dst)
        self.reg.setdefault(kind, []).append(dst)
        self._save()
        return dst

    def get(self, kind: str) -> list[str]:
        return list(self.reg.get(kind, []))

    def for_shot(self, shot_id: str) -> dict:
        """Resolve reference paths usable for a shot (storyboard/start/character/location)."""
        refs = {}
        for k in ("storyboard", "start", "end", "character", "location", "product", "style"):
            matches = [p for p in self.get(k) if shot_id in os.path.basename(p) or k in ("character", "location", "product", "style")]
            if matches:
                refs[k] = matches[0]
        return refs

    # ---- frame extraction ----
    def extract_frame(self, video: str, at: float | str, out: str) -> str:
        """at: seconds | 'first' | 'middle' | 'last'."""
        if isinstance(at, str):
            dur = self.probe_duration(video) or 8.0
            at = {"first": 0.3, "middle": dur / 2, "last": max(0.3, dur - 0.4)}[at]
        subprocess.run([_ffmpeg(), "-y", "-ss", str(at), "-i", video,
                        "-frames:v", "1", "-q:v", "3", out],
                       capture_output=True, check=True)
        return out

    def best_end_frame(self, video: str, out: str) -> str:
        """Sharpest non-black frame from the last 1.2s (for next-shot continuity)."""
        import cv2
        dur = self.probe_duration(video) or 8.0
        cap = cv2.VideoCapture(video)
        fps = cap.get(cv2.CAP_PROP_FPS) or 24
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int((dur - 1.2) * fps)))
        best, best_score = None, -1
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            score = cv2.Laplacian(gray, cv2.CV_64F).var() + gray.mean() * 2
            if score > best_score:
                best, best_score = fr, score
        cap.release()
        if best is None:
            return self.extract_frame(video, "last", out)
        cv2.imwrite(out, best)
        return out

    @staticmethod
    def probe_duration(video: str) -> float | None:
        try:
            import cv2
            cap = cv2.VideoCapture(video)
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            cap.release()
            return (n / fps) if fps else None
        except Exception:
            return None

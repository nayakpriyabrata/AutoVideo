"""Image provider - storyboard frames + kenburns_plus motion clips (free)."""
from __future__ import annotations
import os
from .base import VideoProvider, ProviderStatus


class ImageProvider(VideoProvider):
    name = "image"

    def status(self) -> ProviderStatus:
        return ProviderStatus(True, "pollinations/local fallback")

    def generate_image(self, shot, compiled: dict, out_path: str,
                       vertical: bool, dry_run: bool = False) -> dict:
        if dry_run:
            return {"path": None, "provider": "image", "model": "pollinations",
                    "dry_run": True, "log": "DRY RUN: free image skipped"}
        self.storyboard_frame(compiled.get("prompt", shot.visual_goal)[:180], out_path, vertical)
        return {"path": out_path, "provider": "image", "model": "pollinations",
                "dry_run": False, "log": "free image ok"}

    def storyboard_frame(self, prompt: str, out_path: str, vertical: bool) -> str:
        from ..visuals import get_visuals
        r = get_visuals([prompt], prompt[:60], os.path.dirname(out_path) or ".", vertical)
        import shutil
        shutil.copy(r["images"][0], out_path)
        return out_path

    @staticmethod
    def clip_duration(shot) -> float:
        """Cover the full voice window so the timeline never freeze-fills."""
        window = max(float(shot.voice_end - shot.voice_start),
                     float(shot.duration_target or 0))
        return max(float(shot.gen_duration or 6), window, 2.0)

    @staticmethod
    def motion_for(shot_or_id) -> tuple[bool, tuple[float, float]]:
        """Deterministic but coverage-aware cinematic motion.

        Accepting a plain shot id preserves the public/test API. When a Shot is
        supplied, coverage influences the motion language so consecutive stills
        do not all feel like the same Ken Burns preset.
        """
        import hashlib
        shot_id = getattr(shot_or_id, "shot_id", None) or str(shot_or_id)
        coverage = str(getattr(shot_or_id, "coverage", "") or "").lower()
        h = int(hashlib.md5(shot_id.encode()).hexdigest()[:8], 16)
        defaults = {
            "hook": (True, (0.10, -0.05)),
            "primary": (True, (0.32, 0.08)),
            "closeup": (False, (-0.48, 0.03)),
            "insert": (True, (0.06, 0.03)),
            "broll": (False, (0.72, -0.16)),
            "hero_outro": (False, (-0.24, -0.12)),
        }
        if coverage in defaults:
            zin, (px, py) = defaults[coverage]
            # Flip horizontal direction deterministically to avoid repetition.
            if h % 2:
                px = -px
            return zin, (round(px, 2), round(py, 2))
        zoom_in = bool(h % 2)
        px = (((h >> 1) % 100) / 100 - 0.5) * 1.6
        py = (((h >> 3) % 100) / 100 - 0.5) * 1.0
        return zoom_in, (round(px, 2), round(py, 2))

    def generate(self, shot, compiled: dict, refs: dict, out_path: str,
                 vertical: bool, dry_run: bool = False) -> dict:
        """kenburns_plus: reference frame -> cinematic motion clip (local render)."""
        if dry_run:
            return {"path": None, "provider": "image", "model": "kenburns_plus",
                    "seed": None, "credits": 0, "dry_run": True,
                    "log": f"DRY RUN: would render motion clip for {shot.shot_id}"}
        from PIL import Image
        from moviepy.editor import ImageClip, CompositeVideoClip
        from ..video_builder import _cover_resize, _ken_burns
        W, H = (1080, 1920) if vertical else (1920, 1080)
        start = refs.get("start") or getattr(shot, "opening_frame", None) or refs.get("storyboard")
        end = refs.get("end") or getattr(shot, "closing_frame", None)

        def valid_image(path):
            try:
                if not path or not os.path.isfile(path) or os.path.getsize(path) < 128:
                    return False
                with Image.open(path) as im:
                    im.verify()
                with Image.open(path) as im:
                    return im.size[0] >= 64 and im.size[1] >= 64
            except Exception:
                return False

        # Rendering must never crash merely because an optional closing frame was
        # truncated by a full disk or interrupted Flow download.  A valid opening
        # frame can still produce a perfectly usable single-frame Ken Burns clip.
        if not valid_image(start):
            if valid_image(end):
                print(f"[ImageMotion] {shot.shot_id}: opening frame is invalid; using valid closing frame as the motion source.")
                start, end = end, None
            else:
                raise RuntimeError(
                    f"{shot.shot_id}: no decodable reference image is available for image-motion render")
        if end and not valid_image(end):
            print(f"[ImageMotion] {shot.shot_id}: closing frame is corrupt/incomplete; "
                  "ignoring it and rendering from the opening frame only.")
            end = None

        dur = self.clip_duration(shot)

        def prep(src, suffix):
            try:
                with Image.open(src) as opened:
                    im = opened.convert("RGB")
                    im.load()
            except Exception as e:
                raise RuntimeError(f"Cannot decode reference image {src}: {e}") from e
            im = _cover_resize(im, W, H)
            dst = out_path + suffix
            im.save(dst, quality=90)
            return dst

        start_r = prep(start, ".open.frame.jpg")
        zoom_in, pan = self.motion_for(shot)
        if end and valid_image(end) and os.path.abspath(end) != os.path.abspath(start):
            end_r = prep(end, ".close.frame.jpg")
            overlap = min(0.65, max(0.25, dur * 0.12))
            half = (dur + overlap) / 2.0
            a = ImageClip(start_r, duration=half)
            zr = 0.09 if getattr(shot, "coverage", "") == "insert" else (0.18 if getattr(shot, "coverage", "") == "hook" else 0.14)
            a = _ken_burns(a, W, H, half, zoom_in=zoom_in, pan=pan, zoom_range=zr)
            b = ImageClip(end_r, duration=half)
            b = _ken_burns(b, W, H, half, zoom_in=not zoom_in,
                           pan=(-pan[0], -pan[1]), zoom_range=zr)
            b = b.set_start(half - overlap).crossfadein(overlap)
            clip = CompositeVideoClip([a, b], size=(W, H)).set_duration(dur)
            model = "image_pair_motion"
            log = "local open/close frame motion render"
        else:
            clip = ImageClip(start_r, duration=dur)
            zr = 0.09 if getattr(shot, "coverage", "") == "insert" else (0.18 if getattr(shot, "coverage", "") == "hook" else 0.14)
            clip = _ken_burns(clip, W, H, dur, zoom_in=zoom_in, pan=pan, zoom_range=zr)
            model = "kenburns_plus"
            log = "local single-frame motion render"
        clip.write_videofile(out_path, fps=24, codec="libx264", audio=False,
                             preset="veryfast", logger=None)
        try:
            clip.close()
        except Exception:
            pass
        return {"path": out_path, "provider": "image", "model": model,
                "seed": None, "credits": 0, "dry_run": False, "log": log}

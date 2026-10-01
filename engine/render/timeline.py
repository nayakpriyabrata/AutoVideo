"""
Timeline builder - narration timing drives the edit.

v5.1 guarantees a renderable visual slot for every narration window. Missing
or rejected takes no longer shorten the film; the nearest usable take is held
as a visual bridge and the final timeline is compensated for transition overlap
so rendered duration tracks narration duration closely.
"""
from __future__ import annotations
import os
import json
import math
import shutil
import subprocess

FREEZE_WARN = 1.0


def _take_duration(path: str) -> float | None:
    """Return a sane duration only for an actual time-based video file."""
    if not path or not os.path.isfile(path):
        return None
    fp = shutil.which("ffprobe")
    if fp:
        try:
            cp = subprocess.run(
                [fp, "-v", "error", "-show_entries",
                 "format=format_name,duration:stream=codec_type,duration",
                 "-of", "json", path],
                capture_output=True, text=True, timeout=15)
            if cp.returncode != 0:
                return None
            data = json.loads(cp.stdout or "{}")
            fmt = data.get("format") or {}
            fmt_name = str(fmt.get("format_name") or "").lower()
            if any(x in fmt_name for x in ("image2", "jpeg_pipe", "png_pipe", "bmp_pipe", "gif")):
                return None
            if not any(str(x.get("codec_type")) == "video" for x in (data.get("streams") or [])):
                return None
            vals = [fmt.get("duration")] + [x.get("duration") for x in (data.get("streams") or [])]
            for raw in vals:
                try:
                    d = float(raw)
                    if math.isfinite(d) and 0.05 <= d <= 6 * 3600:
                        return d
                except Exception:
                    pass
            return None
        except Exception:
            return None
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        n = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        d = (n / fps) if fps > 0 else 0
        return d if math.isfinite(d) and 0.05 <= d <= 6 * 3600 else None
    except Exception:
        return None


def _take_for_shot(s, takes_dir: str) -> str:
    shot_dir = os.path.join(takes_dir, s.shot_id)
    preferred = os.path.join(shot_dir, "accepted.mp4")
    if os.path.isfile(preferred) and _take_duration(preferred) is not None:
        return preferred
    accepted = getattr(s, "accepted_take", None)
    if accepted and os.path.isfile(accepted) and _take_duration(accepted) is not None:
        return accepted
    if os.path.isdir(shot_dir):
        try:
            cands = sorted(os.path.join(shot_dir, f) for f in os.listdir(shot_dir)
                           if f.lower().endswith(".mp4") and os.path.isfile(os.path.join(shot_dir, f)))
            for cand in cands:
                if _take_duration(cand) is not None:
                    return cand
        except Exception:
            pass
    return ""


def _transition_overlap(seg: dict) -> float:
    # Must mirror ffmpeg_renderer.py. Hard cuts use a near-zero xfade because
    # xfade itself does not accept a literal zero duration on all FFmpeg builds.
    return 0.35 if seg.get("trans_out") == "dissolve" else 0.01


def build_timeline(manifest, takes_dir: str, narration_dur: float,
                   hard_cuts: bool = False) -> dict:
    """Return ``{segments,total,warnings}`` with narration-complete coverage.

    Segment fields use ``dur`` for source playback duration and ``freeze`` only
    for last-frame extension, so FFmpeg never double-counts freeze time.
    """
    shots = list(manifest.shots or [])
    if not shots:
        raise RuntimeError("No shots to render. Complete planning/generation first.")

    resolved = [_take_for_shot(s, takes_dir) for s in shots]
    if not any(resolved):
        raise RuntimeError("No generated take files are available to render.")

    # Pre-compute nearest usable visual for a missing/rejected slot.
    def nearest_take(i: int) -> str:
        if resolved[i]:
            return resolved[i]
        for d in range(1, len(shots) + 1):
            for j in (i - d, i + d):
                if 0 <= j < len(resolved) and resolved[j]:
                    return resolved[j]
        return ""

    segments, warnings, t = [], [], 0.0
    for i, s in enumerate(shots):
        desired = max(0.10, round(float(s.voice_end) - float(s.voice_start), 3))
        take = nearest_take(i)
        if not take:
            warnings.append(f"{s.shot_id}: no usable visual source - skipped")
            continue
        borrowed = not bool(resolved[i])
        if borrowed:
            warnings.append(f"{s.shot_id}: no accepted take; nearest generated take reused as a visual bridge")

        probed = _take_duration(take)
        if probed is None or not math.isfinite(float(probed)) or float(probed) <= 0:
            warnings.append(f"{s.shot_id}: rejected invalid/non-video take {os.path.basename(take)}")
            continue
        src_dur = float(probed)
        play_dur = min(src_dur, desired)
        freeze = max(0.0, desired - play_dur)
        if freeze > FREEZE_WARN:
            warnings.append(f"{s.shot_id}: source {src_dur:.1f}s < narration window {desired:.1f}s; held last frame {freeze:.1f}s")
        src_in = round(max(0.0, (src_dur - play_dur) / 2.0), 3) if src_dur > play_dur else 0.0
        segments.append({
            "shot_id": s.shot_id,
            "src": take,
            "in": src_in,
            "dur": round(play_dur, 3),
            "freeze": round(freeze, 3),
            "trans_in": "fadein" if i == 0 else s.transition_in,
            "trans_out": "fadeout" if i == len(shots) - 1 else s.transition_out,
            "timeline_start": round(t, 3),
            "borrowed_visual": borrowed,
        })
        t += desired

    if not segments:
        raise RuntimeError("No timeline segments could be resolved.")

    # xfade overlaps subtract time. Compensate on the last segment so the final
    # rendered picture lasts exactly as long as narration instead of ending early.
    if hard_cuts:
        for segment in segments:
            segment["hard_cut"] = True
    overlaps = 0.0 if hard_cuts else sum(_transition_overlap(s) for s in segments[:-1])
    effective = sum(float(s["dur"]) + float(s.get("freeze", 0) or 0) for s in segments) - overlaps
    delta = float(narration_dur) - effective
    if delta > 0.005:
        segments[-1]["freeze"] = round(float(segments[-1].get("freeze", 0) or 0) + delta, 3)
        effective += delta
    elif delta < -0.005:
        # Trim excess from the last source first, then its freeze if necessary.
        excess = -delta
        fr = float(segments[-1].get("freeze", 0) or 0)
        cut_fr = min(fr, excess)
        segments[-1]["freeze"] = round(fr - cut_fr, 3)
        excess -= cut_fr
        if excess > 0:
            segments[-1]["dur"] = round(max(0.10, float(segments[-1]["dur"]) - excess), 3)
        effective = float(narration_dur)

    total = round(effective, 3)
    if abs(total - narration_dur) > 0.25:
        warnings.append(f"timeline {total:.1f}s vs narration {narration_dur:.1f}s after compensation")
    return {"segments": segments, "total": total, "warnings": warnings,
            "transition_overlap": round(overlaps, 3)}

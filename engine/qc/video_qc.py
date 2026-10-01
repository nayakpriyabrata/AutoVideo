"""
Local visual QC (free: OpenCV + FFmpeg). Every candidate is scored; only
accepted takes enter the timeline. Failures map to targeted retry modifiers.
"""
from __future__ import annotations
import os
import cv2
import numpy as np

RETRY_MODIFIERS = {
    "identity_drift": "preserve the exact face, hairstyle and wardrobe from the reference image; same person, no recast",
    "bad_hands": "clean natural hands, correct fingers, hands relaxed and anatomically correct",
    "camera_too_fast": "locked smooth stabilized camera motion; constant slow velocity; no shake, no whip moves",
    "low_motion": "add gentle lifelike motion: breathing, blinking, subtle movement; avoid frozen static frame",
    "wrong_composition": "center subject in frame middle 60%, clear headroom, balanced cinematic composition",
    "text_artifacts": "absolutely no text, letters, logos, watermarks or UI elements anywhere in frame",
    "poor_lighting": "soft balanced cinematic lighting, visible subject, no harsh overexposure or crushed blacks",
    "physics_error": "strictly realistic physics; stable objects; no morphing, melting or teleporting",
    "blur": "tack-sharp focus on subject, crisp detail, high clarity",
    "generic": "higher quality, clean stable professional shot",
}


def _sample_frames(path: str, n: int = 12):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return [], {}
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    idxs = [int(total * (i + 1) / (n + 1)) for i in range(n)] if total > n else list(range(total))
    frames = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = cap.read()
        if ok:
            frames.append(fr)
    cap.release()
    return frames, {"frames": total, "fps": fps, "w": w, "h": h,
                    "duration": (total / fps) if fps else 0}


def _phash(gray) -> int:
    small = cv2.resize(gray, (16, 16))
    m = small.mean()
    bits = (small > m).flatten()
    h = 0
    for b in bits:
        h = (h << 1) | int(b)
    return h


def _ham(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def score_image(path: str) -> dict:
    """Pick the best of K scene images: sharpness + exposure + size sanity."""
    out = {"sharpness": 0.0, "brightness": 0.0, "overall": 0.0, "ok": False}
    try:
        im = cv2.imread(path)
        if im is None or im.size < 10000:
            return out
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        bright = float(gray.mean())
        h, w = gray.shape
        sharp_n = min(100.0, sharp / 4)
        bright_n = 100.0 if 20 < bright < 235 else max(0.0, 100 - abs(bright - 120))
        res_n = 100.0 if min(h, w) >= 512 else min(h, w) / 512 * 100
        overall = round(sharp_n * 0.45 + bright_n * 0.35 + res_n * 0.2, 1)
        return {"sharpness": round(sharp_n, 1), "brightness": round(bright, 1),
                "overall": overall, "ok": overall >= 40}
    except Exception:
        return out


def classify_failure(scores: dict) -> str:
    s = scores
    if s.get("frozen_ratio", 0) > 0.5:
        return "low_motion"
    if s.get("blur", 100) < 35:
        return "blur"
    if s.get("brightness", 100) < 35:
        return "poor_lighting"
    if s.get("motion", 100) > 97:
        return "camera_too_fast"
    if s.get("continuity", 100) < 50:
        return "identity_drift"
    if s.get("text_risk", 0) > 60:
        return "text_artifacts"
    return "generic"


def analyze_take(path: str, ref_images: list[str] | None = None,
                 expect_seconds: float | None = None,
                 expect_vertical: bool | None = None) -> dict:
    """Returns {technical, continuity, motion, overall, decision, details, failure}."""
    out = {"path": path, "technical": 0, "continuity": 0, "motion": 0,
           "overall": 0, "decision": "REJECT", "details": {}, "failure": "generic"}
    if not os.path.exists(path) or os.path.getsize(path) < 20000:
        out["details"] = {"error": "missing/tiny file"}
        return out
    frames, meta = _sample_frames(path)
    if len(frames) < 3:
        out["details"] = {"error": "unreadable/corrupt video"}
        return out
    d = dict(meta)
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]

    # black frames / brightness
    means = [float(g.mean()) for g in grays]
    d["black_ratio"] = round(sum(1 for m in means if m < 8) / len(means), 2)
    d["mean_brightness"] = round(float(np.mean(means)), 1)
    bright_score = 100 if 25 < d["mean_brightness"] < 225 else max(0, 100 - abs(d["mean_brightness"] - 120))

    # blur (Laplacian variance, normalized)
    blurs = [cv2.Laplacian(g, cv2.CV_64F).var() for g in grays]
    d["blur_mean"] = round(float(np.mean(blurs)), 1)
    blur_score = min(100, d["blur_mean"] / 3)

    # frozen frames (identical consecutive hashes)
    hashes = [_phash(g) for g in grays]
    frozen = sum(1 for a, b in zip(hashes, hashes[1:]) if _ham(a, b) < 4)
    d["frozen_ratio"] = round(frozen / max(1, len(hashes) - 1), 2)

    # motion level (mean abs diff)
    diffs = [float(np.mean(cv2.absdiff(grays[i], grays[i + 1]))) for i in range(len(grays) - 1)]
    d["motion_mean"] = round(float(np.mean(diffs)), 2)
    motion_score = min(100, max(0, (d["motion_mean"] - 0.4) * 8 + 40))

    # unexpected cuts (huge hash jumps mid-clip)
    jumps = sum(1 for a, b in zip(hashes, hashes[1:]) if _ham(a, b) > 120)
    d["cut_count"] = jumps

    # duration / aspect checks
    tech = 100.0
    tech -= d["black_ratio"] * 60
    tech -= d["frozen_ratio"] * 50
    tech -= max(0, (35 - blur_score)) * 0.8
    tech -= max(0, (40 - bright_score)) * 0.5
    if jumps > 2:
        tech -= 20
    if expect_seconds and abs(meta["duration"] - expect_seconds) > max(2.5, expect_seconds * 0.4):
        tech -= 15
        d["duration_note"] = f"got {meta['duration']:.1f}s, wanted ~{expect_seconds}s"
    if expect_vertical is not None and meta["w"] and meta["h"]:
        vert = meta["h"] > meta["w"]
        if vert != expect_vertical:
            tech -= 25
            d["aspect_note"] = f"got {meta['w']}x{meta['h']}"
    technical = round(max(0, min(100, tech)), 1)

    # continuity vs reference images (perceptual hash similarity)
    cont = 100.0
    if ref_images:
        ref_hashes = []
        for rp in ref_images:
            if rp and os.path.exists(rp):
                im = cv2.imread(rp, cv2.IMREAD_GRAYSCALE)
                if im is not None:
                    ref_hashes.append(_phash(im))
        if ref_hashes:
            dists = [min(_ham(h, r) for r in ref_hashes) for h in hashes]
            avg = float(np.mean(dists))
            d["ref_hash_dist"] = round(avg, 1)
            cont = max(0, 100 - avg * 0.55)
    continuity = round(cont, 1)

    # text-risk heuristic: many ultra-sharp small edges (cheap, conservative)
    edges = [float(np.mean(cv2.Canny(g, 100, 200))) for g in grays[:4]]
    d["edge_density"] = round(float(np.mean(edges)), 2)
    text_risk = min(100, max(0, (d["edge_density"] - 12) * 6))
    d["text_risk"] = round(text_risk, 1)

    overall = round(technical * 0.55 + continuity * 0.25 + motion_score * 0.2, 1)
    decision = "ACCEPT" if overall >= 70 and technical >= 55 else ("REVIEW" if overall >= 55 else "REJECT")
    scores = {"frozen_ratio": d["frozen_ratio"], "blur": blur_score, "brightness": bright_score,
              "motion": motion_score, "continuity": continuity, "text_risk": text_risk}
    out.update({"technical": technical, "continuity": continuity, "motion": round(motion_score, 1),
                "overall": overall, "decision": decision, "details": d,
                "failure": classify_failure(scores)})
    return out

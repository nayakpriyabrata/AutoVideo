"""Lightweight storyboard visual-diversity audit (v5.1).

Uses perceptual dHash so re-encoded copies are still recognized as near-duplicates.
This is a report-only QC layer; it never discards a completed render.
"""
from __future__ import annotations
import glob
import os


def _dhash(path: str) -> int | None:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("L").resize((9, 8))
            px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
        value = 0
        bit = 0
        for y in range(8):
            row = px[y * 9:(y + 1) * 9]
            for x in range(8):
                if row[x] > row[x + 1]:
                    value |= (1 << bit)
                bit += 1
        return value
    except Exception:
        return None


def _distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def analyze_storyboard(storyboard_dir: str, near_threshold: int = 6) -> dict:
    paths = sorted(set(
        glob.glob(os.path.join(storyboard_dir, "shot_*_open.jpg")) +
        glob.glob(os.path.join(storyboard_dir, "shot_*_close.jpg"))
    ))
    items = []
    for p in paths:
        h = _dhash(p)
        if h is not None:
            items.append((p, h))
    if not items:
        return {"frames": 0, "unique_frames": 0, "unique_ratio": 1.0,
                "near_duplicate_pairs": [], "threshold": near_threshold}

    # Greedy visual clusters: a frame is considered non-unique if it is close
    # to any earlier representative.
    reps: list[tuple[str, int]] = []
    near = []
    for p, h in items:
        match = None
        for rp, rh in reps:
            d = _distance(h, rh)
            if d <= near_threshold:
                match = (rp, d)
                break
        if match:
            near.append({"a": os.path.basename(match[0]), "b": os.path.basename(p),
                         "distance": match[1]})
        else:
            reps.append((p, h))

    return {
        "frames": len(items),
        "unique_frames": len(reps),
        "unique_ratio": round(len(reps) / max(1, len(items)), 4),
        "near_duplicate_pairs": near[:100],
        "threshold": near_threshold,
    }

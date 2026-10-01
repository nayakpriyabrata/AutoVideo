"""Audio director - SFX spotting, music/ambience selection (user/free assets only)."""
from __future__ import annotations
import os
import glob
import re

SFX_KEYWORDS = {
    "whoosh": [r"\bthen\b", r"\bsuddenly\b", r"\bwatch\b", r"\breveal"],
    "impact": [r"\btruth\b", r"\bpowerful\b", r"\bremember\b", r"\bnever\b"],
    "pop": [r"\bfirst\b", r"\bsecond\b", r"\bthird\b", r"\bstep one\b"],
    "click": [r"\btap\b", r"\bclick\b", r"\bpress\b"],
    "shutter": [r"\bphoto\b", r"\bpicture\b", r"\bcamera\b"],
}


def _find(kind: str) -> str | None:
    for ext in ("mp3", "wav", "ogg"):
        files = sorted(glob.glob(f"assets/sfx/{kind}*.{ext}"))
        if files:
            return files[0]
    return None


def pick_music(mood: str = "") -> str | None:
    files = sorted(glob.glob("assets/music/*.mp3") + glob.glob("assets/music/*.wav"))
    if not files:
        return None
    mood = (mood or "").lower()
    for f in files:
        name = os.path.basename(f).lower()
        if any(k in name for k in mood.split()[:3] if len(k) > 3):
            return f
    return files[0]


def pick_ambience(env_text: str = "") -> str | None:
    e = (env_text or "").lower()
    for key in ("city", "room", "wind", "birds", "cafe"):
        if key in e:
            hits = sorted(glob.glob(f"assets/ambience/{key}*.mp3") + glob.glob(f"assets/ambience/{key}*.wav"))
            if hits:
                return hits[0]
    return None


def plan_sfx(words: list[dict], segments: list[dict]) -> list[dict]:
    """Spot SFX moments from narration keywords + transitions. Max ~1 per 6s."""
    if not words:
        return []
    full = " ".join(w["word"] for w in words)
    events = []
    # transition whooshes at hard cuts (subtle)
    for s in segments[1:3]:
        p = _find("whoosh")
        if p:
            events.append({"type": "whoosh", "path": p, "at": s.get("timeline_start", 0), "vol": 0.25})
    # keyword spots
    for kind, pats in SFX_KEYWORDS.items():
        p = _find(kind)
        if not p:
            continue
        for m in list(re.finditer("|".join(f"(?:{x})" for x in pats), full, re.I))[:2]:
            # map char offset -> word time (approx)
            target = m.start()
            acc, at = 0, 0.0
            for w in words:
                acc += len(w["word"]) + 1
                if acc >= target:
                    at = w["start"]
                    break
            events.append({"type": kind, "path": p, "at": round(at, 2), "vol": 0.4})
    events.sort(key=lambda e: e["at"])
    # thin out: min 5s apart
    out, last = [], -10
    for e in events[:8]:
        if e["at"] - last >= 5:
            out.append(e)
            last = e["at"]
    return out

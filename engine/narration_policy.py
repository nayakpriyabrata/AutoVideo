"""Runtime guardrails for long-form narration generation.

Long-form script writers and TTS engines vary in how closely they hit a requested
word count. Keep the user's requested duration as the production target, while
asking for a small bounded script buffer and accepting a measured voiceover up
to one minute either side. Short videos retain the tighter percentage window.
"""
from __future__ import annotations

import math

LONGFORM_THRESHOLD_SECONDS = 120
MAX_LONGFORM_GRACE_SECONDS = 60.0
LONGFORM_GRACE_RATIO = 0.20
SHORTFORM_MIN_RATIO = 0.92
SHORTFORM_MAX_RATIO = 1.11


def narration_grace_seconds(target_seconds: float) -> float:
    """Return the allowed long-form duration drift, capped at one minute."""
    try:
        target = float(target_seconds)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(target) or target < LONGFORM_THRESHOLD_SECONDS:
        return 0.0
    return min(MAX_LONGFORM_GRACE_SECONDS, target * LONGFORM_GRACE_RATIO)


def buffered_script_target_seconds(target_seconds: float,
                                   voiceover_enabled: bool = True) -> int:
    """Add bounded headroom to long-form *script* prompts, not video duration.

    A five-minute requested video therefore asks the writer for about six
    minutes of narration. The manifest and final production target remain five
    minutes; measured TTS and the tolerance policy decide whether another
    bounded retime pass is needed.
    """
    target = max(1, int(round(float(target_seconds))))
    if not voiceover_enabled:
        return target
    return target + int(math.ceil(narration_grace_seconds(target)))


def narration_duration_matches_target(duration_seconds: float,
                                      target_seconds: float) -> bool:
    """Whether measured narration is close enough to avoid another rewrite."""
    try:
        duration = float(duration_seconds)
        target = float(target_seconds)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(duration) or not math.isfinite(target) or duration <= 0 or target <= 0:
        return False
    grace = narration_grace_seconds(target)
    if grace:
        return abs(duration - target) <= grace + 1e-6
    ratio = duration / target
    return SHORTFORM_MIN_RATIO <= ratio <= SHORTFORM_MAX_RATIO

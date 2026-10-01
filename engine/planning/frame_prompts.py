"""Opening/closing frame prompts for continuity-first storyboards."""
from __future__ import annotations


def master_character_prompt(bible: dict, vertical: bool) -> str:
    char = (bible.get("characters") or [{}])[0].get("canonical", "cinematic protagonist")
    style = bible.get("visual_style", "cinematic realism")
    aspect = "vertical 9:16" if vertical else "landscape 16:9"
    return (
        f"CHARACTER MASTER REFERENCE, {aspect}. {char}. Neutral relaxed pose, full body and clear face, "
        f"plain softly lit studio background, consistent wardrobe, natural skin texture, {style}. "
        "No text, no logo, no extra people. This is an identity reference, not an action scene."
    )


def master_location_prompt(bible: dict, vertical: bool) -> str:
    loc = (bible.get("locations") or [{}])[0].get("canonical", "cinematic environment")
    style = bible.get("visual_style", "cinematic realism")
    aspect = "vertical 9:16" if vertical else "landscape 16:9"
    return (f"LOCATION MASTER REFERENCE, {aspect}. {loc}. Empty establishing frame, coherent layout, "
            f"clean geometry, {style}, {bible.get('lighting','cinematic light')}. No text, no people.")


def frame_prompt(shot, bible: dict, vertical: bool, phase: str = "open") -> str:
    phase = "close" if phase.lower().startswith("cl") else "open"
    char = (bible.get("characters") or [{}])[0].get("canonical", "")
    canonical_loc = (bible.get("locations") or [{}])[0].get("canonical", shot.environment)
    # Scene-specific visual intent is allowed to vary the setting for educational
    # b-roll/listicles; the master location remains a style/reference anchor.
    loc = shot.environment or canonical_loc
    style = bible.get("visual_style", "cinematic realism")
    aspect = "vertical 9:16" if vertical else "landscape 16:9"
    timing = ("the instant just BEFORE the described action begins" if phase == "open" else
              "the natural END state immediately AFTER the described action completes")
    continuity = (
        f"Use the exact same protagonist identity and wardrobe: {char}. " if char else ""
    )
    return (
        f"STORYBOARD {phase.upper()} FRAME, {aspect}. Capture {timing}. "
        f"Subject: {shot.subject}. Action context: {shot.subject_action}. Environment: {loc}. "
        f"Visual direction: {shot.visual_goal}. Narrative beat: {shot.narration}. Framing: {shot.camera_framing}. "
        f"Lighting: {shot.lighting or bible.get('lighting','cinematic')}. Look: {style}. "
        f"{continuity}Keep composition compatible with the paired frame so a smooth video transition is possible. "
        "Photorealistic, stable anatomy, no text, no logo, no watermark, no UI."
    )[:3800]

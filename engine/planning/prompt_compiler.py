"""
Prompt compiler - structured cinematic prompts, model-aware adapters.
Never send loose prose; every shot compiles SUBJECT/ACTION/ENV/COMPOSITION/
CAMERA/MOTION/LIGHTING/COLOR/PHYSICS/CONTINUITY/AUDIO/NEGATIVE blocks.
"""
from __future__ import annotations
from .story_bible import continuity_sentence


def _blocks(shot, bible: dict, preset: dict, vertical: bool) -> dict:
    comp = ("vertical 9:16, subject centered in middle 60% width, keep faces clear of "
            "top 15% and bottom 25% (captions/UI safe zones)" if vertical else
            "wide 16:9 cinematic composition, rule of thirds")
    narration = str(getattr(shot, "narration", "") or "")
    professional = any(x in narration.lower() for x in (
        "speak", "communication", "meeting", "executive", "presentation",
        "career", "resume", "interview"))
    context_guard = (
        "professional workplace context; no party, nightclub, casino, dancing, vacation, beach or fantasy imagery"
        if professional else
        "literal visual support for the current narration; do not introduce unrelated activities"
    )
    return {
        "SUBJECT": shot.subject or "cinematic subject",
        "ACTION": shot.subject_action or "subtle natural motion",
        "ENVIRONMENT": shot.environment or bible["locations"][0]["canonical"] if bible.get("locations") else shot.environment,
        "COMPOSITION": f"{shot.camera_framing or 'medium shot'}, {comp}",
        "CAMERA": f"{shot.camera_movement or 'very slow dolly-in'}, {shot.lens_feeling} lens feel, stable professional movement",
        "MOTION": {"low": "minimal motion, gentle breathing, locked camera",
                   "medium": "natural lifelike motion, smooth continuous movement",
                   "high": "dynamic energetic motion, fast but smooth"}.get(shot.motion_intensity, "natural motion"),
        "LIGHTING": shot.lighting or bible.get("lighting", "cinematic lighting"),
        "COLOR": f"{shot.color_palette or preset.get('color_treatment', 'cinematic grade')}",
        "PHYSICS": "realistic physics, correct hands and faces, no morphing, no extra limbs",
        "CONTINUITY": f"{continuity_sentence(bible)} Semantic guard: {context_guard}.",
        "AUDIO": "silent visual (voiceover added in edit), no dialogue needed" if True else "",
        "NEGATIVE": ", ".join(filter(None, [shot.negative, *preset.get("negative", []),
                                           "text, logo, watermark, UI, extra people, warped hands"])),
    }


def compile_for_veo_quality(b, refr: str) -> str:
    p = (f"{b['COMPOSITION']} of {b['SUBJECT']}. {b['ACTION']}. {b['ENVIRONMENT']}. "
         f"Camera: {b['CAMERA']}. {b['LIGHTING']}. {b['COLOR']}. {b['MOTION']}. {b['PHYSICS']}. "
         f"{b['CONTINUITY']} {refr} Avoid: {b['NEGATIVE']}.")
    return p


def compile_for_veo_fast(b, refr: str) -> str:
    return compile_for_veo_quality(b, refr)


def compile_for_veo_lite(b, refr: str) -> str:
    return (f"{b['COMPOSITION']} of {b['SUBJECT']}, {b['ACTION']}. {b['ENVIRONMENT']}. "
            f"{b['CAMERA']}. {b['LIGHTING']}. {b['CONTINUITY']} No {b['NEGATIVE']}.")


def compile_for_omni(b, refr: str) -> str:
    return (f"Create a cinematic shot: {b['SUBJECT']} — {b['ACTION']} in {b['ENVIRONMENT']}. "
            f"Framing {b['COMPOSITION']}; camera {b['CAMERA']}. Lighting: {b['LIGHTING']}; "
            f"look: {b['COLOR']}. {b['REF'] if False else ''}{b['CONTINUITY']} {refr}"
            f"Keep it clean: no {b['NEGATIVE']}.")


def _tags(b) -> str:
    return ", ".join([b["SUBJECT"], b["ACTION"], b["ENVIRONMENT"], b["COMPOSITION"],
                      b["CAMERA"], b["LIGHTING"], b["COLOR"], b["MOTION"],
                      "photorealistic", "high detail", "smooth motion"])


def compile_for_comfy(b, refr: str) -> str:
    return _tags(b) + f". {b['CONTINUITY']}"


def compile_for_wan(b, refr: str) -> str:
    return _tags(b) + ", cinematic, stable camera"


def compile_for_ltx(b, refr: str) -> str:
    return _tags(b) + ", fluid motion, coherent sequence"


ADAPTERS = {"veo_quality": compile_for_veo_quality, "veo_fast": compile_for_veo_fast,
            "veo_lite": compile_for_veo_lite, "omni_draft": compile_for_omni,
            "omni_standard": compile_for_omni, "comfy": compile_for_comfy,
            "wan_t2v": compile_for_comfy, "wan_i2v": compile_for_comfy,
            "ltx_t2v": compile_for_ltx, "ltx_i2v": compile_for_ltx,
            "stock": compile_for_veo_lite, "kenburns_plus": compile_for_comfy}


def compile_shot(shot, bible: dict, preset: dict, vertical: bool = True) -> dict:
    """Returns {prompt, negative, adapter} and sets shot.compiled_prompt."""
    b = _blocks(shot, bible, preset, vertical)
    refs = shot.reference_assets + ([shot.start_frame] if shot.start_frame else [])
    refr = f"Use the supplied reference image(s) for identity ({len(refs)} attached). " if refs else ""
    fn = ADAPTERS.get(shot.model, compile_for_veo_lite)
    prompt = fn(b, refr).replace("  ", " ").strip()
    shot.compiled_prompt = prompt
    return {"prompt": prompt, "negative": b["NEGATIVE"], "adapter": getattr(fn, "__name__", shot.model)}

"""
Story Bible - canonical identities for characters/locations/objects/style.
The SAME identity string is injected into every relevant prompt (no drift).
"""
from __future__ import annotations
import re


def _needs_character(content_type: str) -> bool:
    return content_type in ("storytelling", "cinematic_story", "kids_story", "advertisement",
                            "product_demo", "motivation", "documentary")


def build_bible(topic: str, content_type: str, preset_cfg: dict,
                audience: str = "", tone: str = "cinematic") -> dict:
    vocab = preset_cfg.get("prompt_vocabulary", ["cinematic", "high detail"])
    style = (", ".join(vocab[:3]) + ", " + preset_cfg.get("color_treatment", "")).strip(", ")
    lighting = preset_cfg.get("lighting", "cinematic lighting")

    characters, locations, objects = [], [], []
    if _needs_character(content_type):
        kid = content_type == "kids_story"
        characters.append({
            "id": "CHARACTER_01",
            "role": "protagonist",
            "canonical": ("cheerful 8-year-old kid, big expressive eyes, messy black hair, "
                          "yellow t-shirt, blue shorts" if kid else
                          "adult around 30, Indian, short black hair, trimmed beard, "
                          "navy shirt, beige trousers, slim athletic build"),
        })
    # Location derived from topic keywords (studio-safe default)
    loc_canon = "modern apartment interior, warm wood furniture, large east-facing window, cream walls"
    if re.search(r"office|startup|business|money|financ", topic, re.I):
        loc_canon = "modern startup office, glass walls, warm desk lamps, city view at dusk"
    elif re.search(r"kitchen|food|cook|recipe", topic, re.I):
        loc_canon = "bright modern kitchen, marble counter, morning sunlight, fresh ingredients"
    elif re.search(r"outdoor|walk|morning|nature|travel|mountain|beach", topic, re.I):
        loc_canon = "quiet city street at sunrise, soft mist, warm golden light"
    elif re.search(r"tech|ai|robot|phone|app|software", topic, re.I):
        loc_canon = "sleek tech studio, dark surfaces, soft blue accent light, laptop close by"
    locations.append({"id": "LOCATION_01", "role": "primary", "canonical": loc_canon})

    if content_type in ("advertisement", "product_demo"):
        objects.append({"id": "PRODUCT_01", "role": "hero product",
                        "canonical": f"hero product representing {topic}, clean studio presentation"})

    return {
        "characters": characters, "locations": locations, "objects": objects,
        "visual_style": style, "lighting": lighting,
        "continuity_rules": [
            "Same face, hairstyle, wardrobe for CHARACTER_01 in every shot.",
            "Same room layout, furniture, window light for LOCATION_01.",
            "No extra people unless the shot explicitly requires them.",
            "No text, logos, watermarks, or UI elements in frame.",
            "Physically plausible motion; no morphing limbs or melting objects.",
        ],
        "identity_block": _identity_block(characters, locations, objects),
    }


def _identity_block(chars, locs, objs) -> str:
    parts = []
    for c in chars:
        parts.append(f"{c['id']} = {c['canonical']}")
    for l in locs:
        parts.append(f"{l['id']} = {l['canonical']}")
    for o in objs:
        parts.append(f"{o['id']} = {o['canonical']}")
    return "; ".join(parts)


def continuity_sentence(bible: dict) -> str:
    ids = [c["id"] for c in bible.get("characters", [])]
    ids += [l["id"] for l in bible.get("locations", [])]
    if not ids:
        return "Maintain consistent lighting, color and environment from the reference."
    return (f"Maintain the EXACT identity from reference: {bible['identity_block']}. "
            f"Do not redesign, recast, or restyle {', '.join(ids)}.")

"""Per-job presentation choices, independent of paid visual generation."""
from __future__ import annotations
from dataclasses import dataclass
import math

CARD_STYLES = ("auto", "bold", "playful", "clean")
PRESENTATION_KEYS = {
    "voiceover_enabled", "text_cards_enabled", "text_card_style", "caption_display",
    "background_music", "background_music_path", "music_volume",
    "sound_effects_enabled", "ambience_enabled",
}


def _boolean(settings, name, default):
    value = settings.get(name)
    if value is None:
        return default
    if type(value) is not bool:
        raise ValueError(f"{name} must be true or false, not {value!r}")
    return value


@dataclass(frozen=True)
class Presentation:
    voiceover: bool
    text_cards: bool
    card_style: str
    captions: str
    music_mode: str
    music_path: str
    music_volume: float
    sound_effects: bool
    ambience: bool


def resolve_presentation(settings: dict) -> Presentation:
    """Old jobs retain their recipe; an explicit false always wins over Pro mode."""
    pro = str(settings.get("production_mode", "legacy")).lower() in ("youtube_pro", "reels_pro")
    voice = _boolean(settings, "voiceover_enabled", True)
    cards = _boolean(settings, "text_cards_enabled", bool(settings.get("graphics_overlays", False) or pro))
    style = str(settings.get("text_card_style") or "auto").lower()
    if style not in CARD_STYLES:
        raise ValueError(f"text_card_style must be one of {CARD_STYLES}")
    captions = str(settings.get("caption_display") or "auto").lower()
    if captions not in ("auto", "full", "none"):
        raise ValueError("caption_display must be auto, full or none")
    if not voice:
        captions = "none"  # A silent story is not a spoken transcript.
    elif captions == "auto":
        captions = "none" if pro else "full"
    music_mode = str(settings.get("background_music") or "off").lower()
    if music_mode not in ("off", "auto", "local", "browser"):
        raise ValueError("background_music must be off, auto, local or browser")
    path = str(settings.get("background_music_path") or "").strip()
    volume = settings.get("music_volume")
    if volume is None:
        volume = (.10 if pro else .16) if voice else .55
    if type(volume) not in (int, float) or not math.isfinite(volume) or not 0 <= volume <= 1:
        raise ValueError("music_volume must be a finite number between 0 and 1")
    return Presentation(voice, cards, style, captions, music_mode, path, float(volume),
                        _boolean(settings, "sound_effects_enabled", voice),
                        _boolean(settings, "ambience_enabled", voice))


def visual_duration(manifest) -> float:
    """Existing shots keep their clock when muted; new silent jobs use target time."""
    shots = list(getattr(manifest, "shots", []) or [])
    duration = (max(float(s.voice_end) for s in shots) if shots
                else float(manifest.target_seconds))
    if not math.isfinite(duration) or not .1 <= duration <= 6 * 3600:
        raise ValueError("Invalid visual story duration")
    return duration

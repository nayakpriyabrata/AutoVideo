"""Friendly YAML configuration for the v5.7 Studio and CLI.

The CLI remains the source of truth for execution.  This module gives both the
dashboard and ``create-config`` one validated, reproducible input format.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import yaml


DEFAULTS = {
    "topic": "",
    "production_mode": "youtube_pro",
    "video_type": "faceless_youtube",
    "theme": "motivational",
    "duration": 300,
    "profile": "STORYBOARD_ECONOMY",
    "preset": "cinematic_realism",
    "content_type": "education",
    "tone": "cinematic",
    "language": "en",
    "voice": "en-IN-PrabhatNeural",
    "script_provider": "auto",
    "script_model": "auto",
    "script_quality": "publish",
    "gemini_chat_cleanup": "delete-after-read",
    "tts_provider": "auto",
    "tts_model": "",
    "tts_voice": "",
    "tts_style": "",
    "caption_provider": "auto",
    "caption_display": "auto",
    "render_quality": "high",
    "dynamic_video_scenes": None,
    "stock_scenes": None,
    "stock_source": "auto",
    "background_music": "off",
    "music_mood": "",
    "channel_name": "",
    "channel_logo": "",
    "graphics_overlays": False,
    "voiceover_enabled": True,
    "text_cards_enabled": None,
    "text_card_style": "auto",
    "background_music_path": "",
    "music_volume": None,
    "sound_effects_enabled": None,
    "ambience_enabled": None,
    "watermark": False,
    "images_per_shot": 2,
    "flow_image_workers": 1,
    "video_share": 0.20,
    "stock_share": 0.60,
    "flow_scenes": None,
    "max_flow_scenes": None,
    "frame_source": "auto",
    "flow_approval": "once",
    "flow_project_url": "",
    "flow_reuse_project_media": True,
    "flow_reuse_mode": "exact",
    "max_credits": 100,
    "max_retries": 2,
    "max_generation_credits": 10,
    "flow_frame_retries": 3,
    "network_wait_seconds": 300,
    "flow_capacity_wait_seconds": 900,
    "flow_capacity_retries": 8,
    "flow_video_retries": 1,
    "flow_video_ready_grace_seconds": 20,
    "flow_video_recovery_wait_seconds": 180,
    "shot_max_seconds": None,
    "dry_run": False,
    "plan_only": False,
}

THEMES = {
    "kids_cartoon": {"content_type": "kids_story", "tone": "funny", "preset": "cartoon_3d", "music_mood": "playful children instrumental"},
    "devotional_cartoon": {"content_type": "storytelling", "tone": "calm", "preset": "cartoon_3d", "music_mood": "peaceful devotional instrumental"},
    "devotional_real": {"content_type": "documentary", "tone": "calm", "preset": "cinematic_realism", "music_mood": "peaceful devotional instrumental"},
    "motivational": {"content_type": "motivation", "tone": "cinematic", "preset": "cinematic_realism", "music_mood": "soft motivational cinematic instrumental"},
    "cooking": {"content_type": "education", "tone": "exciting", "preset": "cinematic_realism", "music_mood": "light upbeat cooking instrumental"},
    "health": {"content_type": "education", "tone": "documentary", "preset": "cinematic_realism", "music_mood": "clean calm wellness instrumental"},
    "personal_finance": {"content_type": "finance", "tone": "documentary", "preset": "cinematic_realism", "music_mood": "modern confident business instrumental"},
    "personality_development": {"content_type": "motivation", "tone": "cinematic", "preset": "cinematic_realism", "music_mood": "uplifting personal growth instrumental"},
    "cartoon_story": {"content_type": "cinematic_story", "tone": "funny", "preset": "cartoon_3d", "music_mood": "whimsical story instrumental"},
}

CHOICES = {
    "production_mode": {"legacy", "youtube_pro", "reels_pro"},
    "video_type": {"shorts", "faceless_youtube", "explainer", "marketing"},
    "profile": {"FLOW_CINEMATIC", "FLOW_BALANCED", "FLOW_ECONOMY", "STORYBOARD_ECONOMY", "LOCAL_FREE", "FREE_HYBRID", "MANUAL_DIRECTOR"},
    "script_provider": {"auto", "gemini", "gemini-web", "groq", "openai", "grok", "ollama", "planner"},
    "script_quality": {"standard", "high", "publish"},
    "tts_provider": {"auto", "gemini", "gemini-lite", "groq", "elevenlabs", "kokoro", "edge", "gtts", "mock"},
    "caption_display": {"auto", "full", "none"},
    "text_card_style": {"auto", "bold", "playful", "clean"},
    "render_quality": {"preview", "standard", "high"},
    "frame_source": {"auto", "flow", "free"},
    "flow_approval": {"once", "manual", "always"},
    "flow_reuse_mode": {"exact", "topic", "project"},
    "gemini_chat_cleanup": {"keep", "delete-after-read"},
}


def load_video_config(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ValueError(f"Configuration file not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Video configuration must be a YAML mapping")
    unknown = sorted(set(raw) - set(DEFAULTS))
    if unknown:
        raise ValueError("Unknown configuration option(s): " + ", ".join(unknown))
    cfg = copy.deepcopy(DEFAULTS)
    cfg.update(raw)
    cfg["topic"] = str(cfg.get("topic") or "").strip()
    if not cfg["topic"]:
        raise ValueError("topic is required")
    theme = str(cfg.get("theme") or "motivational")
    if theme not in THEMES:
        raise ValueError(f"Unknown theme {theme!r}. Use one of: {', '.join(THEMES)}")
    # Theme values are defaults, never overrides for explicitly supplied keys.
    for key, value in THEMES[theme].items():
        if key not in raw:
            cfg[key] = value
    mode = str(cfg.get("production_mode") or "youtube_pro")
    if mode == "reels_pro":
        if "video_type" not in raw:
            cfg["video_type"] = "shorts"
        if "duration" not in raw:
            cfg["duration"] = 45
        if "caption_display" not in raw:
            cfg["caption_display"] = "full"
        if "graphics_overlays" not in raw:
            cfg["graphics_overlays"] = True
    for key, values in CHOICES.items():
        if cfg.get(key) not in values:
            raise ValueError(f"Invalid {key}: {cfg.get(key)!r}; choose from {sorted(values)}")
    cfg["duration"] = int(cfg["duration"])
    if not 10 <= cfg["duration"] <= 7200:
        raise ValueError("duration must be between 10 and 7200 seconds")
    cfg["flow_image_workers"] = int(cfg.get("flow_image_workers") or 1)
    if not 1 <= cfg["flow_image_workers"] <= 3:
        raise ValueError("flow_image_workers must be 1, 2, or 3")
    from .presentation import resolve_presentation
    presentation = resolve_presentation(cfg)
    if not presentation.voiceover:
        cfg["caption_display"] = "none"
    if cfg["background_music_path"]:
        music_path = Path(cfg["background_music_path"]).expanduser()
        cfg["background_music_path"] = os.fspath((p.parent / music_path).resolve() if not music_path.is_absolute() else music_path.resolve())
    cfg["production_mode_engine"] = "youtube_pro" if mode == "reels_pro" else mode
    cfg["aspect"] = "9:16" if cfg["video_type"] == "shorts" or mode == "reels_pro" else "16:9"
    cfg["config_source"] = os.fspath(p)
    return cfg


def config_to_factory_kwargs(cfg: dict) -> dict:
    skip = {"topic", "duration", "video_type", "aspect", "theme", "max_credits", "max_retries",
            "plan_only", "config_source", "production_mode_engine"}
    out = {k: v for k, v in cfg.items() if k not in skip}
    out["target_seconds"] = int(cfg["duration"])
    out["production_mode"] = cfg["production_mode_engine"]
    out["production_mode"] = cfg["production_mode_engine"]
    out["budgets"] = {"MAX_CREDITS_PER_VIDEO": int(cfg["max_credits"]),
                      "MAX_RETRIES_PER_SHOT": int(cfg["max_retries"])}
    return out

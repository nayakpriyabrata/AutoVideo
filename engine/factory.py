"""
Factory (v3 orchestrator) - Topic -> plan -> script -> narration -> storyboard ->
Flow/local generation -> QC -> retries -> edit -> captions -> sound -> 1080p.

Resumable: every stage persists; rerunning continues where it stopped.
DRY RUN vs FLOW CREDIT GENERATION vs LOCAL FREE are always explicit.
"""
from __future__ import annotations
import os
import json
import shutil
import time
import hashlib
import glob
import yaml

from .project.manager import ProjectManager
from .project.database import JobDB
from .project.manifest import ProductionManifest, Shot
from .planning.script import plan_content
from .planning.story_bible import build_bible
from .planning.director import create_production_plan
from .planning.prompt_compiler import compile_shot
from .routing.credit_router import CreditRouter
from .routing.provider_router import ProviderRouter, NeedsDecision
from .reference_manager import ReferenceManager
from .audio.tts import synthesize_narration, fit_narration_to_target
from .runtime_log import runtime_print as print
from .presentation import resolve_presentation, visual_duration, PRESENTATION_KEYS
from .providers.flow_browser import FlowRequestPending

# Profiles that use the Flow browser bridge (scene images + Veo/Omni generation).
FLOW_PROFILES = ("FLOW_CINEMATIC", "FLOW_BALANCED", "FLOW_ECONOMY", "STORYBOARD_ECONOMY", "MANUAL_DIRECTOR")


class AssistedNeeded(Exception):
    def __init__(self, job_id: str, shot_id: str, prompt: str, watch_dir: str, reason: str):
        super().__init__(f"Assisted Flow Mode needed for {shot_id}: {reason}")
        self.job_id, self.shot_id, self.prompt, self.watch_dir, self.reason = \
            job_id, shot_id, prompt, watch_dir, reason


def load_preset(name: str) -> dict:
    # Studio's older theme identifier must not silently load photorealism.
    name = "cartoon_story" if name == "cartoon_3d" else name
    p = os.path.join("config", "presets", f"{name}.yaml")
    if not os.path.exists(p):
        p = os.path.join("config", "presets", "cinematic_realism.yaml")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_json(path: str, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


class Factory:
    def _pause_pending_flow(self, m, shot_id, error, project_url=""):
        current = self.pm.load_manifest(m.job_id)
        current.status = "paused"
        self.pm.save_manifest(current)
        self.db.upsert(m.job_id, status="paused")
        self._write_pause_state(m.job_id, shot_id, str(error),
                                kind="flow_download_or_ui", project_url=project_url)
        raise NeedsDecision(str(error), alternatives=[f"python3 cli.py v3 resume {m.job_id}"])
    def __init__(self, outputs: str = "outputs", db_path: str = "data/jobs.db"):
        self.pm = ProjectManager(outputs)
        self.db = JobDB(db_path)

    # ---------------- job setup ----------------
    def create_job(self, topic: str, video_type: str = "shorts", target_seconds: int = 45,
                   aspect: str = "9:16", language: str = "en", voice: str = "en-IN-PrabhatNeural",
                   content_type: str = "education", tone: str = "cinematic",
                   preset: str = "cinematic_realism", profile: str = "FLOW_BALANCED",
                   cartoon_provider: str = "flow", movieflow_mode: str = "full_story",
                   movieflow_project_url: str = "", movieflow_wait_seconds: int = 1800,
                   movieflow_recovery_wait_seconds: int = 300,
                   budgets: dict | None = None, dry_run: bool = False,
                   tts_provider: str = "auto", images_per_shot: int = 2,
                   video_share: float = 0.20, stock_share: float = 0.60,
                   flow_scenes: int | None = None, max_flow_scenes: int | None = None, frame_source: str = "auto",
                   flow_approval: str = "once", max_generation_credits: int = 10,
                   shot_max_seconds: float | None = None, flow_frame_retries: int = 3,
                   network_wait_seconds: int = 300, flow_capacity_wait_seconds: int = 900,
                   flow_capacity_retries: int = 8, flow_project_url: str = "",
                   flow_video_retries: int = 1, flow_video_ready_grace_seconds: int = 20,
                   flow_video_recovery_wait_seconds: int = 180,
                   flow_reuse_project_media: bool = True,
                   flow_reuse_mode: str = "exact",
                   flow_image_workers: int = 1,
                   gemini_chat_cleanup: str = "keep",
                   script_provider: str = "auto", script_model: str = "auto",
                   script_quality: str = "publish", tts_model: str = "",
                   tts_voice: str = "", tts_style: str = "",
                   caption_provider: str = "auto", caption_model: str = "whisper-large-v3-turbo",
                   caption_local_model: str = "small", caption_align_script: bool = True,
                   max_tts_speedup: float = 1.08, auto_retime_script: bool = True,
                   render_quality: str = "high",
                   production_mode: str = "legacy", dynamic_video_scenes: int | None = None,
                   stock_scenes: int | None = None, stock_source: str = "auto",
                   caption_display: str = "auto", background_music: str = "off",
                   music_mood: str = "", channel_name: str = "", channel_logo: str = "",
                   graphics_overlays: bool = False, watermark: bool = False,
                   voiceover_enabled: bool | None = None, text_cards_enabled: bool | None = None,
                   text_card_style: str = "auto", background_music_path: str = "",
                   music_volume: float | None = None, sound_effects_enabled: bool | None = None,
                   ambience_enabled: bool | None = None, destination: str | None = None,
                   approved_plan_path: str = "", narration_input_path: str = "",
                   character_id: str = "") -> str:
        from .languages import language_pack, default_voice
        language = language_pack(language).code
        if voice == 'en-IN-PrabhatNeural' and language != 'en':
            voice = default_voice(language)
        if language == 'or' and caption_provider in ('auto','groq','local'):
            caption_provider = 'script-timed'  # Explicit estimated timings; never pretend Whisper supports or.
        delivery = None
        if destination:
            from .publishing import destination_profile
            delivery = destination_profile(destination)
            aspect = '16:9' if destination == 'youtube_long' else '9:16'
            if target_seconds > delivery['max_seconds']:
                raise ValueError('Duration exceeds the chosen conservative delivery recipe')
        if character_id:
            from .content_library import CharacterLibrary
            CharacterLibrary().get(character_id)
        if approved_plan_path:
            from .content_plan import load_plan
            approved = load_plan(approved_plan_path)
            if approved['language'] != language:
                raise ValueError('Imported plan language must match the job language')
        resolve_presentation({"voiceover_enabled": voiceover_enabled, "text_cards_enabled": text_cards_enabled,
                              "text_card_style": text_card_style, "background_music": background_music,
                              "music_volume": music_volume, "sound_effects_enabled": sound_effects_enabled,
                              "ambience_enabled": ambience_enabled, "caption_display": caption_display})
        W, H = (1080, 1920) if aspect == "9:16" else (1920, 1080)
        m = ProductionManifest(job_id=self.pm.new_job_id(topic), topic=topic, video_type=video_type,
                               target_seconds=target_seconds, aspect=aspect, width=W, height=H,
                               language=language, voice=voice, content_type=content_type, tone=tone,
                               preset=preset, profile=profile, dry_run=dry_run)
        self.pm.create(m)
        _save_json(os.path.join(self.pm.job_dir(m.job_id), "settings.json"),
                   {"budgets": budgets or {}, "tts_provider": tts_provider,
                    "cartoon_provider": str(cartoon_provider or "flow"),
                    "movieflow_mode": str(movieflow_mode or "full_story"),
                    "movieflow_project_url": str(movieflow_project_url or "").strip(),
                    "movieflow_wait_seconds": int(movieflow_wait_seconds or 1800),
                    "movieflow_recovery_wait_seconds": int(movieflow_recovery_wait_seconds or 300),
                    "images_per_shot": images_per_shot,
                    "video_share": float(video_share), "stock_share": float(stock_share),
                    "flow_scenes": flow_scenes, "max_flow_scenes": max_flow_scenes, "frame_source": frame_source,
                    "flow_approval": flow_approval,
                    "max_generation_credits": int(max_generation_credits),
                    "shot_max_seconds": shot_max_seconds,
                    "flow_frame_retries": int(flow_frame_retries),
                    "network_wait_seconds": int(network_wait_seconds),
                    "flow_capacity_wait_seconds": int(flow_capacity_wait_seconds),
                    "flow_capacity_retries": int(flow_capacity_retries),
                    "flow_project_url": str(flow_project_url or "").strip(),
                    "flow_video_retries": int(flow_video_retries),
                    "flow_video_ready_grace_seconds": int(flow_video_ready_grace_seconds),
                    "flow_video_recovery_wait_seconds": int(flow_video_recovery_wait_seconds),
                    "flow_reuse_project_media": bool(flow_reuse_project_media),
                    "flow_reuse_mode": str(flow_reuse_mode or "exact"),
                    "flow_image_workers": max(1, min(3, int(flow_image_workers or 1))),
                    "gemini_chat_cleanup": str(gemini_chat_cleanup or "keep"),
                    "script_provider": str(script_provider or "auto"),
                    "script_model": str(script_model or "auto"),
                    "script_quality": str(script_quality or "publish"),
                    "tts_model": str(tts_model or ""),
                    "tts_voice": str(tts_voice or ""),
                    "tts_style": str(tts_style or ""),
                    "caption_provider": str(caption_provider or "auto"),
                    "caption_model": str(caption_model or "whisper-large-v3-turbo"),
                    "caption_local_model": str(caption_local_model or "small"),
                    "caption_align_script": bool(caption_align_script),
                    "max_tts_speedup": float(max_tts_speedup or 1.08),
                    "auto_retime_script": bool(auto_retime_script),
                    "render_quality": str(render_quality or "high"),
                    "production_mode": str(production_mode or "legacy"),
                    "dynamic_video_scenes": dynamic_video_scenes,
                    "stock_scenes": stock_scenes,
                    "stock_source": str(stock_source or "auto"),
                    "caption_display": str(caption_display or "full"),
                    "background_music": str(background_music or "off"),
                    "music_mood": str(music_mood or ""),
                    "channel_name": str(channel_name or ""),
                    "channel_logo": str(channel_logo or ""),
                    "graphics_overlays": bool(graphics_overlays),
                    "watermark": bool(watermark),
                    "voiceover_enabled": voiceover_enabled, "text_cards_enabled": text_cards_enabled,
                    "text_card_style": text_card_style, "background_music_path": background_music_path,
                    "music_volume": music_volume, "sound_effects_enabled": sound_effects_enabled,
                    "ambience_enabled": ambience_enabled, "destination": destination,
                    "approved_plan_path": approved_plan_path, "narration_input_path": narration_input_path,
                    "character_id": character_id})
        # Freeze these two choices for new jobs; later global defaults must not
        # unexpectedly switch a saved storyboard to a different recipe.
        job_settings_path = os.path.join(self.pm.job_dir(m.job_id), "settings.json")
        actual = resolve_presentation(self._settings(m.job_id))
        job_settings = json.load(open(job_settings_path, encoding="utf-8"))
        job_settings.update(voiceover_enabled=actual.voiceover, text_cards_enabled=actual.text_cards)
        _save_json(job_settings_path, job_settings)
        m.voiceover_enabled = actual.voiceover
        m.timing_source = "narration" if actual.voiceover else "visual_storyboard"
        self.pm.save_manifest(m)
        self.db.upsert(m.job_id, topic=topic, status="created", video_type=video_type,
                       target_seconds=target_seconds, aspect=aspect, profile=profile,
                       preset=preset, dry_run=1 if dry_run else 0,
                       flow_project=str(flow_project_url or "").strip())
        self.pm.log(m.job_id, "job_created", {"profile": profile, "preset": preset, "dry_run": dry_run})
        if approved_plan_path:
            self.import_content_plan(m.job_id, approved)
        if character_id:
            from .content_library import CharacterLibrary, character_snapshot
            _save_json(os.path.join(self.pm.job_dir(m.job_id), 'character_snapshot.json'),
                       character_snapshot(CharacterLibrary().get(character_id)))
        return m.job_id

    def _settings(self, job_id: str) -> dict:
        merged: dict = {"budgets": {}, "tts_provider": "auto", "monthly_credits": None,
                    "cartoon_provider": "flow", "movieflow_mode": "full_story",
                    "movieflow_project_url": "", "movieflow_wait_seconds": 1800,
                    "movieflow_recovery_wait_seconds": 300,
                    "images_per_shot": 2, "video_share": 0.20, "stock_share": 0.60,
                    "flow_scenes": None, "max_flow_scenes": None, "frame_source": "auto",
                    "flow_approval": "once", "max_generation_credits": 10,
                    "shot_max_seconds": None, "flow_frame_retries": 3,
                    "network_wait_seconds": 300, "flow_capacity_wait_seconds": 900,
                    "flow_capacity_retries": 8, "flow_project_url": "",
                    "flow_video_retries": 1, "flow_video_ready_grace_seconds": 20,
                    "flow_video_recovery_wait_seconds": 180, "flow_reuse_project_media": True,
                    "flow_reuse_mode": "exact", "flow_image_workers": 1,
                    "gemini_chat_cleanup": "keep",
                    "script_provider": "auto", "script_model": "auto", "script_quality": "publish",
                    "tts_model": "", "tts_voice": "", "tts_style": "",
                    "caption_provider": "auto", "caption_model": "whisper-large-v3-turbo",
                    "caption_local_model": "small", "caption_align_script": True,
                    "max_tts_speedup": 1.08, "auto_retime_script": True,
                    "render_quality": "high", "production_mode": "legacy",
                    "dynamic_video_scenes": None, "stock_scenes": None, "stock_source": "auto",
                    "caption_display": "auto", "background_music": "off", "music_mood": "",
                    "channel_name": "", "channel_logo": "", "graphics_overlays": False, "watermark": False,
                    "voiceover_enabled": True, "text_cards_enabled": None, "text_card_style": "auto",
                    "background_music_path": "", "music_volume": None,
                    "sound_effects_enabled": None, "ambience_enabled": None, "destination": None, "approved_plan_path": "",
                    "narration_input_path": "", "character_id": ""}
        try:  # global user defaults
            import yaml as _yaml
            if os.path.exists("config/user_settings.yaml"):
                with open("config/user_settings.yaml", encoding="utf-8") as f:
                    g = _yaml.safe_load(f) or {}
                merged["budgets"] = dict(g.get("budgets", {}))
                merged["tts_provider"] = g.get("tts_provider", "auto")
                merged["monthly_credits"] = g.get("monthly_credits")
                merged["images_per_shot"] = int(g.get("images_per_shot", 2) or 0)
                for key in ("cartoon_provider", "movieflow_mode", "movieflow_project_url", "movieflow_wait_seconds", "movieflow_recovery_wait_seconds", "video_share", "stock_share", "flow_scenes", "max_flow_scenes", "frame_source",
                            "flow_approval", "max_generation_credits", "shot_max_seconds",
                            "flow_frame_retries", "network_wait_seconds",
                            "flow_capacity_wait_seconds", "flow_capacity_retries",
                            "flow_project_url", "flow_video_retries", "flow_video_ready_grace_seconds",
                            "flow_video_recovery_wait_seconds", "flow_reuse_project_media",
                            "flow_reuse_mode", "flow_image_workers", "gemini_chat_cleanup",
                        "script_provider", "script_model", "script_quality",
                            "tts_model", "tts_voice", "tts_style", "caption_provider",
                            "caption_model", "caption_local_model", "caption_align_script",
                            "max_tts_speedup", "auto_retime_script", "render_quality",
                            "production_mode", "dynamic_video_scenes", "stock_scenes", "stock_source",
                            "caption_display", "background_music", "music_mood", "channel_name", "channel_logo",
                            "graphics_overlays", "watermark", "voiceover_enabled", "text_cards_enabled", "text_card_style",
                            "background_music_path", "music_volume", "sound_effects_enabled", "ambience_enabled", "destination",
                            "approved_plan_path", "narration_input_path", "character_id"):
                    if key in g:
                        merged[key] = g[key]
        except Exception:
            pass
        try:  # per-job overrides
            with open(os.path.join(self.pm.job_dir(job_id), "settings.json"), encoding="utf-8") as f:
                j = json.load(f)
            merged["budgets"].update(j.get("budgets", {}))
            merged["tts_provider"] = j.get("tts_provider", merged["tts_provider"])
            if "images_per_shot" in j:
                merged["images_per_shot"] = int(j["images_per_shot"] or 0)
            for key in ("cartoon_provider", "movieflow_mode", "movieflow_project_url", "movieflow_wait_seconds", "movieflow_recovery_wait_seconds", "video_share", "stock_share", "flow_scenes", "max_flow_scenes", "frame_source",
                        "flow_approval", "max_generation_credits", "shot_max_seconds",
                        "flow_frame_retries", "network_wait_seconds",
                        "flow_capacity_wait_seconds", "flow_capacity_retries",
                        "flow_project_url", "flow_video_retries", "flow_video_ready_grace_seconds",
                        "flow_video_recovery_wait_seconds", "flow_reuse_project_media",
                        "flow_reuse_mode", "flow_image_workers", "gemini_chat_cleanup",
                        "script_provider", "script_model", "script_quality",
                        "tts_model", "tts_voice", "tts_style", "caption_provider",
                        "caption_model", "caption_local_model", "caption_align_script",
                        "max_tts_speedup", "auto_retime_script", "render_quality",
                        "production_mode", "dynamic_video_scenes", "stock_scenes", "stock_source",
                        "caption_display", "background_music", "music_mood", "channel_name", "channel_logo",
                        "graphics_overlays", "watermark", "voiceover_enabled", "text_cards_enabled", "text_card_style",
                            "background_music_path", "music_volume", "sound_effects_enabled", "ambience_enabled", "destination",
                            "approved_plan_path", "narration_input_path", "character_id"):
                if key in j and not (key in PRESENTATION_KEYS and j[key] is None):
                    merged[key] = j[key]
        except Exception:
            pass
        return merged

    @staticmethod
    def _movieflow_full_story_enabled(m, settings: dict) -> bool:
        return (str(settings.get("cartoon_provider", "flow")).lower() == "movieflow"
                and str(settings.get("movieflow_mode", "full_story")).lower() == "full_story"
                and str(getattr(m, "content_type", "")).lower() in {"kids_story", "cartoon_story", "story", "kids"})

    def _remember_movieflow_project_url(self, job_id: str, url: str | None) -> str:
        try:
            from .providers.movieflow_browser import MovieFlowBrowser
            url = MovieFlowBrowser.normalize_project_url(url)
        except Exception:
            url = str(url or "").strip()
        if not url:
            return ""
        try:
            sp = os.path.join(self.pm.job_dir(job_id), "settings.json")
            cfg = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
            if cfg.get("movieflow_project_url") != url:
                cfg["movieflow_project_url"] = url
                _save_json(sp, cfg)
                self.pm.log(job_id, "movieflow_project_bound", {"url": url})
                print(f"[MovieFlow] Bound AutoVideoAI job to MovieFlow project: {url}")
        except Exception:
            pass
        return url

    @staticmethod
    def _movieflow_story_prompt(m, plan: dict, bible: dict, preset: dict, narration_dur: float) -> str:
        chars = bible.get("characters") or bible.get("character") or bible.get("main_character") or []
        locs = bible.get("locations") or bible.get("location") or bible.get("setting") or []
        style = (bible.get("visual_style") or preset.get("visual_style") or preset.get("style")
                 or "cinematic family-friendly cartoon animation")
        mood = getattr(m, "tone", "warm")
        return (
            ("Create a complete dialogue-free cartoon story from the following visual story notes. "
             if not getattr(m, "voiceover_enabled", True) else
             "Create a complete cartoon story video from the following original narration. ") +
            "Use MovieFlow's story/Agent workflow to parse the story into coherent scenes. "
            "Keep the SAME main character identity, face, hairstyle, body proportions, wardrobe colors and art style in every scene. "
            "Maintain location continuity unless the story clearly changes setting. Avoid text, subtitles, logos and watermarks inside the generated visuals. "
            f"Target runtime: about {max(10, int(round(narration_dur)))} seconds. Aspect ratio: {getattr(m, 'aspect', '16:9')}. "
            f"Visual style: {style}. Mood: {mood}. "
            f"Character bible: {json.dumps(chars, ensure_ascii=False)[:2500]}. "
            f"Setting/location bible: {json.dumps(locs, ensure_ascii=False)[:1800]}. "
            "Story outcome must match the final narration sentence. Build clear beginning, middle, climax/lesson and ending. "
            "Generate a polished, family-friendly cartoon video with expressive acting, readable visual storytelling and smooth shot-to-shot continuity.\n\n"
            "NARRATION/STORY:\n" + str(plan.get("narration") or m.topic)
        )

    def _prepare_movieflow_full_story(self, m, plan: dict, bible: dict, preset: dict, narration_dur: float):
        prompt = self._movieflow_story_prompt(m, plan, bible, preset, narration_dur)
        shot = Shot(
            shot_id="shot_001", voice_start=0.0, voice_end=float(narration_dur),
            duration_target=float(narration_dur), narration=str(plan.get("narration") or ""),
            coverage="hero_outro", visual_goal=f"Complete MovieFlow cartoon story for: {m.topic}",
            subject=str(m.topic), subject_action="complete story progression",
            environment="MovieFlow story world from the character/location bible",
            camera_framing="cinematic animated sequence", camera_movement="story-driven",
            lighting="consistent stylized cartoon lighting", color_palette=str(getattr(m, "color_palette", "")),
            motion_intensity="medium", provider="movieflow", model="movieflow_story",
            gen_duration=max(4, int(round(narration_dur))), num_candidates=1,
            media_strategy="movieflow_full_story", compiled_prompt=prompt, qc_threshold=55, status="planned")
        m.shots = [shot]
        return m

    def _flow_project_url(self, job_id: str, settings: dict | None = None) -> str:
        """Resolve the exact Flow project URL for a job. Explicit setting wins, then DB."""
        from .providers.flow_browser import FlowBrowser
        url = FlowBrowser.normalize_project_url((settings or {}).get("flow_project_url", ""))
        if url:
            return url
        row = self.db.get(job_id) or {}
        return FlowBrowser.normalize_project_url(row.get("flow_project", ""))

    def _remember_flow_project_url(self, job_id: str, url: str | None) -> str:
        """Persist Flow's /project/<uuid> URL for deterministic resume/recovery."""
        from .providers.flow_browser import FlowBrowser
        url = FlowBrowser.normalize_project_url(url)
        if not url:
            return ""
        row = self.db.get(job_id) or {}
        if row.get("flow_project") != url:
            self.db.upsert(job_id, flow_project=url)
            self.pm.log(job_id, "flow_project_bound", {"url": url})
            print(f"[Flow] Bound AutoVideoAI job to Flow project: {url}")
        # Keep the per-job settings portable as well as the SQLite binding.
        try:
            sp = os.path.join(self.pm.job_dir(job_id), "settings.json")
            cfg = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
            if cfg.get("flow_project_url") != url:
                cfg["flow_project_url"] = url
                _save_json(sp, cfg)
        except Exception:
            pass
        return url

    def pause_state(self, job_id: str) -> dict:
        """Return durable user guidance for a paused/assisted job."""
        path = os.path.join(self.pm.job_dir(job_id), "pause_state.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_pause_state(self, job_id: str, shot_id: str, reason: str,
                           kind: str = "flow_recovery",
                           project_url: str = "",
                           baseline_signatures=None) -> dict:
        """Persist exactly what stopped and the safest next actions."""
        import datetime
        try:
            m = self.pm.load_manifest(job_id)
            accepted, total = m.accepted_count(), len(m.shots)
        except Exception:
            accepted, total = 0, 0
        project_url = project_url or self._flow_project_url(job_id)
        baseline = sorted({str(x) for x in (baseline_signatures or []) if str(x)})
        recover = (f"python3 cli.py v3 recover-flow-video {job_id} "
                   f"--shot-id {shot_id} --wait-seconds 120")
        resume_action = {"label": "Resume the saved job after recovery/limit reset",
                         "command": f"python3 cli.py v3 resume {job_id}"}
        actions = [resume_action]
        if baseline:
            actions.insert(0, {"label": "Recover a new existing Flow video (no new credits)",
                               "command": recover})
        state = {
            "paused_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "kind": kind,
            "job_id": job_id,
            "shot_id": shot_id,
            "reason": str(reason),
            "flow_project_url": project_url,
            "accepted_shots": accepted,
            "total_shots": total,
            "safe_to_resume": True,
            "baseline_signatures": baseline,
            "safe_automatic_recovery": bool(baseline),
            "actions": actions,
        }
        _save_json(os.path.join(self.pm.job_dir(job_id), "pause_state.json"), state)
        self.pm.log(job_id, "job_paused", state)
        from .support_report import redact
        print(f"[PAUSED] {job_id}/{shot_id} ({kind}): {redact(str(reason))}")
        print(f"[PAUSED] Saved details: {os.path.join(self.pm.job_dir(job_id), 'pause_state.json')}. "
              f"Export diagnostics offline: python3 cli.py v3 support-report {job_id}")
        return state

    def import_content_plan(self, job_id, plan):
        from .content_plan import validate_plan, script_from_plan, plan_fingerprint
        from .production import save
        plan = validate_plan(plan)
        m = self.pm.load_manifest(job_id)
        if m.shots:
            raise ValueError('Do not replace an approved script after scene planning/generation; create a separate job')
        if plan['language'] != m.language:
            raise ValueError('Approved plan language does not match the job')
        root = self.pm.job_dir(job_id)
        save(os.path.join(root,'approved_content_plan.json'), plan)
        save(os.path.join(root,'script.json'), script_from_plan(plan))
        settings = json.load(open(os.path.join(root,'settings.json'),encoding='utf-8'))
        settings.update(auto_retime_script=False, imported_plan_sha256=plan_fingerprint(plan))
        save(os.path.join(root,'settings.json'), settings)
        m.status = 'scripted';self.pm.save_manifest(m)
        self.db.upsert(job_id,status='scripted',script_status='imported')
        return {'job_id':job_id,'script_source':'approved-import','new_generations':0}

    def set_presentation_options(self, job_id: str, **updates) -> dict:
        """Local editing only: keep takes, scene timings, project bindings and journals."""
        unknown = set(updates) - PRESENTATION_KEYS
        if unknown:
            raise ValueError("Unknown presentation option(s): " + ", ".join(sorted(unknown)))
        m = self.pm.load_manifest(job_id)
        merged = {**self._settings(job_id), **updates}
        resolve_presentation(merged)  # Validate every option before changing files.
        path = os.path.join(self.pm.job_dir(job_id), "settings.json")
        saved = json.load(open(path, encoding="utf-8"))
        saved.update(updates)
        from .production import save
        save(path, saved)
        m.voiceover_enabled = resolve_presentation(merged).voiceover
        self.pm.save_manifest(m)
        save(os.path.join(self.pm.job_dir(job_id), "production", "review.json"),
             {"status": "STALE_AFTER_PRESENTATION_CHANGE", "next_action": "Render the same accepted takes, then review"})
        self.pm.log(job_id, "presentation_changed", {"options": updates, "new_visual_generations": 0})
        return updates

    # ---------------- main run (resumable) ----------------
    def set_gemini_cleanup(self, job_id, policy):
        if policy not in ("keep", "delete-after-read"):
            raise ValueError("Invalid Gemini cleanup policy")
        self.pm.load_manifest(job_id)  # Never create settings for a nonexistent job.
        path = os.path.join(self.pm.job_dir(job_id), "settings.json")
        with open(path, encoding="utf-8") as handle:
            settings = json.load(handle)
        settings["gemini_chat_cleanup"] = policy
        _save_json(path, settings)
        return policy

    def run_job(self, job_id: str, progress_cb=None, auto_render: bool = True) -> dict:
        from .progress import JobProgress
        progress = JobProgress(self.pm.job_dir(job_id), progress_cb)
        def prog(stage, pct, info=""):
            try:
                progress.emit(stage, pct, info)
            except Exception:
                pass

        m = self.pm.load_manifest(job_id)
        D = self.pm.dirs(job_id)
        settings = self._settings(job_id)
        from .clip_recreation import require_recreation_approval
        require_recreation_approval(D['root'])
        presentation = resolve_presentation(settings)
        m.voiceover_enabled = presentation.voiceover
        os.environ["AUTOVIDEO_GEMINI_CHAT_CLEANUP"] = str(
            settings.get("gemini_chat_cleanup", "keep") or "keep")
        prog("Gemini temporary-chat policy", 1, os.environ["AUTOVIDEO_GEMINI_CHAT_CLEANUP"])
        os.environ["AUTOVIDEO_STOCK_SOURCE"] = str(settings.get("stock_source", "auto") or "auto")
        self._check_storage(D["root"], prog)
        router = CreditRouter(m.profile, overrides=settings.get("budgets"))
        preset = load_preset(m.preset)
        # Optional visual-density override. Long videos normally work well around
        # 6-9 seconds per visual beat; this controls the maximum without changing
        # narration duration.
        if settings.get("shot_max_seconds"):
            preset = dict(preset)
            sl = list(preset.get("shot_length", [4, 8]))
            mx = max(2.0, float(settings["shot_max_seconds"]))
            preset["shot_length"] = [min(float(sl[0]), mx), mx]
        dry = m.dry_run
        refs = ReferenceManager(D["references"])

        # ---- 1. script ----
        script_path = os.path.join(D["root"], "script.json")
        if m.status in ("created",) or not os.path.exists(script_path):
            prog("✍️ Director: planning content...", 5)
            plan = plan_content(
                m.topic, m.content_type, m.target_seconds, m.tone, m.language,
                script_provider=settings.get("script_provider", "auto"),
                script_model=settings.get("script_model", "auto"),
                script_quality=settings.get("script_quality", "publish"),
            )
            from .planning.script_engine import script_quality_report
            editorial_qc = plan.get("editorial_qc") or script_quality_report(
                plan, m.topic, m.content_type, m.target_seconds)
            plan["editorial_qc"] = editorial_qc
            _save_json(os.path.join(D["root"], "editorial_qc.json"), editorial_qc)
            if str(settings.get("script_quality", "publish")).lower() == "publish" and not editorial_qc.get("passed"):
                raise RuntimeError(
                    "Script failed publish-quality editorial QC before media generation: "
                    + "; ".join(editorial_qc.get("flags") or [])
                )
            _save_json(script_path, plan)
            self._write_script_md(m, plan, os.path.join(D["root"], "script.md"))
            prog(f"✍️ Script ready: {plan.get('words', 0)} words for {m.target_seconds}s target "
                 f"via {plan.get('source', 'planner')}", 7)
            m.angle, m.audience = plan["angle"], plan["audience"]
            m.status = "scripted"
            self.pm.save_manifest(m)
            self.db.upsert(job_id, status="scripted", script_status="done")
        else:
            plan = json.load(open(script_path, encoding="utf-8"))

        # Gemini Web intentionally shares one sync-Playwright browser across the
        # multi-step writing pass.  Once the script is complete, release that
        # Playwright driver before TTS or Flow starts.  Keeping it alive in the
        # same Python process can make Edge TTS see an active asyncio loop and can
        # make a second sync-Playwright instance (Flow) fail immediately.  The
        # Gemini login itself remains persisted on disk and is reused next time.
        if str(plan.get("source", "")).lower().startswith("gemini-web") or \
                str(settings.get("script_provider", "")).lower() == "gemini-web":
            try:
                from .providers.gemini_web import close_shared_session
                close_shared_session()
                prog("🌐 Gemini writing session released; continuing with a clean TTS/Flow browser context.", 8)
            except Exception:
                pass

        # ---- 2. narration ----
        voice_path = os.path.join(D["narration"], "voice.mp3")
        words_path = voice_path + ".words.json"
        if not presentation.voiceover:
            # Do not synthesize a voice then mute it. No TTS, transcription,
            # retiming, dummy MP3 or fabricated caption timestamps are needed.
            words = []
            narration_dur = visual_duration(m)
            if not m.shots:
                m.timing_source = "visual_storyboard"
                m.status = "narrated"  # Existing stage order; voice itself is skipped.
                self.pm.save_manifest(m)
            prog("🎵 Voiceover disabled — visual story clock", 14, f"{narration_dur:.1f}s; TTS and speech captions skipped")
            self.pm.log(job_id, "voiceover_skipped", {"duration": narration_dur, "timing_source": "visual_storyboard"})
        elif m.status in ("created", "scripted") or not os.path.exists(voice_path):
            prog("🎙️ Narrating...", 12)

            def _synth(current_plan):
                if settings.get('narration_input_path'):
                    from .audio.tts import _audio_to_mp3, _mp3_len
                    local_audio = os.path.abspath(os.path.expanduser(settings['narration_input_path']))
                    if not os.path.isfile(local_audio):
                        raise ValueError('Imported narration file not found')
                    _audio_to_mp3(local_audio, voice_path)
                    return {'audio':voice_path,'words':[],'duration':_mp3_len(voice_path),'engine':'imported-native-narration'}
                return synthesize_narration(
                    current_plan["narration"], m.voice, voice_path,
                    provider=settings.get("tts_provider", "auto"),
                    language=m.language,
                    style=settings.get("tts_style", ""),
                    model=settings.get("tts_model", ""),
                    provider_voice=settings.get("tts_voice", ""),
                )

            tts = None
            # A caption/transcription failure can happen after a perfectly good
            # narration file was already written. On resume, do not spend another
            # TTS request (or change the voice) just because manifest status never
            # advanced past ``scripted``. Reuse the audio checkpoint and retry the
            # caption-timing stage only.
            if m.status == "scripted" and os.path.exists(voice_path):
                try:
                    from .audio.tts import _mp3_len
                    checkpoint_dur = float(_mp3_len(voice_path) or 0)
                    if os.path.getsize(voice_path) >= 1024 and checkpoint_dur > 0:
                        tts = {"audio": voice_path, "words": [],
                               "duration": checkpoint_dur, "engine": "existing-narration-checkpoint"}
                        prog(f"♻️ Reusing existing narration checkpoint: {checkpoint_dur:.1f}s", 12)
                except Exception:
                    tts = None

            if tts is None:
                try:
                    tts = _synth(plan)
                except Exception as e:
                    if dry:
                        prog(f"TTS offline ({str(e)[:60]}), using mock narration for dry run...", 12)
                        tts = synthesize_narration(plan["narration"], m.voice, voice_path,
                                                   provider="mock", language=m.language)
                    else:
                        raise RuntimeError(f"Narration failed: {e}")

            prog(f"🎙️ Voice ready via {tts.get('engine', settings.get('tts_provider', 'auto'))}: "
                 f"{float(tts.get('duration') or 0):.1f}s", 12)

            # v5.5.3: measured speech duration is the source of truth.
            # Retiming is now bidirectional: short narration is expanded and
            # overlong narration is shortened before media generation.
            if not dry and bool(settings.get("auto_retime_script", True)):
                from .planning.script_engine import retime_script_plan
                for _retime_round in range(2):
                    measured = float(tts.get("duration") or 0)
                    if measured <= 0:
                        break
                    ratio_to_target = measured / max(float(m.target_seconds), 0.1)
                    if 0.92 <= ratio_to_target <= 1.11:
                        break

                    current_words = int(plan.get("words") or len(plan["narration"].split()))
                    target_words = max(45, int(round(
                        current_words * (float(m.target_seconds) / measured) * 0.99
                    )))
                    if measured > m.target_seconds:
                        prog(
                            f"✂️ Narration measured {measured:.1f}s; rewriting script to ~{target_words} words "
                            "instead of over-speeding it...", 12
                        )
                    else:
                        prog(
                            f"➕ Narration measured only {measured:.1f}s; expanding script to ~{target_words} words "
                            "to reach the requested runtime...", 12
                        )

                    retimed = retime_script_plan(
                        plan, m.topic, m.content_type, m.target_seconds, m.tone, m.language,
                        target_words=target_words,
                        provider=settings.get("script_provider", "auto"),
                        model=settings.get("script_model", "auto"),
                    )
                    try:
                        from .providers.gemini_web import close_shared_session
                        close_shared_session()
                    except Exception:
                        pass
                    if not retimed or retimed.get("narration") == plan.get("narration"):
                        break

                    from .planning.script_engine import script_quality_report
                    retime_qc = retimed.get("editorial_qc") or script_quality_report(
                        retimed, m.topic, m.content_type, m.target_seconds, target_words)
                    retimed["editorial_qc"] = retime_qc
                    if str(settings.get("script_quality", "publish")).lower() == "publish" and not retime_qc.get("passed"):
                        raise RuntimeError(
                            "Retimed script failed publish-quality editorial QC before media generation: "
                            + "; ".join(retime_qc.get("flags") or [])
                        )
                    plan = retimed
                    _save_json(os.path.join(D["root"], "editorial_qc.json"), retime_qc)
                    _save_json(script_path, plan)
                    self._write_script_md(m, plan, os.path.join(D["root"], "script.md"))
                    try:
                        os.remove(voice_path)
                    except Exception:
                        pass
                    for suffix in (".words.json", ".words.meta.json"):
                        try:
                            os.remove(voice_path + suffix)
                        except Exception:
                            pass
                    tts = _synth(plan)
                    prog(
                        f"✍️ Retimed script: {plan.get('words', 0)} words; narration "
                        f"{float(tts.get('duration') or 0):.1f}s", 13
                    )

            # Use native TTS boundaries when present, otherwise Groq/local Whisper
            # only for timing. In both cases align visible caption wording back to
            # the exact authored script.
            from .captions import get_word_timestamps, align_words_to_script
            words = list(tts.get("words") or [])
            if words and bool(settings.get("caption_align_script", True)):
                words = align_words_to_script(plan["narration"], words, float(tts.get("duration") or 0))
            if not words:
                words = get_word_timestamps(
                    voice_path,
                    model_size=str(settings.get("caption_local_model", "small") or "small"),
                    provider=str(settings.get("caption_provider", "auto") or "auto"),
                    script_text=plan["narration"], language=m.language,
                    groq_model=str(settings.get("caption_model", "whisper-large-v3-turbo") or "whisper-large-v3-turbo"),
                    align_script=bool(settings.get("caption_align_script", True)),
                    force=True,
                ) or []

            if tts.get("engine") != "mock-silent":
                words_f, dur_f = fit_narration_to_target(
                    voice_path, words, m.target_seconds,
                    max_rate=float(settings.get("max_tts_speedup", 1.08) or 1.08),
                    hard_trim=False,
                )
                if dur_f and abs(dur_f - float(tts.get("duration") or 0)) > 0.3:
                    prog(f"⏱️ Gentle pacing correction {tts.get('duration', 0):.1f}s → {dur_f:.1f}s "
                         f"(target {m.target_seconds}s; max speedup {float(settings.get('max_tts_speedup', 1.08)):.2f}x)", 13)
                tts["words"], tts["duration"] = words_f, dur_f
                words = words_f
            narration_dur = float(tts.get("duration") or 0)
            if narration_dur <= 0 or not words:
                raise RuntimeError("Narration produced no usable audio/timings - aborting before spending anything.")
            # Persist authoritative caption timings after any final atempo change.
            _save_json(words_path, words)
            if narration_dur > m.target_seconds * 1.12:
                prog(f"⚠️ Narration is {narration_dur:.1f}s vs {m.target_seconds}s target; v5 keeps natural speech rather than hard-trimming audio.", 14)
            if m.target_seconds >= 120 and narration_dur < m.target_seconds * 0.75:
                raise RuntimeError(
                    f"Narration is only {narration_dur:.1f}s for a {m.target_seconds}s target. "
                    "Aborting before image/video generation."
                )
            if m.target_seconds >= 120 and narration_dur < m.target_seconds * 0.90:
                prog(f"⚠️ Narration is {narration_dur:.1f}s vs {m.target_seconds}s target; continuing but final runtime will be shorter.", 14)
            m.status = "narrated"
            self.pm.save_manifest(m)
            self.pm.log(job_id, "narrated", {"engine": tts["engine"], "duration": round(narration_dur, 1),
                                             "words": len(words), "script_source": plan.get("source")})
        else:
            words = json.load(open(words_path, encoding="utf-8")) if os.path.exists(words_path) else []
            from moviepy.editor import AudioFileClip
            c = AudioFileClip(voice_path)
            narration_dur = c.duration
            c.close()

        # ---- 3. bible + director ----
        if m.status in ("created", "scripted", "narrated") or not m.shots:
            prog("📖 Building story bible + shot plan...", 18)
            bible = build_bible(m.topic, m.content_type, preset, m.audience, m.tone)
            character_file = os.path.join(D['root'], 'character_snapshot.json')
            if os.path.isfile(character_file):
                character = json.load(open(character_file,encoding='utf-8'))
                bible['characters'] = [{'id':'CHARACTER_01','canonical':character['canonical'],'name':character['name']}]
                from .planning.story_bible import _identity_block
                bible['identity_block'] = _identity_block(bible['characters'], bible.get('locations',[]), bible.get('objects',[]))
                for i, reference in enumerate(character.get('references', [])):
                    if self._file_sha256(reference['path']) != reference['sha256']:
                        raise ValueError('Character reference changed; no new generation submitted')
                    copied = os.path.join(D['references'], f'character-approved-{i}.png')
                    if not os.path.isfile(copied):
                        refs.add('character', reference['path'], f'character-approved-{i}.png')
            _save_json(os.path.join(D["root"], "story_bible.json"), bible)
            m = create_production_plan(m, plan["narration"], words, plan["beats"],
                                       bible, preset, router, narration_dur,
                                       timing_source="narration" if presentation.voiceover else "visual_storyboard")
            self.pm.save_manifest(m)
            self.db.upsert(job_id, status="planned")
            self.pm.log(job_id, "planned", {"shots": len(m.shots)})

        bible = json.load(open(os.path.join(D["root"], "story_bible.json"), encoding="utf-8"))

        # ---- 3a. MovieFlow full-story cartoon mode ----
        movieflow_full = self._movieflow_full_story_enabled(m, settings)
        if movieflow_full:
            if not (len(m.shots) == 1 and getattr(m.shots[0], "provider", "") == "movieflow"):
                m = self._prepare_movieflow_full_story(m, plan, bible, preset, narration_dur)
                self.pm.save_manifest(m)
                self.pm.log(job_id, "movieflow_full_story_planned",
                            {"project_url": settings.get("movieflow_project_url", ""),
                             "runtime": round(float(narration_dur), 1)})
            prog("🎨 MovieFlow cartoon: full-story Agent generation selected; Google Flow scene generation is bypassed.", 20)

        # ---- 3b. storyboard-economy media routing (zero spend) ----
        if m.profile == "STORYBOARD_ECONOMY" and not movieflow_full:
            econ_path = os.path.join(D["root"], "economy_plan.json")
            if not os.path.exists(econ_path):
                from .planning.economy_storyboard import EconomyOptions, assign_storyboard_economy
                # Only reserve stock slots when a real stock source is available.
                # v4.0 could report "2 stock" even when no local library/API existed,
                # then silently route those scenes to image-motion at runtime.
                try:
                    from .providers.stock_provider import StockProvider
                    stock_available = StockProvider().status().available
                except Exception:
                    stock_available = False
                # Long-form default mix: 60% meaningful stock video, 20% Flow
                # hero/action video and 20% locally animated stills. Explicit
                # CLI/YAML scene counts always win and the credit budget may cap
                # Flow below its requested share.
                if str(settings.get("production_mode", "legacy")).lower() == "youtube_pro":
                    target_dynamic = settings.get("dynamic_video_scenes")
                    if target_dynamic is None:
                        target_dynamic = max(1, int(round(len(m.shots) * 0.80)))
                    if settings.get("flow_scenes") is None:
                        settings["flow_scenes"] = max(1, int(round(len(m.shots) * 0.20)))
                    if settings.get("stock_scenes") is None:
                        settings["stock_scenes"] = max(0, min(
                            len(m.shots) - int(settings.get("flow_scenes") or 0),
                            int(round(len(m.shots) * 0.60))))
                    settings["dynamic_video_scenes"] = int(target_dynamic)
                os.environ["AUTOVIDEO_STOCK_SOURCE"] = str(settings.get("stock_source", "auto") or "auto")

                opts = EconomyOptions(
                    max_credits=float(settings.get("budgets", {}).get("MAX_CREDITS_PER_VIDEO", 50)),
                    video_share=float(settings.get("video_share", 0.20) or 0),
                    stock_share=float(settings.get("stock_share", 0.60) or 0),
                    flow_scenes=settings.get("flow_scenes"),
                    max_flow_scenes=settings.get("max_flow_scenes"),
                    stock_scenes=settings.get("stock_scenes"),
                    dynamic_video_scenes=settings.get("dynamic_video_scenes"),
                    prefer_stock=bool(stock_available),
                    reserve_pct=float(router.budgets.get("RETRY_RESERVE_PCT", 15) or 0),
                )
                report = assign_storyboard_economy(m, router, opts)
                self.pm.save_manifest(m)
                _save_json(econ_path, report)
                self._write_economy_plan_md(m, report, os.path.join(D["root"], "economy_plan.md"))
                self.pm.log(job_id, "economy_routed", {k: report[k] for k in
                            ("flow_scenes", "stock_scenes", "image_scenes", "projected_total")})
            else:
                # Manifest already contains the persisted routing from the first run.
                try:
                    report = json.load(open(econ_path, encoding="utf-8"))
                except Exception:
                    report = {}
            # Cartoon scenes mode reuses the economy planner only to select how
            # many motion-critical shots deserve AI video, then hands those shots
            # to MovieFlow instead of Google Flow. Opening/closing stills can still
            # come from the normal frame pipeline.
            if (str(settings.get("cartoon_provider", "flow")).lower() == "movieflow"
                    and str(settings.get("movieflow_mode", "full_story")).lower() == "scenes"):
                changed = 0
                for _s in m.shots:
                    if getattr(_s, "provider", "") == "flow":
                        _s.provider = "movieflow"
                        _s.model = "movieflow_scene"
                        _s.media_strategy = "movieflow_video"
                        changed += 1
                if changed:
                    self.pm.save_manifest(m)
                    self.pm.log(job_id, "movieflow_scene_routing", {"shots": changed})
                    report["movieflow_scenes"] = changed
                    report["flow_scenes"] = 0
                    _save_json(econ_path, report)
            flow_note = ""
            if report.get("requested_flow_scenes") is not None:
                flow_note = f" (requested {report.get('requested_flow_scenes')})"
            elif settings.get("max_flow_scenes") is not None:
                flow_note = f" (max cap {settings.get('max_flow_scenes')})"
            if report.get("budget_limited"):
                flow_note += " [budget-limited]"
            _mf_scenes = int(report.get("movieflow_scenes", 0) or 0)
            _motion_count = _mf_scenes if _mf_scenes else int(report.get("flow_scenes", 0) or 0)
            _motion_name = "MovieFlow video" if _mf_scenes else "AI video"
            prog(f"🧠 Economy storyboard: {_motion_count} {_motion_name}{flow_note} / "
                 f"{report.get('stock_scenes',0)} stock / {report.get('image_scenes',0)} image-motion; "
                 f"~{report.get('projected_total',0)} credits", 21)

        # ---- 4. storyboard frames + compiled prompts ----
        prog("🖼️ Storyboard frames...", 24)
        from .providers.image_provider import ImageProvider
        img_prov = ImageProvider()
        vertical = m.aspect == "9:16"
        strict_flow_storyboard = bool(
            m.profile == "STORYBOARD_ECONOMY"
            and str(settings.get("frame_source", "auto") or "auto").lower() == "flow"
            and not movieflow_full
        )
        if strict_flow_storyboard:
            # These preview JPEGs used Pollinations before the real Flow-frame pass.
            # On long-form jobs that meant dozens of 90-second HTTP waits before
            # the first visible per-shot progress line.  They are redundant when
            # strict Flow is already responsible for the actual opening/closing
            # frames, so compile prompts now without generating network previews.
            prog("⏭️ Strict Flow frame mode: skipping Pollinations storyboard previews; Flow frames will be generated next.", 24)
        for s in m.shots:
            if movieflow_full:
                # MovieFlow full-story mode needs only the story/character bible;
                # do not spend time creating Google Flow/local storyboard frames.
                continue
            frame = os.path.join(D["storyboard"], f"{s.shot_id}.jpg")
            if not os.path.exists(frame) and not dry and not strict_flow_storyboard:
                try:
                    img_prov.storyboard_frame(
                        f"{s.subject}, {s.environment}, {s.camera_framing}, {preset.get('color_treatment','')}, no text",
                        frame, vertical)
                    refs.add("storyboard", frame, f"{s.shot_id}.jpg")
                except Exception as e:
                    self.pm.log(job_id, "storyboard_failed", {"shot": s.shot_id, "error": str(e)[:150]})
            # resolve continuity placeholder
            if s.start_frame and s.start_frame.startswith("{prev_end_frame:"):
                prev = s.start_frame[16:-1]
                cand = os.path.join(D["references"], f"{prev}_end.jpg")
                s.start_frame = cand if os.path.exists(cand) else None
            if not s.compiled_prompt:
                c = compile_shot(s, bible, preset, vertical)
                s.compiled_prompt = c["prompt"]
                approved_scenes = plan.get('beats', [])
                if plan.get('source') == 'approved-import' and approved_scenes:
                    scene = approved_scenes[min(len(approved_scenes)-1,int(m.shots.index(s)*len(approved_scenes)/len(m.shots)))]
                    if scene.get('motion_prompt'):
                        s.compiled_prompt += ' Authored motion direction: ' + str(scene['motion_prompt'])
        self.pm.save_manifest(m)

        # ---- 5. budget gate (Flow profiles) ----
        K = int(settings.get("images_per_shot", 2) or 0)
        est = router.estimate_job(m.shots)
        img_unit = float(router.reg["models"].get("imagen_flow", {}).get("credits_per_image", 0))
        est["image_credits"] = round(img_unit * K * len(m.shots), 1)
        est["projected_total"] = round(est["projected_total"] + est["image_credits"], 1)
        est["within_budget"] = est["projected_total"] <= float(est["max_per_video"])
        _save_json(os.path.join(D["root"], "budget.json"), est)
        self.db.upsert(job_id, est_credits=int(est["projected_total"]))
        if m.profile in ("FLOW_CINEMATIC", "FLOW_BALANCED", "FLOW_ECONOMY", "STORYBOARD_ECONOMY", "MANUAL_DIRECTOR") and not dry:
            if not est["within_budget"]:
                m.status = "paused"
                self.pm.save_manifest(m)
                self.db.upsert(job_id, status="paused")
                raise NeedsDecision(
                    f"Projected {est['projected_total']} Flow credits exceeds budget "
                    f"{est['max_per_video']}. Job paused before spending anything.",
                    alternatives=["Raise MAX_CREDITS_PER_VIDEO in SETTINGS and resume",
                                  "Switch profile to FLOW_ECONOMY", "Run as DRY RUN first"])
        prog(f"💳 Budget: ~{est['projected_total']} credits" + (" (DRY RUN - spending nothing)" if dry else ""), 28)

        # ---- 5b. scene images (Flow image gen; free fallback) ----
        # Multiple stills per scene -> best becomes the video reference (reference-first).
        # Runs only after the budget gate passes (never spends before approval).
        needs_approval = (m.profile == "MANUAL_DIRECTOR"
                          and any(s.status == "planned" for s in m.shots))
        if not dry and m.profile == "STORYBOARD_ECONOMY" and not needs_approval and not movieflow_full:
            try:
                self._generate_economy_frames(m, D, refs, vertical, settings, bible, prog)
            except RuntimeError as e:
                # Strict Flow-frame jobs are intentionally resumable. Keep every
                # completed/downloaded frame and return a clean PAUSED result instead
                # of ending with a raw traceback after a network/UI interruption.
                msg = str(e)
                if "Strict --frame-source flow" in msg:
                    m2 = self.pm.load_manifest(job_id)
                    m2.status = "paused"
                    self.pm.save_manifest(m2)
                    self.db.upsert(job_id, status="paused")
                    self.pm.log(job_id, "flow_frames_paused", {"error": msg[:1200]})
                    prog("⏸️ Flow frame generation paused; completed frames are cached.", 26)
                    return {
                        "job_id": job_id, "status": "paused",
                        "message": msg,
                        "resume": f"python3 cli.py v3 resume {job_id}",
                    }
                raise
            m = self.pm.load_manifest(job_id)
        elif K > 0 and not dry and m.profile in FLOW_PROFILES and not needs_approval and not movieflow_full:
            self._generate_scene_images(m, D, refs, vertical, K, prog, settings=settings)
            m = self.pm.load_manifest(job_id)

        # ---- 6. generation loop ----
        if m.profile == "MANUAL_DIRECTOR" and any(s.status == "planned" for s in m.shots):
            m.status = "review"
            self.pm.save_manifest(m)
            self.db.upsert(job_id, status="review")
            return {"job_id": job_id, "status": "review",
                    "message": "MANUAL_DIRECTOR: approve shots in STORYBOARD, then resume."}

        self._generate_all(m, D, refs, router, vertical, dry, prog, settings)

        if dry:
            self.db.upsert(job_id, status="dry_complete")
            return {"job_id": job_id, "status": "dry_complete", "est": est,
                    "message": "DRY RUN complete - no credits spent and no media generated. Planning/audit files were written for review."}

        # ---- 7. review gate ----
        m = self.pm.load_manifest(job_id)
        if m.status == "review":
            return {"job_id": job_id, "status": "review", "message": "Awaiting director approval."}

        # ---- 8. render ----
        if auto_render:
            return self.render_job(job_id, quality=str(settings.get("render_quality", "high") or "high"), progress_cb=progress_cb)
        return {"job_id": job_id, "status": m.status}

    # ---------------- script markdown / Flow project frame cache ----------------
    @staticmethod
    def _norm_prompt_key(text: str) -> str:
        return " ".join(str(text or "").split()).strip().lower()

    @staticmethod
    def _file_sha256(path: str) -> str:
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    @staticmethod
    def _is_valid_image_file(path: str, min_bytes: int = 128) -> bool:
        """Return True only for a decodable raster image with useful dimensions.

        A nearly-full disk or a Flow/download interruption can leave a .jpg path
        behind that is zero-byte, HTML, or a truncated JPEG.  Older releases
        treated mere path existence as success and later crashed in Pillow during
        image-motion rendering.  Validate bytes before caching/reusing a frame.
        """
        try:
            if not path or not os.path.isfile(path) or os.path.getsize(path) < min_bytes:
                return False
            from PIL import Image
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                w, h = im.size
                return w >= 64 and h >= 64
        except Exception:
            return False

    @classmethod
    def _remove_invalid_image(cls, path: str) -> bool:
        """Delete a corrupt/incomplete image file if present; return True if removed."""
        try:
            if path and os.path.exists(path) and not cls._is_valid_image_file(path):
                os.remove(path)
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _check_storage(path: str, prog=None) -> None:
        """Fail early before media generation when the target drive is critically full.

        AutoVideoAI writes intermediate JPEG/MP4 files next to the job. A nearly
        full drive can leave truncated files that look cached but are undecodable.
        The thresholds are configurable for small systems.
        """
        try:
            free = shutil.disk_usage(os.path.abspath(path)).free
            free_gb = free / (1024 ** 3)
            minimum = float(os.environ.get("AUTOVIDEO_MIN_FREE_GB", "1.5"))
            warning = float(os.environ.get("AUTOVIDEO_WARN_FREE_GB", "5.0"))
            if free_gb < minimum:
                raise RuntimeError(
                    f"Insufficient free disk space on the output drive: {free_gb:.2f} GB available; "
                    f"at least {minimum:.1f} GB is required. Free space, then resume the same job.")
            if free_gb < warning and prog:
                prog(f"⚠️ Low disk space: {free_gb:.1f} GB free on output drive; media writes are protected but cleanup is recommended.", 4)
        except RuntimeError:
            raise
        except Exception:
            # Disk probing should never block production on exotic filesystems.
            return

    @staticmethod
    def _image_dhash(path: str) -> int | None:
        """Small perceptual hash used only to detect near-duplicate storyboard frames."""
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

    @classmethod
    def _image_distance(cls, a: str, b: str) -> int | None:
        ha, hb = cls._image_dhash(a), cls._image_dhash(b)
        if ha is None or hb is None:
            return None
        return (ha ^ hb).bit_count()

    def _flow_frame_cache_key(self, project_url: str, prompt: str, vertical: bool, label: str) -> str:
        payload = "|".join([project_url.strip(), "9:16" if vertical else "16:9",
                            str(label or "frame").strip().lower(), self._norm_prompt_key(prompt)])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _flow_frame_cache_dir(self, project_url: str) -> str:
        """Project cache shared across AutoVideoAI versions/install folders.

        v4.8 and older stored the cache under each source tree's ``data/`` folder,
        so extracting a new release made an existing Flow project look empty and
        caused the same images to be generated again.  v4.9 moves the canonical
        cache to the user's home directory and imports sibling legacy caches.
        """
        from .providers.flow_browser import FlowBrowser
        url = FlowBrowser.normalize_project_url(project_url)
        ident = url.rsplit("/", 1)[-1] if url else "unbound"
        base = os.environ.get("AUTOVIDEO_FLOW_CACHE_DIR") or os.path.join(
            os.path.expanduser("~"), ".local", "share", "autovideoai", "flow_project_cache")
        root = os.path.abspath(os.path.join(base, ident, "frames"))
        os.makedirs(root, exist_ok=True)
        self._import_legacy_flow_cache(ident, root)
        return root

    def _import_legacy_flow_cache(self, project_id: str, target: str) -> int:
        """Import per-release v4.x project caches into the shared v4.9 cache."""
        imported = 0
        candidates = []
        here = os.path.abspath(os.getcwd())
        candidates.append(os.path.join(here, "data", "flow_project_cache", project_id, "frames"))
        parent = os.path.dirname(here)
        try:
            for name in os.listdir(parent):
                if not name.lower().startswith("autovideoai"):
                    continue
                candidates.append(os.path.join(parent, name, "data", "flow_project_cache", project_id, "frames"))
        except Exception:
            pass
        for srcdir in candidates:
            try:
                if not os.path.isdir(srcdir) or os.path.abspath(srcdir) == os.path.abspath(target):
                    continue
                for fn in os.listdir(srcdir):
                    if not (fn.endswith(".jpg") or fn.endswith(".json")):
                        continue
                    src = os.path.join(srcdir, fn)
                    dst = os.path.join(target, fn)
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                        imported += 1
            except Exception:
                continue
        return imported

    def _external_project_jobs(self, project_url: str, topic: str = "", aspect: str = "",
                               reuse_mode: str = "topic") -> list[tuple[str, dict, dict]]:
        """Find prior jobs in this and sibling AutoVideoAI release folders.

        Returns ``(job_root, manifest_json, settings_json)`` newest-first.  This is
        intentionally file-based so project reuse survives extracting v4.9 into a
        brand-new source directory.
        """
        from .providers.flow_browser import FlowBrowser
        wanted = FlowBrowser.normalize_project_url(project_url)
        mode = str(reuse_mode or "topic").lower()
        if not wanted or mode == "exact":
            return []
        roots = [os.path.abspath(os.getcwd())]
        parent = os.path.dirname(os.path.abspath(os.getcwd()))
        try:
            roots += [os.path.join(parent, n) for n in os.listdir(parent)
                      if n.lower().startswith("autovideoai")]
        except Exception:
            pass
        seen = set()
        found = []
        wanted_topic = self._norm_prompt_key(topic)
        for root in roots:
            outroot = os.path.join(root, "outputs")
            if not os.path.isdir(outroot):
                continue
            try:
                jobids = sorted(os.listdir(outroot), reverse=True)
            except Exception:
                continue
            for jobid in jobids:
                jobroot = os.path.join(outroot, jobid)
                mp = os.path.join(jobroot, "production_manifest.json")
                sp = os.path.join(jobroot, "settings.json")
                if not os.path.isfile(mp):
                    continue
                key = os.path.realpath(jobroot)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    manifest = json.load(open(mp, encoding="utf-8"))
                    settings = json.load(open(sp, encoding="utf-8")) if os.path.isfile(sp) else {}
                    purl = FlowBrowser.normalize_project_url(settings.get("flow_project_url", ""))
                    if purl != wanted:
                        continue
                    if aspect and manifest.get("aspect") != aspect:
                        continue
                    if mode == "topic" and self._norm_prompt_key(manifest.get("topic", "")) != wanted_topic:
                        continue
                    found.append((jobroot, manifest, settings))
                except Exception:
                    continue
        return found

    def _previous_project_frame(self, m, project_url: str, shot_id: str, label: str,
                                reuse_mode: str) -> str | None:
        """Reuse same-topic/same-shot media from an older release folder."""
        role = str(label or "").lower()
        for jobroot, manifest, _ in self._external_project_jobs(
                project_url, topic=m.topic, aspect=m.aspect, reuse_mode=reuse_mode):
            if manifest.get("job_id") == m.job_id:
                continue
            if role == "location master":
                cand = os.path.join(jobroot, "storyboard", "location_master.jpg")
            elif role == "character master":
                cand = os.path.join(jobroot, "storyboard", "character_master.jpg")
            elif role == "opening frame":
                cand = os.path.join(jobroot, "storyboard", f"{shot_id}_open.jpg")
            elif role == "closing frame":
                cand = os.path.join(jobroot, "storyboard", f"{shot_id}_close.jpg")
            else:
                continue
            try:
                if not self._is_valid_image_file(cand):
                    continue
                # Never resurrect an older poisoned identical closing frame.
                if role == "closing frame":
                    op = os.path.join(jobroot, "storyboard", f"{shot_id}_open.jpg")
                    if os.path.isfile(op) and self._file_sha256(op) == self._file_sha256(cand):
                        continue
                return cand
            except Exception:
                continue
        return None

    def _previous_project_video(self, m, project_url: str, shot_id: str,
                                reuse_mode: str) -> str | None:
        """Return a previously accepted *Flow* video for the same reusable shot."""
        for jobroot, manifest, _ in self._external_project_jobs(
                project_url, topic=m.topic, aspect=m.aspect, reuse_mode=reuse_mode):
            if manifest.get("job_id") == m.job_id:
                continue
            for s in manifest.get("shots", []) or []:
                if s.get("shot_id") != shot_id or s.get("actual_provider") != "flow":
                    continue
                cand = s.get("accepted_take") or ""
                if cand and not os.path.isabs(cand):
                    cand = os.path.join(jobroot, cand)
                if not cand or not os.path.exists(cand):
                    # Historical manifests normally store an absolute accepted path;
                    # recover the conventional location if that path moved with a folder.
                    cand = os.path.join(jobroot, "flow", "shots", shot_id, "accepted.mp4")
                    if not os.path.exists(cand):
                        cand = os.path.join(jobroot, "flow", "shots", shot_id, "take_01.mp4")
                try:
                    if os.path.isfile(cand) and os.path.getsize(cand) > 4096:
                        return cand
                except Exception:
                    continue
        return None

    def _flow_frame_cache_get(self, project_url: str, prompt: str, vertical: bool, label: str) -> str | None:
        if not project_url:
            return None
        key = self._flow_frame_cache_key(project_url, prompt, vertical, label)
        path = os.path.join(self._flow_frame_cache_dir(project_url), key + ".jpg")
        try:
            if self._is_valid_image_file(path):
                return path
            if os.path.exists(path):
                # Never keep a poisoned shared cache entry.
                try: os.remove(path)
                except Exception: pass
                meta = os.path.splitext(path)[0] + ".json"
                try:
                    if os.path.exists(meta): os.remove(meta)
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _flow_frame_cache_put(self, project_url: str, prompt: str, vertical: bool,
                              label: str, src: str, source_job: str = "") -> str | None:
        if not project_url or not src or not self._is_valid_image_file(src):
            return None
        key = self._flow_frame_cache_key(project_url, prompt, vertical, label)
        root = self._flow_frame_cache_dir(project_url)
        dst = os.path.join(root, key + ".jpg")
        try:
            shutil.copy2(src, dst)
            if not self._is_valid_image_file(dst):
                try: os.remove(dst)
                except Exception: pass
                return None
            meta = os.path.join(root, key + ".json")
            _save_json(meta, {"project_url": project_url, "label": label,
                              "prompt_sha256": hashlib.sha256(self._norm_prompt_key(prompt).encode()).hexdigest(),
                              "source_job": source_job, "source_file": os.path.abspath(src)})
            return dst
        except Exception:
            return None

    def _bootstrap_flow_frame_cache(self, m, settings: dict, bible: dict, vertical: bool) -> int:
        """Index compatible frames from older local jobs bound to the same Flow project.

        This is the safe bridge for projects created before v4.6. We do not blindly
        trust generic Flow filenames. Instead we reconstruct each old frame prompt and
        only cache it under the exact prompt/aspect/project fingerprint. A new job can
        then reuse a byte-for-byte compatible image without spending another image
        generation or depending on Flow's date/time project title.
        """
        if not bool(settings.get("flow_reuse_project_media", True)):
            return 0
        project_url = self._flow_project_url(m.job_id, settings)
        if not project_url:
            return 0
        from .planning.frame_prompts import master_character_prompt, master_location_prompt, frame_prompt
        added = 0
        for old_id in self.pm.list_jobs():
            if old_id == m.job_id:
                continue
            try:
                old_settings = self._settings(old_id)
                if self._flow_project_url(old_id, old_settings) != project_url:
                    continue
                old_m = self.pm.load_manifest(old_id)
                if old_m.aspect != m.aspect:
                    continue
                old_D = self.pm.dirs(old_id)
                bible_path = os.path.join(old_D["root"], "story_bible.json")
                if not os.path.exists(bible_path):
                    continue
                old_bible = json.load(open(bible_path, encoding="utf-8"))

                # Master references.
                for label, fn, maker, enabled in (
                    ("character master", "character_master.jpg", master_character_prompt, bool(old_bible.get("characters"))),
                    ("location master", "location_master.jpg", master_location_prompt, bool(old_bible.get("locations"))),
                ):
                    src = os.path.join(old_D["storyboard"], fn)
                    if enabled and self._is_valid_image_file(src):
                        pr = maker(old_bible, vertical)
                        if not self._flow_frame_cache_get(project_url, pr, vertical, label):
                            if self._flow_frame_cache_put(project_url, pr, vertical, label, src, old_id):
                                added += 1

                for old_s in old_m.shots:
                    old_open = os.path.join(old_D["storyboard"], old_s.shot_id + "_open.jpg")
                    old_close = os.path.join(old_D["storyboard"], old_s.shot_id + "_close.jpg")
                    poisoned_pair = (os.path.exists(old_open) and os.path.exists(old_close) and
                                     self._file_sha256(old_open) and
                                     self._file_sha256(old_open) == self._file_sha256(old_close))
                    for kind, suffix, label in (("open", "_open.jpg", "opening frame"),
                                                ("close", "_close.jpg", "closing frame")):
                        # Do not bootstrap a known-bad closing frame from older jobs
                        # where opening and closing were byte-identical.
                        if poisoned_pair and kind == "close":
                            continue
                        src = os.path.join(old_D["storyboard"], old_s.shot_id + suffix)
                        if not self._is_valid_image_file(src):
                            continue
                        pr = frame_prompt(old_s, old_bible, vertical, kind)
                        if not self._flow_frame_cache_get(project_url, pr, vertical, label):
                            if self._flow_frame_cache_put(project_url, pr, vertical, label, src, old_id):
                                added += 1
            except Exception:
                continue
        return added

    @staticmethod
    def _write_script_md(m, plan: dict, path: str):
        L = [f"# {m.topic}", "",
             f"**Job:** {m.job_id} · **Type:** {m.video_type} · **Target:** {m.target_seconds}s · **Tone:** {m.tone}",
             f"**Angle:** {plan.get('angle', '')} · **Audience:** {plan.get('audience', '')}", "",
             f"## 🎣 Hook", plan.get("hook", ""), ""]
        for i, b in enumerate(plan.get("beats", []), 1):
            L += [f"### Beat {i}: {b.get('name', '')}", b.get("text", ""), ""]
        L += ["## 🎙️ Narration", plan.get("narration", ""), "",
              f"**CTA:** {plan.get('cta', '')} · **Words:** {plan.get('words', '')} · **Source:** {plan.get('source', '')}"]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")

    @staticmethod
    def _write_economy_plan_md(m, report: dict, path: str):
        rows = report.get("shots", [])
        lines = [f"# Storyboard Economy Plan - {m.topic}", "",
                 f"**Target:** {m.target_seconds}s · **Aspect:** {m.aspect} · **Budget:** {report.get('budget', 0)} credits", "",
                 f"**Plan:** {report.get('flow_scenes',0)} AI-video · {report.get('stock_scenes',0)} stock · {report.get('image_scenes',0)} image-motion", "",
                 f"**Estimated:** {report.get('estimated_credits',0)} + {report.get('retry_reserve',0)} reserve = **{report.get('projected_total',0)} credits**", "",
                 "| Shot | Time | Strategy | Model | Est. credits | Reason |", "|---|---:|---|---|---:|---|"]
        for r in rows:
            lines.append(f"| {r['shot_id']} | {r['start']:.1f}-{r['end']:.1f}s | {r['strategy']} | {r['model']} | {r['estimated_credits']} | {r['reason']} |")
        lines += ["", "## Continuity design", "",
                  "Each scene gets an opening and closing still. When continuity is appropriate, the previous scene's closing frame becomes the next scene's opening frame. Image-only scenes are animated locally with pan/zoom/crossfade, while selected motion-critical scenes use the same frame pair as first/last-frame guidance for Flow when supported."]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def _generate_economy_frames(self, m, D, refs, vertical: bool, settings: dict, bible: dict, prog):
        """Create continuity-first opening/closing stills for every scene.

        `frame_source=auto` tries Flow's no-charge image path first and falls back
        to the local/free image provider.  `free` skips Flow entirely.  Frames are
        reusable by both local image-motion and Flow first/last-frame video shots.
        """
        from .planning.frame_prompts import master_character_prompt, master_location_prompt, frame_prompt
        from .providers.flow_browser import FlowServiceBusy
        providers = self._providers()
        flowp, freep = providers["flow"], providers["image"]
        source = str(settings.get("frame_source", "auto") or "auto").lower()
        reuse_project_media = bool(settings.get("flow_reuse_project_media", True))
        longform_single_frame = bool(
            m.profile == "STORYBOARD_ECONOMY"
            and source == "flow"
            and float(getattr(m, "target_seconds", 0) or 0) >= 180
        )
        if longform_single_frame:
            one_frame = sum(1 for _s in m.shots if getattr(_s, "provider", "") not in ("flow", "movieflow"))
            paired = len(m.shots) - one_frame
            prog(f"🧩 Long-form optimization: {one_frame} image-motion shot(s) use one Flow still each; "
                 f"{paired} AI-video shot(s) keep opening+closing frame pairs.", 24)
        if reuse_project_media:
            added = self._bootstrap_flow_frame_cache(m, settings, bible, vertical)
            if added:
                prog(f"♻️ Indexed {added} compatible frame(s) from earlier jobs using this Flow project.", 24)

        def gen(prompt, out, shot, label="frame", bypass_cache: bool = False):
            project_url = self._flow_project_url(m.job_id, settings)
            comp = {"prompt": prompt, "negative": getattr(shot, "negative", ""),
                    "project": f"AutoVideo-{m.job_id}",
                    "project_url": project_url,
                    "approval": "once", "max_generation_credits": 0,
                    "flow_reuse_project_media": reuse_project_media,
                    "flow_capacity_wait_seconds": int(settings.get("flow_capacity_wait_seconds", 900) or 900),
                    "flow_capacity_retries": int(settings.get("flow_capacity_retries", 8) or 8)}
            errors = []

            # Exact project/prompt/aspect cache only. This is intentionally stricter
            # than matching old Flow filenames such as shot_001_open.jpg.
            if reuse_project_media and project_url and not bypass_cache:
                cached = self._flow_frame_cache_get(project_url, prompt, vertical, label)
                if cached:
                    try:
                        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                        shutil.copy2(cached, out)
                        if not self._is_valid_image_file(out):
                            self._remove_invalid_image(out)
                            raise ValueError("cached Flow frame was corrupt/incomplete")
                        prog(f"♻️ {shot.shot_id} {label}: reused exact frame from shared Flow-project cache.", 25)
                        self.pm.log(m.job_id, "flow_frame_cache_hit",
                                    {"shot": shot.shot_id, "label": label, "project_url": project_url,
                                     "mode": "exact"})
                        return out, "flow-project-cache"
                    except Exception:
                        pass
                reuse_mode = str(settings.get("flow_reuse_mode", "exact") or "exact").lower()
                previous = self._previous_project_frame(m, project_url, shot.shot_id, label, reuse_mode)
                if previous:
                    try:
                        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                        shutil.copy2(previous, out)
                        if not self._is_valid_image_file(out):
                            self._remove_invalid_image(out)
                            raise ValueError("reused project frame was corrupt/incomplete")
                        self._flow_frame_cache_put(project_url, prompt, vertical, label, out, m.job_id)
                        prog(f"♻️ {shot.shot_id} {label}: reused existing {reuse_mode}-matched frame from this Flow project.", 25)
                        self.pm.log(m.job_id, "flow_project_existing_frame_reuse",
                                    {"shot": shot.shot_id, "label": label, "project_url": project_url,
                                     "mode": reuse_mode, "source": previous})
                        return out, f"flow-project-{reuse_mode}-reuse"
                    except Exception:
                        pass
            if source in ("auto", "flow"):
                max_attempts = max(1, int(settings.get("flow_frame_retries", 3) or 3))
                network_wait = max(15, int(settings.get("network_wait_seconds", 300) or 300))
                attempt = 1
                network_recoveries = 0
                browser_recoveries = 0
                while attempt <= max_attempts:
                    try:
                        r = flowp.generate_image(shot, comp, out, vertical, dry_run=False)
                        bound = self._remember_flow_project_url(
                            m.job_id, r.get("project_url") or flowp.current_project_url())
                        if bound:
                            comp["project_url"] = bound
                        if r.get("path") and self._is_valid_image_file(r["path"]):
                            if reuse_project_media and comp.get("project_url"):
                                self._flow_frame_cache_put(comp["project_url"], prompt, vertical,
                                                           label, r["path"], m.job_id)
                            return r["path"], "flow"
                        if r.get("path") and os.path.exists(r["path"]):
                            self._remove_invalid_image(r["path"])
                            errtxt = "Flow returned a corrupt/incomplete image file; removed it and will retry"
                        else:
                            errtxt = r.get("error", "no image returned")
                        # A connectivity drop should pause/recover, not consume a
                        # normal generation retry or silently switch providers.
                        if (network_recoveries < 3 and
                                flowp.is_transient_network_error(errtxt)):
                            prog(f"🌐 {shot.shot_id} {label}: network interrupted; waiting for Flow to recover...", 26)
                            if flowp.recover_network(comp["project"], timeout_s=network_wait,
                                                     project_url=comp.get("project_url")):
                                network_recoveries += 1
                                prog(f"🌐 Network restored; retrying {shot.shot_id} {label} without losing progress.", 26)
                                continue
                        errors.append(f"Flow attempt {attempt}: {errtxt}")
                    except FlowRequestPending as e:
                        self._pause_pending_flow(m, shot.shot_id, e, comp.get("project_url", ""))
                    except FlowServiceBusy as e:
                        # High-demand throttling is handled internally with bounded
                        # Try-again/backoff. If that window expires, pause/fallback
                        # without burning normal frame retries.
                        errors.append(f"Flow capacity: {e}")
                        if source == "flow":
                            try:
                                flowp.close()
                            except Exception:
                                pass
                            raise RuntimeError(
                                f"Strict --frame-source flow: {shot.shot_id} {label} paused because Flow Agent remained at high demand. "
                                f"No normal frame retry was consumed. Completed frames are cached; run `python3 cli.py v3 resume {m.job_id}` later. "
                                + str(e)[-500:]
                            )
                        break
                    except Exception as e:
                        if (browser_recoveries < 2 and flowp.is_browser_closed_error(e)):
                            prog(f"🧭 {shot.shot_id} {label}: browser session closed; rebuilding Flow session...", 26)
                            if flowp.recover_browser(comp["project"],
                                                     project_url=comp.get("project_url")):
                                browser_recoveries += 1
                                prog(f"🧭 Browser recovered; retrying {shot.shot_id} {label} without consuming a frame retry.", 26)
                                continue
                        if (network_recoveries < 3 and
                                flowp.is_transient_network_error(e)):
                            prog(f"🌐 {shot.shot_id} {label}: network interrupted; waiting up to {network_wait}s...", 26)
                            if flowp.recover_network(comp["project"], timeout_s=network_wait,
                                                     project_url=comp.get("project_url")):
                                network_recoveries += 1
                                prog(f"🌐 Network restored; retrying {shot.shot_id} {label} without losing progress.", 26)
                                continue
                        errors.append(f"Flow attempt {attempt}: {type(e).__name__}: {e}")
                    if attempt < max_attempts:
                        prog(f"⚠️ {shot.shot_id} {label}: Flow attempt {attempt} failed; retrying ({attempt+1}/{max_attempts})...", 26)
                        time.sleep(min(6.0, 1.5 * attempt))
                    attempt += 1
                if source == "flow":
                    try:
                        flowp.close()
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"Strict --frame-source flow: {shot.shot_id} {label} failed after {max_attempts} attempts. "
                        f"Completed frames are cached; after fixing connectivity/UI run `python3 cli.py v3 resume {m.job_id}`. "
                        + "; ".join(errors)[-900:]
                    )
                prog(f"⚠️ {shot.shot_id} {label}: Flow failed after {max_attempts} attempts -> free fallback (may use Pollinations).", 26)
                self.pm.log(m.job_id, "flow_frame_fallback", {
                    "shot": shot.shot_id, "label": label, "errors": errors[-max_attempts:], "to": "free"})
            try:
                r = freep.generate_image(shot, comp, out, vertical, dry_run=False)
                if r.get("path") and self._is_valid_image_file(r["path"]):
                    return r["path"], "free"
                if r.get("path") and os.path.exists(r["path"]):
                    self._remove_invalid_image(r["path"])
                    errors.append("free provider returned a corrupt/incomplete image")
                else:
                    errors.append(r.get("error", "free provider returned no image"))
            except Exception as e:
                errors.append(str(e))
            raise RuntimeError("; ".join(errors)[-800:])

        # Stable master references.  They are generated once per project and can
        # later be supplied to Flow ingredients/character references.
        if bible.get("characters") and not refs.get("character"):
            tmp = os.path.join(D["storyboard"], "character_master.jpg")
            try:
                dummy = m.shots[0] if m.shots else None
                if dummy:
                    p, src = gen(master_character_prompt(bible, vertical), tmp, dummy, "character master")
                    refs.add("character", p, "character_master.jpg")
                    self.pm.log(m.job_id, "master_character", {"source": src})
            except Exception as e:
                prog(f"⚠️ Character master image failed: {str(e)[:160]}", 25)
                self.pm.log(m.job_id, "master_character_failed", {"error": str(e)[:180]})
                if source == "flow":
                    raise
        if bible.get("locations") and not refs.get("location"):
            tmp = os.path.join(D["storyboard"], "location_master.jpg")
            try:
                dummy = m.shots[0] if m.shots else None
                if dummy:
                    p, src = gen(master_location_prompt(bible, vertical), tmp, dummy, "location master")
                    refs.add("location", p, "location_master.jpg")
                    self.pm.log(m.job_id, "master_location", {"source": src})
            except Exception as e:
                prog(f"⚠️ Location master image failed: {str(e)[:160]}", 25)
                self.pm.log(m.job_id, "master_location_failed", {"error": str(e)[:180]})
                if source == "flow":
                    raise

        previous_close = None
        previous_shot = None
        for i, s in enumerate(m.shots):
            open_path = os.path.join(D["storyboard"], f"{s.shot_id}_open.jpg")
            close_path = os.path.join(D["storyboard"], f"{s.shot_id}_close.jpg")
            # A full disk or interrupted browser download can leave a .jpg that
            # exists but is not actually decodable.  Purge it before deciding a
            # frame is cached/completed so resume can regenerate it cleanly.
            if self._remove_invalid_image(open_path):
                prog(f"🧹 {s.shot_id} opening frame: removed corrupt/incomplete cached image.", 25)
            if self._remove_invalid_image(close_path):
                prog(f"🧹 {s.shot_id} closing frame: removed corrupt/incomplete cached image.", 26)
            if s.status not in ("planned", "approved", "failed"):
                prev = s.closing_frame or previous_close
                previous_close = prev if self._is_valid_image_file(prev) else previous_close
                continue
            # Preserve continuity only when the new shot genuinely shares the
            # same environment. v5.0 copied *every* previous closing frame into
            # the next opening, which made listicles look like one repeated room.
            # Inserts/b-roll/hooks/outros intentionally refresh composition.
            same_environment = bool(
                previous_shot and
                self._norm_prompt_key(getattr(previous_shot, "environment", "")) ==
                self._norm_prompt_key(getattr(s, "environment", ""))
            )
            refresh_coverages = {"hook", "insert", "broll", "hero_outro"}
            reuse_previous = bool(
                previous_close and self._is_valid_image_file(previous_close) and
                same_environment and getattr(s, "coverage", "primary") not in refresh_coverages
            )
            if reuse_previous:
                try:
                    shutil.copy(previous_close, open_path)
                except shutil.SameFileError:
                    pass
                open_src = "previous-close-continuity"
            elif not self._is_valid_image_file(open_path):
                prog(f"🖼️ [{i+1}/{len(m.shots)}] {s.shot_id} opening frame...",
                     min(29, 25 + int(4 * (i + 1) / max(1, len(m.shots)))))
                _, open_src = gen(frame_prompt(s, bible, vertical, "open"), open_path, s, "opening frame")
            else:
                open_src = "cached"

            # A stale Flow asset selector/cache can accidentally return the
            # generic location master as the shot opening. Do not let a master
            # reference become the actual scene image: force one fresh,
            # action-specific opening frame and replace the poisoned cache entry.
            if self._is_valid_image_file(open_path):
                open_hash = self._file_sha256(open_path)
                location_hashes = {self._file_sha256(lp) for lp in refs.get("location")
                                   if self._is_valid_image_file(lp)}
                if open_hash and open_hash in location_hashes and open_src != "previous-close-continuity":
                    prog(f"♻️ {s.shot_id}: opening frame matched location master; regenerating a scene-specific composition.", 25)
                    try:
                        os.remove(open_path)
                    except Exception:
                        pass
                    open_prompt = frame_prompt(s, bible, vertical, "open") + (
                        " IMPORTANT: create a NEW shot-specific composition, not the generic location/master image. "
                        "Show the described subject action prominently with a clearly different camera position and framing.")
                    _, open_src = gen(open_prompt, open_path, s, "opening frame", bypass_cache=True)
            close_prompt_text = frame_prompt(s, bible, vertical, "close")
            degraded_close = False
            skip_longform_close = bool(
                longform_single_frame
                and getattr(s, "provider", "") not in ("flow", "movieflow")
                and not self._is_valid_image_file(close_path)
            )
            if skip_longform_close:
                # For five-minute+ strict-Flow jobs, generating a second still for
                # every local image-motion scene roughly doubles browser work and
                # can take hours. A single high-quality Flow still already supports
                # the local pan/zoom renderer, while paid/AI-video shots retain
                # distinct first/last guidance frames.
                close_src = "skipped-longform-single-frame"
                degraded_close = True
                prog(f"⏭️ [{i+1}/{len(m.shots)}] {s.shot_id} closing frame skipped (single-frame long-form image-motion).",
                     min(29, 25 + int(4 * (i + 1) / max(1, len(m.shots)))))
            elif not self._is_valid_image_file(close_path):
                prog(f"🖼️ [{i+1}/{len(m.shots)}] {s.shot_id} closing frame...",
                     min(29, 25 + int(4 * (i + 1) / max(1, len(m.shots)))))
                try:
                    _, close_src = gen(close_prompt_text, close_path, s, "closing frame")
                except RuntimeError as e:
                    # In STORYBOARD_ECONOMY only the selected paid Flow-video
                    # scene truly requires a distinct closing frame.  Do not pause
                    # the entire job because a later image-motion scene's closing
                    # still timed out after all Flow retries.  Reuse that scene's
                    # already-generated Flow opening frame as an emergency close.
                    # This does NOT switch to another image provider and therefore
                    # still honours strict --frame-source flow for source media.
                    if (source == "flow" and m.profile == "STORYBOARD_ECONOMY"
                            and getattr(s, "provider", "") != "flow"
                            and os.path.exists(open_path)):
                        shutil.copy2(open_path, close_path)
                        close_src = "flow-opening-emergency-reuse"
                        degraded_close = True
                        prog(f"⚠️ {s.shot_id} closing frame: Flow exhausted retries; "
                             "reusing the existing Flow opening frame so this non-video scene does not pause the job.", 26)
                        self.pm.log(m.job_id, "flow_closing_frame_emergency_reuse", {
                            "shot": s.shot_id, "error": str(e)[-500:],
                            "source": "opening_frame", "provider": "flow"})
                    else:
                        raise
            else:
                close_src = "cached"

            # v4.6 could bootstrap a poisoned cache created by older Flow asset
            # selection bugs. In the reported run shot_001_open.jpg and
            # shot_001_close.jpg had the *same content hash*, so Flow was asked to
            # interpolate an image to itself. Detect/repair that automatically.
            if os.path.exists(open_path) and os.path.exists(close_path) and not degraded_close:
                open_hash = self._file_sha256(open_path)
                close_hash = self._file_sha256(close_path)
                if open_hash and open_hash == close_hash:
                    prog(f"♻️ {s.shot_id}: opening/closing frames are identical; "
                         "invalidating the closing-frame cache and regenerating it.", 26)
                    self.pm.log(m.job_id, "duplicate_frame_pair", {
                        "shot": s.shot_id, "sha256": open_hash,
                        "open_source": open_src, "close_source": close_src})
                    # Remove the bad original-key cache entry as well as this job's
                    # copy so a later run cannot immediately resurrect it.
                    project_url = self._flow_project_url(m.job_id, settings)
                    try:
                        bad = self._flow_frame_cache_get(project_url, close_prompt_text, vertical, "closing frame")
                        if bad and os.path.exists(bad):
                            os.remove(bad)
                        meta_bad = os.path.splitext(bad)[0] + ".json" if bad else ""
                        if meta_bad and os.path.exists(meta_bad):
                            os.remove(meta_bad)
                    except Exception:
                        pass
                    try:
                        os.remove(close_path)
                    except Exception:
                        pass

                    # Give the image agent an explicit visual delta while retaining
                    # the same subject/location/identity continuity.
                    corrective = (close_prompt_text +
                        " IMPORTANT: This closing frame MUST be visibly different from the opening frame. "
                        "Show the completed action/end-state, change subject pose or object state, and use a "
                        "noticeably different camera moment while preserving identity, wardrobe and location.")
                    _, close_src = gen(corrective, close_path, s, "closing frame", bypass_cache=True)

                    # One extra repair attempt if the provider still returned the
                    # exact same bytes. This is independent of paid video retries.
                    if (os.path.exists(close_path) and
                            self._file_sha256(close_path) == open_hash):
                        try:
                            os.remove(close_path)
                        except Exception:
                            pass
                        corrective2 = corrective + (
                            " Use a different framing/camera position and a clearly changed end-state; "
                            "do not reproduce the supplied/opening composition.")
                        _, close_src = gen(corrective2, close_path, s, "closing frame", bypass_cache=True)

                    # Store a repaired distinct frame under the normal/original key
                    # so future same-project jobs can safely reuse it.
                    if (project_url and os.path.exists(close_path) and
                            self._file_sha256(close_path) != open_hash):
                        self._flow_frame_cache_put(project_url, close_prompt_text, vertical,
                                                   "closing frame", close_path, m.job_id)

            # For composition-refresh shots, reject a closing frame that is
            # perceptually almost the same as the previous scene. Exact byte
            # comparisons miss re-encoded duplicates; dHash catches those cheaply.
            if (previous_close and self._is_valid_image_file(previous_close) and
                    self._is_valid_image_file(close_path) and
                    getattr(s, "provider", "") != "flow" and
                    getattr(s, "coverage", "") in {"insert", "broll", "hero_outro"}):
                dist = self._image_distance(previous_close, close_path)
                if dist is not None and dist <= 5:
                    prog(f"♻️ {s.shot_id}: composition too similar to previous scene; regenerating for visual diversity.", 26)
                    try:
                        os.remove(close_path)
                    except Exception:
                        pass
                    diverse_prompt = close_prompt_text + (
                        " IMPORTANT: make this composition visually distinct from the previous shot. "
                        "Change camera distance/angle, subject placement, foreground/background geometry and end-state while preserving story continuity.")
                    try:
                        _, close_src = gen(diverse_prompt, close_path, s, "closing frame", bypass_cache=True)
                    except Exception:
                        # Diversity is quality-only; the normal valid frame path
                        # remains recoverable on resume and must not crash a job.
                        pass

            s.opening_frame = open_path if self._is_valid_image_file(open_path) else None
            s.closing_frame = close_path if self._is_valid_image_file(close_path) else None
            s.opening_frame_source = open_src if s.opening_frame else ""
            s.closing_frame_source = close_src if s.closing_frame else ""
            s.start_frame = s.opening_frame
            s.end_frame = s.closing_frame
            if s.opening_frame:
                try: refs.add("start", s.opening_frame, f"{s.shot_id}_start.jpg")
                except Exception: pass
            if s.closing_frame:
                try: refs.add("end", s.closing_frame, f"{s.shot_id}_end.jpg")
                except Exception: pass
            s.reference_assets = [p for p in [s.opening_frame, s.closing_frame, *refs.get("character"), *refs.get("location")] if p]
            self.pm.update_shot(m.job_id, s)
            self.pm.log(m.job_id, "economy_frames", {"shot": s.shot_id, "open": open_src,
                                                       "close": close_src, "strategy": s.media_strategy})
            previous_close = s.closing_frame
            previous_shot = s
        try:
            flowp.close()
        except Exception:
            pass

    # ---------------- generation ----------------
    def _generate_scene_images(self, m, D, refs, vertical: bool, K: int, prog, settings=None):
        """K stills per scene via Flow image mode (free provider fallback).
        Best still overwrites the storyboard frame -> feeds image/frames video gen."""
        workers = max(1, min(3, int((settings or {}).get("flow_image_workers", 1) or 1)))
        if workers > 1:
            return self._generate_scene_images_parallel(m, D, refs, vertical, K, prog,
                                                        settings or {}, workers)
        from .providers.flow_browser import (FlowUIChanged, FlowAuthNeeded, FlowQuotaExceeded,
                                                   FlowBrowserClosedError, FlowServiceBusy)
        from .qc.video_qc import score_image
        providers = self._providers()
        fprov, freeprov = providers["flow"], providers["image"]
        project_url = self._flow_project_url(m.job_id, settings or {})
        for idx, s in enumerate(m.shots):
            if s.status not in ("planned", "approved", "failed"):
                continue
            imgdir = os.path.join(D["flow"], "shots", s.shot_id, "images")
            os.makedirs(imgdir, exist_ok=True)
            got = []
            for k in range(K):
                out = os.path.join(imgdir, f"img_{k+1:02d}.jpg")
                if os.path.exists(out) and os.path.getsize(out) > 5000:
                    got.append(out)
                    continue
                prog(f"🖼️ {s.shot_id} image {k+1}/{K}...", 26)
                comp = {"prompt": s.compiled_prompt, "negative": s.negative,
                        "project": f"AutoVideo-{m.job_id}",
                        "project_url": project_url}
                try:
                    res = fprov.generate_image(s, comp, out, vertical, dry_run=False)
                    observed_url = res.get("project_url")
                    if not observed_url:
                        try:
                            observed_url = fprov.current_project_url()
                        except Exception:
                            observed_url = ""
                    bound = self._remember_flow_project_url(m.job_id, observed_url)
                    if bound:
                        project_url = bound
                        if settings is not None:
                            settings["flow_project_url"] = bound
                    if res.get("path") and os.path.exists(res["path"]):
                        got.append(out)
                    else:
                        raise RuntimeError(res.get("error", "no image returned"))
                except FlowRequestPending as e:
                    self._pause_pending_flow(m, s.shot_id, e, project_url)
                except (FlowAuthNeeded, FlowQuotaExceeded) as e:
                    try:
                        bound = self._remember_flow_project_url(m.job_id, fprov.current_project_url())
                        if bound:
                            project_url = bound
                    except Exception:
                        pass
                    m2 = self.pm.load_manifest(m.job_id)
                    m2.status = "assisted"
                    self.pm.save_manifest(m2)
                    self.db.upsert(m.job_id, status="assisted")
                    raise AssistedNeeded(m.job_id, s.shot_id, s.compiled_prompt,
                                         D["downloads"], f"{type(e).__name__}: {e}")
                except Exception as e:
                    self.pm.log(m.job_id, "scene_image_flow_failed",
                                {"shot": s.shot_id, "error": str(e)[:150], "fallback": "free"})
                    try:
                        r2 = freeprov.generate_image(s, comp, out, vertical, dry_run=False)
                        if r2.get("path"):
                            got.append(out)
                    except Exception as e2:
                        self.pm.log(m.job_id, "scene_image_failed",
                                    {"shot": s.shot_id, "error": str(e2)[:150]})
            scored = [(score_image(p)["overall"], p) for p in got
                      if self._is_valid_image_file(p)]
            scored.sort(reverse=True)
            if scored and scored[0][0] > 0:
                best = scored[0][1]
                frame = os.path.join(D["storyboard"], f"{s.shot_id}.jpg")
                try:
                    shutil.copy(best, frame)
                    refs.add("storyboard", frame, f"{s.shot_id}.jpg")
                except Exception:
                    pass
                s.reference_assets = [p for _, p in scored]
                self.pm.log(m.job_id, "scene_images",
                            {"shot": s.shot_id, "count": len(scored),
                             "best_score": scored[0][0]})
            else:
                self.pm.log(m.job_id, "scene_images_empty", {"shot": s.shot_id})
            self.pm.update_shot(m.job_id, s)
        try:
            providers["flow"].close()
        except Exception:
            pass

    def _generate_scene_images_parallel(self, m, D, refs, vertical: bool, K: int,
                                        prog, settings: dict, workers: int):
        """Generate independent still candidates with isolated browser profiles.

        Playwright's sync API and one browser context are not thread-safe.  Each
        worker therefore owns a provider/profile.  Results are merged and the
        manifest is updated only on the main thread.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from .providers.flow_browser import (FlowBrowserProvider, PROFILE_DIR,
                                             FlowAuthNeeded, FlowQuotaExceeded,
                                             resolve_browser_cfg)
        from .providers.image_provider import ImageProvider
        from .qc.video_qc import score_image

        worker_root = os.path.join(D["root"], ".flow-workers")
        os.makedirs(worker_root, exist_ok=True)
        try:
            with open("config/flow_ui.yaml", encoding="utf-8") as handle:
                browser_cfg = resolve_browser_cfg(yaml.safe_load(handle) or {})
            worker_uses_cdp = (str(browser_cfg.get("mode", "auto")).lower() in ("auto", "cdp")
                               and bool(browser_cfg.get("cdp_url")))
        except Exception:
            worker_uses_cdp = False
        # Bootstrap a worker's persistent profile once. Lock/socket files must
        # never be copied from an active Chromium profile.
        def profile_for(index):
            dst = os.path.join(worker_root, f"worker-{index + 1}")
            if worker_uses_cdp:
                # These profiles are not used by CDP-attached workers. Avoid
                # copying a potentially live Chrome profile just to attach tabs.
                os.makedirs(dst, exist_ok=True)
                return dst
            if not os.path.isdir(dst) and os.path.isdir(PROFILE_DIR):
                try:
                    shutil.copytree(PROFILE_DIR, dst, ignore=shutil.ignore_patterns(
                        "Singleton*", "LOCK", "lockfile", "DevToolsActivePort", "*.tmp"))
                except Exception:
                    os.makedirs(dst, exist_ok=True)
            else:
                os.makedirs(dst, exist_ok=True)
            return dst

        tasks = []
        for s in m.shots:
            if s.status not in ("planned", "approved", "failed"):
                continue
            imgdir = os.path.join(D["flow"], "shots", s.shot_id, "images")
            os.makedirs(imgdir, exist_ok=True)
            for k in range(K):
                out = os.path.join(imgdir, f"img_{k+1:02d}.jpg")
                if os.path.exists(out):
                    if os.path.getsize(out) > 5000 and self._is_valid_image_file(out):
                        continue
                    self._remove_invalid_image(out)
                tasks.append((s, k, out))

        # A baseline diff cannot attribute concurrent generations in one project.
        # Each worker therefore owns a dedicated project AND browser/profile/tab.
        prog(f"🖼️ Parallel Flow queue: {len(tasks)} image(s), {workers} isolated worker project(s). Master references are created serially first.", 25)

        def run_batch(wi, batch):
            provider = None
            free_provider = ImageProvider()
            results = []
            project = f"AutoVideo-{m.job_id}-images-worker-{wi + 1}"
            binding_path = os.path.join(worker_root, f"worker-{wi + 1}-project.json")

            def fallback(shot, out, project_url, flow_error):
                journal = out + ".flow-request.json"
                if os.path.isfile(journal):
                    # Never route a submitted/pending Flow request to another
                    # provider; keep its project binding available to Resume.
                    try:
                        with open(journal, encoding="utf-8") as handle:
                            pending_url = json.load(handle).get("project_url", "")
                    except Exception:
                        pending_url = project_url
                    pending = FlowRequestPending(
                        "A saved Flow image request is still pending; worker recovery failed, "
                        "so no replacement provider or prompt was submitted.")
                    return (shot, "", pending_url, "failed", str(pending), pending)
                try:
                    result = free_provider.generate_image(shot, {
                        "prompt": shot.compiled_prompt, "negative": shot.negative,
                        "project": project, "project_url": project_url,
                    }, out, vertical, dry_run=False)
                    fallback_path = result.get("path")
                    if fallback_path and self._is_valid_image_file(fallback_path):
                        return (shot, fallback_path, project_url, "free",
                                f"Flow failed: {str(flow_error)[:180]}", None)
                    fallback_error = result.get("error", "free provider returned no valid image")
                except Exception as fallback_exc:
                    fallback_error = str(fallback_exc)
                detail = f"Flow failed: {flow_error}; free fallback failed: {fallback_error}"[:300]
                # Match the prior feature's behavior: report this candidate as
                # failed and continue other images instead of pausing the job.
                return (shot, "", project_url, "failed", detail, None)

            try:
                # Playwright is created, used and closed on this same thread.
                provider = FlowBrowserProvider(profile_dir=profile_for(wi))
                project_url = ""
                if os.path.isfile(binding_path):
                    try:
                        with open(binding_path, encoding="utf-8") as handle:
                            project_url = json.load(handle).get("project_url", "")
                    except (OSError, ValueError, TypeError):
                        project_url = ""
                browser = provider._ensure()
                browser.ensure_project(project, project_url=project_url or None)
                project_url = browser.current_project_url()
                if not project_url:
                    raise RuntimeError("Parallel worker did not expose a project URL")
                with open(binding_path + ".tmp", "w", encoding="utf-8") as handle:
                    json.dump({"project_url": project_url}, handle)
                os.replace(binding_path + ".tmp", binding_path)
                for shot, k, out in batch:
                    comp = {"prompt": shot.compiled_prompt, "negative": shot.negative,
                            "project": project, "project_url": project_url,
                            "approval": "once", "max_generation_credits": 0,
                            "reference_paths": [path for path in (
                                os.path.join(D["storyboard"], "character_master.jpg"),
                                os.path.join(D["storyboard"], "location_master.jpg")) if os.path.isfile(path)]}
                    try:
                        result = provider.generate_image(shot, comp, out, vertical, dry_run=False)
                        if not result.get("path") or not os.path.isfile(result["path"]):
                            raise RuntimeError(result.get("error", "no image returned"))
                        results.append((shot, out, project_url, "flow", "", None))
                    except (FlowAuthNeeded, FlowQuotaExceeded, FlowRequestPending) as error:
                        # A pending exact Flow request must never be replaced by
                        # a different provider or another generation attempt.
                        results.append((shot, "", project_url, "failed", str(error)[:300], error))
                        break
                    except Exception as error:
                        results.append(fallback(shot, out, project_url, error))
                        if results[-1][5] is not None:
                            break
            except (FlowAuthNeeded, FlowQuotaExceeded) as error:
                results.append((batch[0][0], "", "", "failed", str(error)[:300], error))
            except Exception as error:
                # If project/browser bootstrap failed, preserve pending journals;
                # otherwise retain the legacy free-provider fallback for each task.
                for shot, _k, out in batch:
                    result = fallback(shot, out, "", error)
                    results.append(result)
                    if result[5] is not None:
                        break
            finally:
                if provider is not None:
                    try:
                        provider.close()
                    except Exception:
                        pass
            return results

        by_shot = {s.shot_id: [] for s in m.shots}
        auth_error = None
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="flow-image") as pool:
            batches = [[] for _ in range(workers)]
            for item in tasks:
                shot, candidate_index, _out = item
                base = int(hashlib.sha256(str(shot.shot_id).encode()).hexdigest()[:8], 16)
                batches[(base + int(candidate_index)) % workers].append(item)
            futures = [pool.submit(run_batch, i, batch) for i, batch in enumerate(batches) if batch]
            done = 0
            for future in as_completed(futures):
                for shot, path, url, source, error, exception in future.result():
                    done += 1
                    if path:
                        by_shot.setdefault(shot.shot_id, []).append(path)
                    self.pm.log(m.job_id, "parallel_scene_image", {
                        "shot": shot.shot_id, "source": source, "path": path,
                        "worker_project_url": url, "error": error})
                    if exception is not None:
                        try:
                            setattr(exception, "project_url", url)
                        except Exception:
                            pass
                        auth_error = (shot, exception)
                    prog(f"🖼️ Parallel images completed {done}/{len(tasks)}", 25 + 4 * done / max(1, len(tasks)))
        if auth_error:
            shot, error = auth_error
            if isinstance(error, FlowRequestPending):
                self._pause_pending_flow(m, shot.shot_id, error,
                                         project_url=getattr(error, "project_url", ""))
            raise AssistedNeeded(m.job_id, shot.shot_id, shot.compiled_prompt,
                                 D["downloads"], f"{type(error).__name__}: {error}")

        # Include already-cached files and update shared state serially.
        for s in m.shots:
            imgdir = os.path.join(D["flow"], "shots", s.shot_id, "images")
            got = sorted(set(by_shot.get(s.shot_id, []) + glob.glob(os.path.join(imgdir, "img_*.jpg")))) if os.path.isdir(imgdir) else []
            scored = [(score_image(p)["overall"], p) for p in got
                      if self._is_valid_image_file(p)]
            scored.sort(reverse=True)
            if scored and scored[0][0] > 0:
                frame = os.path.join(D["storyboard"], f"{s.shot_id}.jpg")
                shutil.copy(scored[0][1], frame)
                refs.add("storyboard", frame, f"{s.shot_id}.jpg")
                s.reference_assets = [p for _, p in scored]
            self.pm.update_shot(m.job_id, s)

    def _providers(self):
        from .providers.flow_browser import FlowBrowserProvider
        from .providers.comfy_provider import ComfyProvider
        from .providers.stock_provider import StockProvider
        from .providers.image_provider import ImageProvider
        from .providers.movieflow_browser import MovieFlowBrowserProvider
        return {"flow": FlowBrowserProvider(), "movieflow": MovieFlowBrowserProvider(),
                "comfy": ComfyProvider(), "stock": StockProvider(), "image": ImageProvider()}

    def _generate_all(self, m, D, refs, router, vertical, dry, prog, settings=None):
        from .providers.flow_browser import (FlowUIChanged, FlowAuthNeeded, FlowQuotaExceeded,
                                                   FlowBrowserClosedError, FlowServiceBusy)
        from .qc.video_qc import analyze_take, RETRY_MODIFIERS
        providers = self._providers()
        movieflow_full = self._movieflow_full_story_enabled(m, settings or {})
        avail = {k: p.status().available for k, p in providers.items()}
        self.pm.log(m.job_id, "provider_status", {k: v for k, v in avail.items()})
        takeroot = os.path.join(D["flow"], "shots")
        max_retries = router.budgets.get("MAX_RETRIES_PER_SHOT", 2)

        pending = [s for s in m.shots if s.status in ("planned", "approved", "generating", "qc", "failed")]
        total = len(m.shots)
        for s in pending:
            if s.status == "failed" and s.retry_count >= max_retries:
                continue
            s.status = "generating"
            self.pm.update_shot(m.job_id, s)
            try:
                use_prov = ProviderRouter(m.profile).plan(s.provider, avail)
            except NeedsDecision as e:
                m = self.pm.load_manifest(m.job_id)
                m.status = "paused"
                self.pm.save_manifest(m)
                raise e
            planned_provider = s.provider
            if use_prov != planned_provider:
                reason = f"planned {planned_provider} unavailable; runtime routed to {use_prov}"
                s.fallback_reason = reason
                prog(f"⚠️ {s.shot_id}: {reason}", 29)
                self.pm.log(m.job_id, "provider_runtime_reroute",
                            {"shot": s.shot_id, "from": planned_provider, "to": use_prov})
            shot_dir = os.path.join(takeroot, s.shot_id)
            os.makedirs(shot_dir, exist_ok=True)
            shot_refs = refs.for_shot(s.shot_id)
            # Resolve provider before building provider-specific compiled fields.
            # v5.3.1 referenced current_prov while constructing the MovieFlow
            # story payload, before current_prov had been assigned.
            current_prov = use_prov
            if s.start_frame and os.path.exists(s.start_frame):
                shot_refs["start"] = s.start_frame
            elif s.opening_frame and os.path.exists(s.opening_frame):
                shot_refs["start"] = s.opening_frame
            if s.end_frame and os.path.exists(s.end_frame):
                shot_refs["end"] = s.end_frame
            elif s.closing_frame and os.path.exists(s.closing_frame):
                shot_refs["end"] = s.closing_frame
            compiled = {"prompt": s.compiled_prompt, "negative": s.negative,
                        "project": f"AutoVideo-{m.job_id}",
                        "project_url": self._flow_project_url(m.job_id, settings or {}),
                        "approval": (settings or {}).get("flow_approval", "once"),
                        "max_generation_credits": (settings or {}).get("max_generation_credits", 10),
                        "flow_capacity_wait_seconds": int((settings or {}).get("flow_capacity_wait_seconds", 900) or 900),
                        "flow_capacity_retries": int((settings or {}).get("flow_capacity_retries", 8) or 8),
                        "flow_video_ready_grace_seconds": int((settings or {}).get("flow_video_ready_grace_seconds", 20) or 20),
                        "flow_video_recovery_wait_seconds": int((settings or {}).get("flow_video_recovery_wait_seconds", 180) or 180),
                        "flow_reuse_project_media": bool((settings or {}).get("flow_reuse_project_media", True)),
                        "flow_reuse_mode": str((settings or {}).get("flow_reuse_mode", "exact") or "exact"),
                        "movieflow_project_url": str((settings or {}).get("movieflow_project_url", "") or ""),
                        "movieflow_wait_seconds": int((settings or {}).get("movieflow_wait_seconds", 1800) or 1800),
                        "movieflow_recovery_wait_seconds": int((settings or {}).get("movieflow_recovery_wait_seconds", 300) or 300),
                        "movieflow_story_prompt": s.compiled_prompt if current_prov == "movieflow" else ""}

            takes = []
            n_cand = 1 if dry else max(1, s.num_candidates)
            for t in range(n_cand):
                pct = 30 + int(50 * ((total - len([x for x in m.shots if x.status in ('planned','approved','generating','qc','failed')])) / max(1, total)))
                current_prov = use_prov
                prov = providers[current_prov]
                prog(f"🎬 {s.shot_id} take {t+1}/{n_cand} via {current_prov}/{s.model}...", min(82, pct))
                take_path = os.path.join(shot_dir, f"take_{t+1:02d}.mp4")
                fallback_reason = ""
                try:
                    # STORYBOARD_ECONOMY gets one bounded Flow-video retry before
                    # dropping to local image motion. This retry is separate from
                    # still-frame retries and is useful for transient Agent/approval
                    # glitches where the first request never creates usable media.
                    flow_video_retries = max(0, int((settings or {}).get("flow_video_retries", 1) or 0))
                    flow_attempt = 0
                    while True:
                        try:
                            reused_video = None
                            if (current_prov == "flow" and not dry
                                    and bool((settings or {}).get("flow_reuse_project_media", True))):
                                reused_video = self._previous_project_video(
                                    m, compiled.get("project_url", ""), s.shot_id,
                                    str((settings or {}).get("flow_reuse_mode", "exact") or "exact"))
                            if reused_video:
                                shutil.copy2(reused_video, take_path)
                                prog(f"♻️ {s.shot_id}: reused an existing accepted Flow video from this project.", min(82, pct))
                                res = {"path": take_path, "provider": "flow", "model": s.model,
                                       "credits": 0, "project_url": compiled.get("project_url", ""),
                                       "log": "flow project video reuse"}
                            else:
                                res = prov.generate(s, compiled, shot_refs, take_path, vertical, dry_run=dry)
                        except (FlowBrowserClosedError, FlowServiceBusy, FlowUIChanged) as e:
                            if isinstance(e, FlowRequestPending):
                                self._pause_pending_flow(m, s.shot_id, e, compiled.get("project_url", ""))
                            # The Flow provider owns post-submit recovery. Do not
                            # start another full recovery timer here; v5.3.2 could
                            # stack multiple 179s waits for one shot. A browser-
                            # closed retry gets only an immediate session rebuild.
                            if (current_prov == "flow" and m.profile == "STORYBOARD_ECONOMY"
                                    and flow_attempt < flow_video_retries):
                                flow_attempt += 1
                                prog(f"🔁 {s.shot_id}: Flow video attempt failed; retrying once "
                                     f"({flow_attempt}/{flow_video_retries}) before image-motion fallback...", min(82, pct))
                                self.pm.log(m.job_id, "flow_video_retry",
                                            {"shot": s.shot_id, "attempt": flow_attempt + 1,
                                             "error": f"{type(e).__name__}: {str(e)[:220]}"})
                                # Browser-closed errors get an explicit project-URL recovery.
                                if isinstance(e, FlowBrowserClosedError):
                                    try:
                                        providers["flow"].recover_browser(
                                            compiled["project"], project_url=compiled.get("project_url"))
                                    except Exception:
                                        pass
                                time.sleep(2)
                                continue
                            raise

                        if current_prov == "flow":
                            bound = self._remember_flow_project_url(
                                m.job_id, res.get("project_url") or providers["flow"].current_project_url())
                            if bound:
                                compiled["project_url"] = bound
                        elif current_prov == "movieflow":
                            bound = self._remember_movieflow_project_url(
                                m.job_id, res.get("project_url") or providers["movieflow"].current_project_url())
                            if bound:
                                compiled["movieflow_project_url"] = bound

                        if (current_prov == "flow" and m.profile == "STORYBOARD_ECONOMY"
                                and not dry and not res.get("path")
                                and flow_attempt < flow_video_retries):
                            # Provider.generate() already exhausted exactly one
                            # bounded recovery window. Never add another recovery
                            # wait at the factory layer. The next provider call has
                            # a short retry-guard scan before it can submit again.
                            flow_attempt += 1
                            reason = res.get("error", "Flow returned no usable media")
                            prog(f"🔁 {s.shot_id}: Flow returned no usable video; retrying once "
                                 f"({flow_attempt}/{flow_video_retries}) before image-motion fallback...", min(82, pct))
                            self.pm.log(m.job_id, "flow_video_retry",
                                        {"shot": s.shot_id, "attempt": flow_attempt + 1,
                                         "error": str(reason)[:220]})
                            time.sleep(2)
                            continue
                        break
                except (FlowUIChanged, FlowAuthNeeded, FlowQuotaExceeded,
                        FlowBrowserClosedError, FlowServiceBusy) as e:
                    flow_baseline = set(getattr(
                        providers.get("flow"), "_last_video_baseline", set()) or set())
                    if current_prov == "flow":
                        try:
                            bound = self._remember_flow_project_url(
                                m.job_id, providers["flow"].current_project_url())
                            if bound:
                                compiled["project_url"] = bound
                        except Exception:
                            pass
                    if m.profile == "STORYBOARD_ECONOMY" and avail.get("image"):
                        fallback_reason = f"Flow generation failure after retry: {str(e)[:180]}"
                        prog(f"⚠️ {s.shot_id}: Flow unavailable after retry -> image-motion fallback", min(82, pct))
                        self.pm.log(m.job_id, "flow_motion_fallback",
                                    {"shot": s.shot_id, "error": str(e)[:220], "fallback": "image_motion"})
                        current_prov = "image"
                        res = providers["image"].generate(s, compiled, shot_refs, take_path, vertical, dry_run=dry)
                    elif isinstance(e, FlowAuthNeeded):
                        s.status = "failed"
                        self.pm.update_shot(m.job_id, s)
                        m2 = self.pm.load_manifest(m.job_id)
                        m2.status = "assisted"
                        self.pm.save_manifest(m2)
                        self.db.upsert(m.job_id, status="assisted")
                        self._write_pause_state(
                            m.job_id, s.shot_id, f"{type(e).__name__}: {e}",
                            kind="flow_login", project_url=compiled.get("project_url", ""),
                            baseline_signatures=flow_baseline)
                        raise AssistedNeeded(m.job_id, s.shot_id, s.compiled_prompt,
                                             D["downloads"], f"{type(e).__name__}: {e}")
                    else:
                        s.status = "failed"
                        self.pm.update_shot(m.job_id, s)
                        m2 = self.pm.load_manifest(m.job_id)
                        m2.status = "paused"
                        self.pm.save_manifest(m2)
                        self.db.upsert(m.job_id, status="paused")
                        if isinstance(e, FlowQuotaExceeded):
                            kind = "flow_usage_limit"
                        elif isinstance(e, FlowServiceBusy):
                            kind = "flow_capacity"
                        else:
                            kind = "flow_download_or_ui"
                        state = self._write_pause_state(
                            m.job_id, s.shot_id, f"{type(e).__name__}: {e}",
                            kind=kind, project_url=compiled.get("project_url", ""),
                            baseline_signatures=flow_baseline)
                        next_step = (
                            "Scan for media newer than the saved pre-generation baseline before any retry."
                            if state.get("safe_automatic_recovery") else
                            "Wait for Flow access to reset, then resume this same saved job."
                        )
                        raise NeedsDecision(
                            f"Flow paused at {s.shot_id}. Existing generated media and "
                            f"{state['accepted_shots']}/{state['total_shots']} accepted shots are safe. "
                            f"{next_step} "
                            f"Reason: {type(e).__name__}: {e}",
                            alternatives=[x["command"] for x in state["actions"]])

                # A provider can report a download/detection failure as a normal
                # result after Flow has already spent the credits. For strict
                # Flow profiles, pause and scan the bound project instead of
                # silently submitting another request on recursive resume.
                if (not dry and current_prov == "flow" and not res.get("path")
                        and m.profile != "STORYBOARD_ECONOMY"):
                    s.status = "failed"
                    self.pm.update_shot(m.job_id, s)
                    m2 = self.pm.load_manifest(m.job_id)
                    m2.status = "paused"
                    self.pm.save_manifest(m2)
                    self.db.upsert(m.job_id, status="paused")
                    reason = str(res.get("error") or "Flow media was generated but no valid video was downloaded")
                    state = self._write_pause_state(
                        m.job_id, s.shot_id, reason, kind="flow_existing_video_recovery",
                        project_url=compiled.get("project_url", ""),
                        baseline_signatures=set(getattr(
                            providers.get("flow"), "_last_video_baseline", set()) or set()))
                    raise NeedsDecision(
                        f"Flow may already contain the finished video for {s.shot_id}; the job is paused "
                        f"before any retry can spend more credits. {reason}",
                        alternatives=[x["command"] for x in state["actions"]])
                if not dry and not res.get("path") and current_prov == "movieflow" and movieflow_full:
                    s.status = "failed"
                    self.pm.update_shot(m.job_id, s)
                    m2 = self.pm.load_manifest(m.job_id)
                    m2.status = "paused"
                    self.pm.save_manifest(m2)
                    self.db.upsert(m.job_id, status="paused")
                    raise NeedsDecision(
                        "MovieFlow full-story generation did not produce a valid downloadable video. "
                        + str(res.get("error", "Open MovieFlow Studio and inspect the project, then resume."))[:700],
                        alternatives=[f"Run: python3 cli.py v3 resume {m.job_id}",
                                      "Run: python3 cli.py v3 movieflow-open --project-url <project-url>",
                                      "Use --cartoon-provider flow for the Google Flow cartoon preset"]
                    )
                if not dry and not res.get("path") and m.profile == "STORYBOARD_ECONOMY" and current_prov != "image" and avail.get("image"):
                    fallback_reason = res.get("error", "provider returned no media")
                    prog(f"⚠️ {s.shot_id}: {current_prov} returned no usable media -> image-motion fallback", min(82, pct))
                    self.pm.log(m.job_id, "economy_provider_fallback",
                                {"shot": s.shot_id, "from": current_prov,
                                 "error": fallback_reason, "to": "image_motion"})
                    current_prov = "image"
                    res = providers["image"].generate(s, compiled, shot_refs, take_path, vertical, dry_run=False)
                if dry or not res.get("path"):
                    takes.append({"take": f"take_{t+1:02d}", "dry": True,
                                  "provider": current_prov, "model": res.get("model", s.model),
                                  "credits": res.get("credits", 0) or 0,
                                  "fallback_reason": fallback_reason,
                                  "log": res.get("log", ""), "error": res.get("error", "")})
                    continue
                qc = analyze_take(res["path"],
                                  [shot_refs.get("storyboard"), shot_refs.get("start"), shot_refs.get("character")],
                                  expect_seconds=s.gen_duration, expect_vertical=vertical)
                _save_json(os.path.join(D["qc"], f"{s.shot_id}_take_{t+1:02d}.json"), qc)
                takes.append({"take": f"take_{t+1:02d}", "path": res["path"],
                              "provider": current_prov, "model": res.get("model", s.model),
                              "credits": res.get("credits", 0) or 0,
                              "fallback_reason": fallback_reason,
                              "overall": qc["overall"], "decision": qc["decision"],
                              "failure": qc["failure"]})
                self.pm.log(m.job_id, "take_qc", {"shot": s.shot_id, "take": t + 1,
                                                  "provider": current_prov,
                                                  "overall": qc["overall"], "decision": qc["decision"]})
                self.db.bump(m.job_id, "actual_generations")

            if dry:
                s.takes = [x["take"] for x in takes]
                s.status = "planned"
                self.pm.update_shot(m.job_id, s)
                continue

            # pick best; retry failures with targeted modifier
            takes.sort(key=lambda x: x.get("overall", 0), reverse=True)
            best = takes[0] if takes else None
            if best and best.get("decision") in ("ACCEPT", "REVIEW") and best.get("overall", 0) >= s.qc_threshold - 10:
                shutil.copy(best["path"], os.path.join(shot_dir, "accepted.mp4"))
                s.accepted_take = os.path.join(shot_dir, "accepted.mp4")
                s.takes = [x["take"] for x in takes]
                s.status = "accepted"
                s.actual_provider = best.get("provider", use_prov)
                s.actual_model = best.get("model", s.model)
                if best.get("fallback_reason"):
                    s.fallback_reason = best.get("fallback_reason", "")
                actual_credits = best.get("credits", 0)
                if actual_credits in (-1, None) and s.actual_provider == "flow":
                    actual_credits = router.model_cost(s.model, s.gen_duration)
                try:
                    s.credits_spent = int(round(float(actual_credits or 0)))
                except Exception:
                    s.credits_spent = 0
                self.db.bump(m.job_id, "accepted_shots")
                # continuity: end frame for next shot
                try:
                    refs.best_end_frame(s.accepted_take, os.path.join(D["references"], f"{s.shot_id}_end.jpg"))
                    nxt = next((x for x in m.shots if x.start_frame == f"{{prev_end_frame:{s.shot_id}}}"), None)
                    if nxt is not None:
                        nxt.start_frame = os.path.join(D["references"], f"{s.shot_id}_end.jpg")
                        self.pm.update_shot(m.job_id, nxt)
                except Exception as e:
                    self.pm.log(m.job_id, "endframe_failed", {"shot": s.shot_id, "error": str(e)[:150]})
            else:
                fail = (best or {}).get("failure", "generic")
                if s.retry_count < max_retries:
                    mod = RETRY_MODIFIERS.get(fail, RETRY_MODIFIERS["generic"])
                    s.compiled_prompt = s.compiled_prompt + f" Retry fix ({fail}): {mod}."
                    s.retry_history.append(f"{fail}: {mod}")
                    s.retry_count += 1
                    s.status = "failed"  # resume will retry
                    self.db.bump(m.job_id, "retry_count")
                    self.db.bump(m.job_id, "rejected_shots")
                    self.pm.log(m.job_id, "shot_retry", {"shot": s.shot_id, "failure": fail})
                else:
                    # keep best-effort take rather than blocking the film
                    if best and best.get("path"):
                        shutil.copy(best["path"], os.path.join(shot_dir, "accepted.mp4"))
                        s.accepted_take = os.path.join(shot_dir, "accepted.mp4")
                    s.status = "accepted" if best and best.get("path") else "failed"
                    self.pm.log(m.job_id, "shot_best_effort", {"shot": s.shot_id})
            self.pm.update_shot(m.job_id, s)

        # close browser provider
        try:
            providers["flow"].close()
        except Exception:
            pass
        m = self.pm.load_manifest(m.job_id)
        if not dry:
            # retry loop exhausted? mark review if failures remain
            failed = [s for s in m.shots if s.status == "failed"]
            if failed and all(s.retry_count >= max_retries for s in failed):
                pass  # best-effort already applied
            elif failed:
                return self._generate_all(m, D, refs, router, vertical, dry, prog, settings)  # next retry pass
        self.pm.save_manifest(m)

    # ---------------- assisted association ----------------
    def associate_download(self, job_id: str, shot_id: str, src_file: str) -> dict:
        """Assisted mode: map a user-downloaded Flow clip to a shot, QC it, continue."""
        from .qc.video_qc import analyze_take
        m = self.pm.load_manifest(job_id)
        D = self.pm.dirs(job_id)
        s = next(x for x in m.shots if x.shot_id == shot_id)
        vertical = m.aspect == "9:16"
        shot_dir = os.path.join(D["flow"], "shots", shot_id)
        os.makedirs(shot_dir, exist_ok=True)
        n = len([f for f in os.listdir(shot_dir) if f.startswith("take_")]) + 1
        dst = os.path.join(shot_dir, f"take_{n:02d}.mp4")
        shutil.copy(src_file, dst)
        refs = ReferenceManager(D["references"]).for_shot(shot_id)
        qc = analyze_take(dst, [refs.get("storyboard"), refs.get("start")],
                          expect_seconds=s.gen_duration, expect_vertical=vertical)
        _save_json(os.path.join(D["qc"], f"{shot_id}_take_{n:02d}.json"), qc)
        if qc["decision"] in ("ACCEPT", "REVIEW"):
            shutil.copy(dst, os.path.join(shot_dir, "accepted.mp4"))
            s.accepted_take = os.path.join(shot_dir, "accepted.mp4")
            s.status = "accepted"
            self.db.bump(job_id, "accepted_shots")
        else:
            s.status = "failed"
            self.db.bump(job_id, "rejected_shots")
        s.takes = s.takes + [f"take_{n:02d}"]
        self.pm.update_shot(job_id, s)
        return {"qc": qc, "take": dst}

    def recover_flow_video(self, job_id: str, shot_id: str | None = None,
                           wait_seconds: int = 120,
                           allow_latest: bool = False) -> dict:
        """Download an already-generated video from the bound Flow project.

        This recovery path never fills/submits a prompt and therefore cannot
        initiate a new credit-bearing generation. It is safe to run while the
        account is usage-limited, provided the existing project remains readable.
        """
        from .providers.flow_browser import FlowBrowserProvider

        m = self.pm.load_manifest(job_id)
        candidates = [s for s in m.shots
                      if not s.accepted_take and s.status in
                      ("failed", "generating", "planned", "approved", "qc")]
        if shot_id:
            shot = next((s for s in m.shots if s.shot_id == shot_id), None)
            if shot is None:
                raise ValueError(f"Unknown shot {shot_id!r} in job {job_id}")
            if shot.accepted_take:
                return {
                    "job_id": job_id, "shot_id": shot_id,
                    "status": "already_accepted", "accepted": True,
                    "take": shot.accepted_take, "new_credits": 0,
                    "message": (f"{shot_id} already has an accepted take. Nothing was replaced and "
                                f"no Flow generation/download was started; resume or render the job."),
                }
        elif candidates:
            shot = candidates[0]
        else:
            return {
                "job_id": job_id, "status": "all_shots_accepted",
                "accepted": True, "new_credits": 0,
                "message": "All shots are already accepted; run resume or render. No Flow action was started.",
            }

        project_url = self._flow_project_url(job_id)
        if not project_url:
            raise RuntimeError(
                "This job has no saved Flow project URL. Bind it first with: "
                f"python3 cli.py v3 flow-project {job_id} https://flow.google.com/project/<id>")

        pause = self.pause_state(job_id)
        baseline = {str(x) for x in (pause.get("baseline_signatures") or []) if str(x)}
        if not baseline and not allow_latest:
            raise RuntimeError(
                "This paused job has no saved pre-generation media baseline, so selecting the newest "
                "tile automatically could duplicate an earlier accepted shot. Wait for Flow access to "
                "reset and resume the same job, manually associate the confirmed MP4, or rerun this "
                "command with --allow-latest only after visually confirming the newest tile belongs to "
                f"{shot.shot_id}.")

        D = self.pm.dirs(job_id)
        os.makedirs(D["downloads"], exist_ok=True)
        recovered = os.path.join(D["downloads"], f"recovered_{shot.shot_id}.mp4")
        provider = FlowBrowserProvider()
        print(f"[Flow] Recovery-only mode: scanning {project_url} for the newest existing video; "
              "no generation will be submitted and no new credits will be requested.")
        try:
            result = provider.rescue_recent_project_video(
                f"AutoVideo-{job_id}", recovered, project_url=project_url,
                max_candidates=12, wait_s=max(5, int(wait_seconds or 0)),
                baseline_signatures=baseline)
            if not result or not result.get("path"):
                raise RuntimeError(
                    f"No downloadable video tile became available in {int(wait_seconds)}s. "
                    "The project is unchanged; wait for Flow to finish/reset, then run this recovery again.")
            bound = self._remember_flow_project_url(
                job_id, result.get("project_url") or provider.current_project_url())
            associated = self.associate_download(job_id, shot.shot_id, result["path"])
            qc = associated.get("qc", {})
            accepted = str(qc.get("decision", "")).upper() in ("ACCEPT", "REVIEW")
            refreshed = self.pm.load_manifest(job_id)
            refreshed.status = "planned" if accepted else "paused"
            self.pm.save_manifest(refreshed)
            self.db.upsert(job_id, status=refreshed.status,
                           flow_project=bound or project_url)
            pause.update({
                "recovery_completed_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
                "recovered_shot": shot.shot_id,
                "recovered_file": associated.get("take"),
                "recovery_qc": qc,
                "resolved": accepted,
            })
            _save_json(os.path.join(self.pm.job_dir(job_id), "pause_state.json"), pause)
            self.pm.log(job_id, "flow_existing_video_recovered", {
                "shot": shot.shot_id, "project_url": bound or project_url,
                "take": associated.get("take"), "qc": qc, "new_credits": 0})
            return {"job_id": job_id, "shot_id": shot.shot_id,
                    "project_url": bound or project_url, "new_credits": 0,
                    "accepted": accepted, **associated}
        finally:
            try:
                provider.close()
            except Exception:
                pass

    # ---------------- render ----------------
    def render_job(self, job_id: str, quality: str = "high", progress_cb=None) -> dict:
        from .render.timeline import build_timeline
        from .render.captions_ass import build_captions
        from .render.ffmpeg_renderer import render_ffmpeg
        from .audio.sound_design import plan_sfx, pick_music, pick_ambience
        from moviepy.editor import AudioFileClip

        from .progress import JobProgress
        progress = JobProgress(self.pm.job_dir(job_id), progress_cb)
        def prog(stage, pct, info=""):
            try:
                progress.emit(stage, pct, info)
            except Exception:
                pass

        m = self.pm.load_manifest(job_id)
        D = self.pm.dirs(job_id)
        settings = self._settings(job_id)
        preset = load_preset(m.preset)
        prog("🎞️ Building timeline...", 85)
        presentation = resolve_presentation(settings)
        m.voiceover_enabled = presentation.voiceover
        voice_path = os.path.join(D["narration"], "voice.mp3")
        voice = voice_path if presentation.voiceover else None
        if voice:
            if not os.path.isfile(voice):
                raise RuntimeError("Voiceover is enabled but no narration exists. Run Resume to prepare it, or disable voiceover for a music-only/silent edit.")
            c = AudioFileClip(voice)
            ndur = c.duration
            c.close()
        else:
            ndur = visual_duration(m)
        tl = build_timeline(m, os.path.join(D["flow"], "shots"), ndur, hard_cuts=True)
        from .production import apply_overrides, save as save_review
        tl = apply_overrides(D["root"], tl)
        repaired = {s["shot_id"] for s in tl["segments"] if s.get("local_repair")}
        _save_json(os.path.join(D["render"], "timeline.json"), tl)
        from .render.coverage import audit_coverage
        coverage = audit_coverage(tl["segments"], ndur)
        # A rejected take must not be silently used even if a file exists.
        for shot in m.shots:
            if shot.status != "accepted" and shot.shot_id not in repaired:
                coverage["issues"].append(f"{shot.shot_id}: shot is not accepted")
        coverage["passed"] = not coverage["issues"]
        _save_json(os.path.join(D["render"], "coverage_qc.json"), coverage)
        if not coverage["passed"]:
            prog("⛔ Coverage QC stopped render before encoding", 85,
                 "See render/coverage_qc.json; replace the listed media or create a corrected plan. Existing job and Flow project are preserved.")
            raise RuntimeError("Coverage QC: " + "; ".join(coverage["issues"]) +
                               ". No new generation submitted. See render/coverage_qc.json.")
        words_p = voice_path + ".words.json"
        words = json.load(open(words_p, encoding="utf-8")) if voice and os.path.exists(words_p) else []
        script_text = ""
        script_data = {}
        try:
            script_data = json.load(open(os.path.join(D["root"], "script.json"), encoding="utf-8"))
            script_text = str(script_data.get("narration", "") or "")
        except Exception:
            script_text = ""
        if presentation.voiceover:
            if not words:
                from .captions import get_word_timestamps
                words = get_word_timestamps(
                    voice,
                    model_size=str(settings.get("caption_local_model", "small") or "small"),
                    provider=str(settings.get("caption_provider", "auto") or "auto"),
                    script_text=script_text, language=m.language,
                    groq_model=str(settings.get("caption_model", "whisper-large-v3-turbo") or "whisper-large-v3-turbo"),
                    align_script=bool(settings.get("caption_align_script", True)),
                ) or []
            elif script_text and bool(settings.get("caption_align_script", True)):
                from .captions import align_words_to_script
                words = align_words_to_script(script_text, words, ndur)
            cap = build_captions(words, os.path.join(D["captions"], "captions"),
                                 template=preset.get("caption_style", "HORMOZI"),
                                 aspect=m.aspect, W=m.width, H=m.height, duration=ndur)
        else:
            cap = {"ass": None, "srt": None, "events": 0, "warnings": [],
                   "disabled": True, "reason": "voiceover_disabled"}
        if cap.get("warnings"):
            self.pm.log(job_id, "caption_timing_warning", {"warnings": cap["warnings"]})
            prog("⚠️ Caption timing needs review", 87, "; ".join(cap["warnings"]))

        pro_mode = str(settings.get("production_mode", "legacy") or "legacy").lower() == "youtube_pro"
        caption_display = presentation.captions
        burn_ass = cap["ass"] if caption_display == "full" else None

        # v5.6 graphics replace the dead-end permanent transcript in YouTube
        # production mode. Full SRT/ASS files are still generated for YouTube CC.
        overlays = []
        graphics_enabled = presentation.text_cards
        if graphics_enabled or bool(settings.get("watermark", False)):
            try:
                from .render.graphics import build_overlay_assets
                overlays = build_overlay_assets(
                    m, script_data, os.path.join(D["render"], "graphics"),
                    channel_name=str(settings.get("channel_name", "") or ""),
                    logo_path=str(settings.get("channel_logo", "") or ""),
                    show_watermark=bool(settings.get("watermark", False)),
                    actual_duration=ndur, text_cards_enabled=graphics_enabled,
                    style=presentation.card_style
                )
                _save_json(os.path.join(D["root"], "graphics_plan.json"), overlays)
            except Exception as ge:
                overlays = []
                self.pm.log(job_id, "graphics_overlay_failed", {"error": str(ge)[:300]})

        from .render.structured_graphics import build_structured_overlays
        from .render.typography import resolve_style
        card_style = resolve_style(presentation.card_style, m)
        custom = (build_structured_overlays(D["root"], ndur, m.width, m.height, style=card_style)
                  if graphics_enabled else [])
        if custom:
            overlays = [e for e in overlays if e.get("kind") == "watermark"] + custom
            _save_json(os.path.join(D["root"], "graphics_plan.json"), overlays)

        # Always update the plan, so a disabled overlay is not resurrected by
        # stale PNGs or a previous graphics_plan on a later render.
        _save_json(os.path.join(D["root"], "graphics_plan.json"), overlays)
        music_mode = presentation.music_mode
        music_meta = {"path": None, "source": "off"}
        if music_mode != "off":
            if presentation.music_path:
                local_music = os.path.abspath(os.path.expanduser(presentation.music_path))
                if not os.path.isfile(local_music):
                    raise ValueError("Background music file does not exist: " + local_music)
                music_meta = {"path": local_music, "source": "local-user-supplied", "license": "User must verify music rights"}
            else:
                try:
                    from .audio.music_provider import ensure_background_music
                    mood = str(settings.get("music_mood", "") or m.audio_mood or preset.get("music_style", "")
                               or f"soft motivational {m.content_type} instrumental")
                    music_meta = ensure_background_music(mood, D["audio"], mode=music_mode)
                except Exception as me:
                    music_meta = {"path": None, "source": "error", "error": str(me)[:300]}
        music = music_meta.get("path")
        # Legacy local music remains available when the explicit provider is off.
        if not music and not pro_mode and music_mode != "off":
            music = pick_music(preset.get("music_style", ""))
        if not voice and music_mode != "off" and not music:
            raise RuntimeError("Music-only edit requested but no music was obtained. Choose a licensed local track or explicitly select music off for a silent video. Accepted visuals were not regenerated.")
        amb = pick_ambience(m.shots[0].environment if m.shots else "") if presentation.ambience else None
        sfx = plan_sfx(words, tl["segments"]) if presentation.sound_effects else []
        audio_expected = bool(voice or music or amb or any(e.get("path") for e in sfx))
        _save_json(os.path.join(D["audio"], "sound_plan.json"),
                   {"music": music_meta if music_meta.get("path") else music, "ambience": amb, "sfx": sfx,
                    "caption_display": caption_display, "overlays": len([x for x in overlays if x.get("path")]),
                    "voiceover_enabled": presentation.voiceover, "text_cards_enabled": graphics_enabled,
                    "audio_expected": audio_expected, "music_volume": presentation.music_volume,
                    "audio_mode": "voiceover" if voice else ("instrumental" if audio_expected else "silent")})
        prog("🎬 Rendering 1080p YouTube master..." if pro_mode else "🎬 Rendering 1080p...", 92)
        out = os.path.join(D["render"], f"{job_id}-final.mp4")
        from .publishing import destination_profile
        delivery = destination_profile(settings['destination']) if settings.get('destination') else {}
        try:
            r = render_ffmpeg(tl["segments"], voice, out, W=m.width, H=m.height,
                              fps=delivery.get('fps',24), audio_bitrate=delivery.get('audio_kbps',192),
                              ass_path=burn_ass, music=music, ambience=amb,
                              sfx=sfx, overlays=overlays, music_volume=presentation.music_volume,
                              stereo_master=True, quality=quality,
                              safe_concat=True, loop_short_segments=True,
                              progress_cb=lambda p, detail="": prog("🎬 Rendering", 92 + (float(p) * 0.06), detail))
            renderer = "ffmpeg"
            # Some WSL/libass builds advertise the subtitles filter but fail at
            # runtime. Keep the successful FFmpeg master edit/audio and replace
            # only the caption burn with a Pillow/MoviePy overlay pass.
            if r.get("caption_fallback_required") and words:
                from .video_builder import burn_wordpop_captions
                base = os.path.join(D["render"], f"{job_id}-ffmpeg-base.mp4")
                try:
                    if os.path.exists(base):
                        os.remove(base)
                    os.replace(out, base)
                    burn_wordpop_captions(base, words, out, vertical=(m.aspect == "9:16"))
                    renderer = "ffmpeg+caption-overlay"
                    try:
                        os.remove(base)
                    except Exception:
                        pass
                    prog("✅ FFmpeg master preserved; captions added with safe overlay renderer.", 94)
                except Exception as ce:
                    # The master edit is still valid. Restore it before allowing
                    # the outer fallback to decide whether a full rebuild is needed.
                    if not os.path.exists(out) and os.path.exists(base):
                        os.replace(base, out)
                    raise RuntimeError(f"Caption overlay fallback failed: {ce}")
        except Exception as e:
            render_error = str(e)
            render_error_lower = render_error.lower()
            integrity_failure = any(marker in render_error_lower for marker in (
                "visual qc detected", "motion qc detected",
                "refusing to publish a stuck render", "video stream covers only",
                "safe recovery watchdog",
                "encoder stalled",
            ))
            if integrity_failure:
                # MoviePy re-encodes the same damaged/timing-starved inputs and
                # used to sit silently for 30+ minutes. The FFmpeg renderer has
                # already tried a hard-cut, motion-looping recovery at this point;
                # stop clearly instead of pretending a second full rebuild can
                # repair corrupt or nearly-static source media.
                prog("⛔ Render QC stopped an unhealthy video", 98,
                     render_error[:500] +
                     " — replace/recover the affected source clip(s), then run Resume/Render again.")
                raise RuntimeError(
                    "Render recovery stopped: the output is still blank, truncated, or frozen after "
                    "the bounded safe recovery pass. AutoVideoAI did not publish it and did not start "
                    "the slow MoviePy fallback. Replace/recover the affected source clip(s), then "
                    f"resume the same job. Technical detail: {render_error}") from e
            prog(f"FFmpeg pipeline failed ({str(e)[:80]}), trying full MoviePy fallback...", 93)
            r = self._render_moviepy_fallback(m, D, tl, voice, out,
                                              music=music, ambience=amb, sfx=sfx, overlays=overlays,
                                              words=words, captions=caption_display == "full",
                                              music_volume=presentation.music_volume, quality=quality)
            renderer = "moviepy-fallback"
        # metadata bundle + planned-vs-actual generation audit
        _save_json(os.path.join(D["root"], "shots.json"), [s.model_dump() for s in m.shots])
        fallback_shots = [s for s in m.shots if s.fallback_reason]
        accepted_shots = [s for s in m.shots if s.status == "accepted"]
        unaccepted_shots = [s for s in m.shots if s.status != "accepted"]
        actual_counts = {}
        for s in accepted_shots:
            ap = s.actual_provider or s.provider or "unknown"
            actual_counts[ap] = actual_counts.get(ap, 0) + 1
        flow_credits = sum(int(s.credits_spent or 0) for s in accepted_shots
                           if (s.actual_provider or s.provider) == "flow")
        generation_summary = {
            "shots": len(m.shots),
            "accepted": len(accepted_shots),
            "unaccepted": len(unaccepted_shots),
            "unaccepted_shots": [s.shot_id for s in unaccepted_shots],
            "planned_flow_scenes": sum(1 for s in m.shots if s.media_strategy == "flow_video"),
            "actual_provider_counts": actual_counts,
            "fallback_count": len(fallback_shots),
            "actual_flow_credits": flow_credits,
            "credit_basis": "observed-or-model-estimate",
            "fallbacks": [{"shot_id": s.shot_id, "planned": s.provider,
                           "actual": s.actual_provider or s.provider,
                           "reason": s.fallback_reason} for s in fallback_shots],
        }
        _save_json(os.path.join(D["root"], "generation_summary.json"), generation_summary)
        # Collect stock/music provenance for later YouTube descriptions and
        # license audits. Browser/API helpers write sidecars next to downloaded
        # media; the finished job consolidates them here.
        asset_sources = []
        for base in (D.get("flow"), D.get("audio")):
            if not base or not os.path.isdir(base):
                continue
            for root, _, files in os.walk(base):
                for fn in files:
                    if not fn.endswith(".source.json"):
                        continue
                    try:
                        meta = json.load(open(os.path.join(root, fn), encoding="utf-8"))
                        if isinstance(meta, dict):
                            asset_sources.append(meta)
                    except Exception:
                        pass
        if "music_meta" in locals() and isinstance(music_meta, dict) and music_meta.get("path"):
            if not any(x.get("path") == music_meta.get("path") for x in asset_sources if isinstance(x, dict)):
                asset_sources.append(music_meta)
        _save_json(os.path.join(D["root"], "asset_sources.json"), asset_sources)
        try:
            lines = ["# Media credits / provenance", ""]
            for a in asset_sources:
                src = str(a.get("source", "media"))
                creator = str(a.get("creator", "") or "").strip()
                page = str(a.get("page_url") or a.get("source_page") or "").strip()
                lic = str(a.get("license", "") or "").strip()
                q = str(a.get("query", "") or "").strip()
                line = f"- {src}" + (f" — {creator}" if creator else "")
                if lic:
                    line += f" — {lic}"
                if q:
                    line += f" — query: {q}"
                if page:
                    line += f" — {page}"
                lines.append(line)
            open(os.path.join(D["root"], "asset_credits.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
        except Exception:
            pass
        with open(os.path.join(D["root"], "generation_summary.md"), "w", encoding="utf-8") as gf:
            gf.write(f"# Generation Summary\n\nShots: {len(m.shots)}\n\n")
            gf.write(f"Planned Flow motion scenes: {generation_summary['planned_flow_scenes']}\n\n")
            gf.write(f"Actual provider counts: {actual_counts}\n\n")
            gf.write(f"Actual/observed Flow credits: {generation_summary['actual_flow_credits']}\n\n")
            gf.write(f"Fallbacks: {len(fallback_shots)}\n")
            for fs in fallback_shots:
                gf.write(f"- {fs.shot_id}: {fs.provider} -> {fs.actual_provider or fs.provider}: {fs.fallback_reason}\n")

        final_warnings = list(tl["warnings"])
        if fallback_shots:
            final_warnings.append(f"{len(fallback_shots)} scene(s) used runtime fallback; see generation_summary.md")
        if unaccepted_shots:
            final_warnings.append(f"{len(unaccepted_shots)} planned shot(s) were not accepted; timeline used visual bridging where needed")
        if renderer == "moviepy-fallback":
            final_warnings.append("FFmpeg master render failed; full MoviePy fallback was used")
        elif renderer == "ffmpeg+caption-overlay":
            final_warnings.append("FFmpeg master render succeeded; libass caption burn was replaced by safe Pillow overlay")

        # v5.1 visual-diversity QC is report-only: do not destroy a completed
        # render, but make excessive near-duplication visible in the job audit.
        try:
            from .qc.visual_diversity import analyze_storyboard
            diversity = analyze_storyboard(D["storyboard"])
            _save_json(os.path.join(D["root"], "visual_diversity.json"), diversity)
            if diversity.get("unique_ratio", 1.0) < 0.65:
                final_warnings.append(
                    f"Low storyboard visual diversity ({diversity.get('unique_ratio', 0):.0%} unique); "
                    "future same-topic generations will force more composition changes")
        except Exception:
            diversity = {}
        editorial_qc = script_data.get("editorial_qc") or {}
        dynamic_actual = int(actual_counts.get("flow", 0) or 0) + int(actual_counts.get("stock", 0) or 0) + int(actual_counts.get("movieflow", 0) or 0)
        overlay_count = len([x for x in overlays if x.get("path")]) if "overlays" in locals() else 0
        readiness_checks = {
            "editorial_qc": bool(editorial_qc.get("passed", False)),
            "ai_script": not str(script_data.get("source", "planner")).startswith("planner"),
            "all_shots_accepted": not bool(unaccepted_shots),
            "captions_present": not presentation.voiceover or bool(cap.get("events", 0)),
            "caption_timing": not bool(cap.get("warnings")),
            "visual_diversity": (not diversity or float(diversity.get("unique_ratio", 1.0)) >= 0.70),
            "render_integrity": True,  # render_ffmpeg refuses broken black/missing outputs
        }
        if pro_mode:
            readiness_checks.update({
                "dynamic_media": dynamic_actual >= max(3, int(round(float(m.target_seconds or 300) / 60.0))),
                "editorial_graphics": not graphics_enabled or overlay_count >= 3,
                "stereo_master": True,
                "outro_cta": (not graphics_enabled or m.content_type in {"kids_story", "kids", "cartoon_story", "cinematic_story", "storytelling"}
                              or any(x.get("kind") == "outro" and x.get("path") for x in overlays)),
            })
        publish_warnings = list(cap.get("warnings", []))
        failed_cards = [e for e in overlays if e.get("error")]
        if failed_cards:
            publish_warnings.extend("Text card needs review: " + e['error'] for e in failed_cards)
            readiness_checks["card_layout"] = False
        if fallback_shots:
            publish_warnings.append(f"{len(fallback_shots)} planned AI-motion scene(s) used fallback media")
        if diversity and float(diversity.get("unique_ratio", 1.0)) < 0.80:
            publish_warnings.append(f"Visual diversity is {float(diversity.get('unique_ratio', 0)):.0%}; 80%+ is preferred")
        if pro_mode and dynamic_actual < 5:
            publish_warnings.append(f"Only {dynamic_actual} real/AI motion clip(s) made the final edit; 5+ is preferred for a five-minute video")
        if pro_mode and music_mode != "off" and not music:
            publish_warnings.append("Background music was requested but no royalty-free asset was obtained; add a local track or retry browser lookup")
        if pro_mode and not str(settings.get("channel_name", "") or "").strip():
            publish_warnings.append("No channel name supplied; watermark/brand identity is incomplete")
        publish_readiness = {
            "status": "NEEDS_EDITORIAL_REVIEW" if all(readiness_checks.values()) else "NEEDS_REVIEW",
            "passed": False,
            "technical_and_recipe_checks_passed": all(readiness_checks.values()),
            "checks": readiness_checks,
            "warnings": publish_warnings,
            "script_source": script_data.get("source", "unknown"),
            "renderer": renderer,
            "production_mode": settings.get("production_mode", "legacy"),
            "caption_display": caption_display,
            "voiceover_enabled": presentation.voiceover, "text_cards_enabled": graphics_enabled,
            "text_card_style": card_style,
            "checks_not_applicable": (["captions_present", "caption_timing"] if not voice else [])
                                     + (["editorial_graphics", "outro_cta"] if not graphics_enabled else []),
            "graphics_overlays": overlay_count,
            "dynamic_media_clips": dynamic_actual,
            "background_music": music_meta if "music_meta" in locals() else {"path": music, "source": "legacy"},
        }
        _save_json(os.path.join(D["root"], "publish_readiness.json"), publish_readiness)
        save_review(os.path.join(D["root"], "production", "review.json"),
                    {"status": "RENDER_CHANGED", "next_action": "Run production-check for this render"})
        details = (f"Title: {m.topic}\nProfile: {m.profile} | Preset: {m.preset}\n"
                   f"Size: {m.width}x{m.height} | Renderer: {renderer}\nShots: {len(m.shots)} "
                   f"accepted: {m.accepted_count()}\nActual providers: {actual_counts}\n"
                   f"Fallbacks: {len(fallback_shots)} | Flow credits: {generation_summary['actual_flow_credits']}\n"
                   f"Publish readiness: {publish_readiness['status']}\n"
                   f"Warnings: {final_warnings + publish_warnings}\n")
        open(os.path.join(D["root"], "details.txt"), "w", encoding="utf-8").write(details)
        m.status = "done"
        self.pm.save_manifest(m)
        self.db.upsert(job_id, status="done", render_status="done", final_path=out,
                       accepted_shots=m.accepted_count())
        prog(f"Render complete — {publish_readiness['status']}; providers={actual_counts} fallbacks={len(fallback_shots)}", 100)
        return {"job_id": job_id, "status": "done", "video": out, "renderer": renderer,
                "captions": cap, "generation_summary": generation_summary,
                "visual_diversity": diversity, "publish_readiness": publish_readiness,
                "graphics": overlays if "overlays" in locals() else [],
                "background_music": music_meta if "music_meta" in locals() else {},
                "warnings": final_warnings + publish_warnings}

    def _render_moviepy_fallback(self, m, D, tl, voice, out, **presentation) -> dict:
        from .render.moviepy_renderer import render_moviepy
        return render_moviepy(tl["segments"], voice, out, total=tl["total"],
                              W=m.width, H=m.height, **presentation)

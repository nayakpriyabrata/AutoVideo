"""
AutoVideoAI v4.0 - Storyboard Economy Video Factory dashboard.
Pages: CREATE / STORYBOARD / DIRECTOR REVIEW / QUEUE / FLOW SESSION /
       ASSETS / RENDER / HISTORY / SETTINGS (+ Quick v2).
"""
import os
import glob
import json
import threading
import time
import yaml
import streamlit as st
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
if not any(os.getenv(k) for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY")):
    here = Path(__file__).resolve().parent
    candidates = [Path.home() / ".config" / "autovideoai" / ".env"]
    try:
        candidates += sorted(here.parent.glob("AutoVideoAI-v*/.env"),
                             key=lambda q: q.stat().st_mtime, reverse=True)
    except Exception:
        pass
    for env_path in candidates:
        try:
            if env_path.is_file() and env_path.resolve() != (here / ".env").resolve():
                load_dotenv(env_path, override=False)
                if any(os.getenv(k) for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY")):
                    break
        except Exception:
            continue
from engine.env_config import load_environment
ENV_REPORT = load_environment(Path(__file__).resolve().parent)

from engine.version import get_version
from engine.support_report import build_support_report
APP_VERSION = get_version()
st.set_page_config(page_title=f"AutoVideoAI v{APP_VERSION} Studio 🎬", page_icon="🎬", layout="wide")

from engine.factory import Factory, AssistedNeeded, load_preset
from engine.project.database import JobDB
from engine.routing.provider_router import NeedsDecision
from engine.studio_config import DEFAULTS, THEMES, config_to_factory_kwargs

F = Factory()
DB = JobDB()


def _flow_pause_setting_default():
    """Read only the non-sensitive global opt-in preference for new jobs."""
    try:
        with open("config/user_settings.yaml", encoding="utf-8") as handle:
            value = (yaml.safe_load(handle) or {}).get("flow_pause_on_unresolved_request", False)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    except Exception:
        return False


PROFILES = ["STORYBOARD_ECONOMY", "FLOW_CINEMATIC", "FLOW_BALANCED", "FLOW_ECONOMY", "LOCAL_FREE", "FREE_HYBRID", "MANUAL_DIRECTOR"]
PRESETS = sorted([os.path.splitext(f)[0] for f in os.listdir("config/presets") if f.endswith(".yaml")])
CONTENT_TYPES = ["education", "storytelling", "cinematic_story", "documentary", "motivation",
                 "technology", "history", "finance", "kids_story", "advertisement",
                 "product_demo", "news_explainer"]
VOICES = ["en-IN-PrabhatNeural", "en-IN-NeerjaNeural", "en-US-GuyNeural", "en-US-AriaNeural",
          "en-GB-RyanNeural", "en-GB-SoniaNeural", "hi-IN-MadhurNeural", "hi-IN-SwaraNeural"]

if "job_id" not in st.session_state:
    st.session_state.job_id = None

# ---------------- sidebar ----------------
st.sidebar.title(f"🎬 AutoVideoAI v{APP_VERSION} Studio")
mode_badge = {"STORYBOARD_ECONOMY": "🌱", "FLOW_CINEMATIC": "💎", "FLOW_BALANCED": "⚖️", "FLOW_ECONOMY": "💰",
              "LOCAL_FREE": "🖥️", "FREE_HYBRID": "🆓", "MANUAL_DIRECTOR": "🎥"}
page = st.sidebar.radio("Navigate", ["STUDIO", "MINI REELS", "CREATE", "STORYBOARD", "DIRECTOR REVIEW", "QUEUE",
                                     "FLOW SESSION", "CLIP STUDIO", "CONTENT INBOX", "CHARACTER LIBRARY", "AI RECREATE", "PUBLISHING DESK", "PRODUCTION QC", "ASSETS", "RENDER", "HISTORY",
                                     "SETTINGS", "Quick (v2)"])
st.sidebar.divider()
jobs = DB.list(30)
job_ids = [j["job_id"] for j in jobs]
sel = st.sidebar.selectbox("Active job", ["(none)"] + job_ids,
                           index=([ "(none)"] + job_ids).index(st.session_state.job_id) if st.session_state.job_id in job_ids else 0)
st.session_state.job_id = None if sel == "(none)" else sel
if st.session_state.job_id:
    j = DB.get(st.session_state.job_id)
    if j:
        st.sidebar.caption(f"Status: **{j['status']}** | {j['profile']} | ✅{j['accepted_shots']} ❌{j['rejected_shots']}")


_pause_panels = set()


def pause_panel(job_id, reason=""):
    """Actionable recovery controls for a durable paused/assisted job."""
    if job_id in _pause_panels:
        return
    _pause_panels.add(job_id)
    state = F.pause_state(job_id)
    if not state:
        try:
            m = F.pm.load_manifest(job_id)
            pending = [s for s in m.shots if not s.accepted_take and
                       s.status in ("failed", "generating", "planned", "approved", "qc")]
            shot = pending[0] if pending else None
            if shot:
                state = F._write_pause_state(
                    job_id, shot.shot_id,
                    reason or "This saved job is paused and can be recovered/resumed.",
                    kind="legacy_pause_recovery")
        except Exception:
            state = {}
    if not state:
        st.info("No unfinished Flow shot was found for this job.")
        return

    accepted = state.get("accepted_shots", 0)
    total = state.get("total_shots", 0)
    shot_id = state.get("shot_id", "")
    kind = state.get("kind", "flow_recovery")
    st.warning(f"⏸️ Job paused at `{shot_id}` · {accepted}/{total} accepted shots are saved.")
    st.write(state.get("reason") or reason or "Flow needs attention before the job can continue.")
    if kind == "flow_usage_limit":
        st.info("Flow reported a usage/rate limit. Your displayed credit balance can still be positive. "
                "Do not create a new job: wait for access to reset, or recover a video that already exists in the project.")
    project_url = state.get("flow_project_url")
    if project_url:
        st.markdown(f"[Open the saved Flow project]({project_url})")

    safe_recovery = bool(state.get("safe_automatic_recovery"))
    if safe_recovery:
        st.markdown("**Safest next step:** scan for a video newer than the saved pre-generation "
                    "baseline. This does not submit a prompt and requests **0 new credits**.")
        c1, c2 = st.columns(2)
        if c1.button("♻️ Recover proven-new Flow video — 0 new credits",
                     key=f"recover-existing-{job_id}-{shot_id}", type="primary"):
            with st.spinner("Scanning the saved Flow project for a new completed video (up to 120 seconds)..."):
                try:
                    result = F.recover_flow_video(job_id, shot_id=shot_id or None, wait_seconds=120)
                    if result.get("accepted"):
                        st.success(f"Recovered `{result['shot_id']}` and passed QC. Click Resume to continue/render.")
                    else:
                        st.warning("A video was recovered, but QC rejected it. Review the QC report before retrying recovery.")
                    st.json({"shot": result.get("shot_id"), "new_credits": 0,
                             "qc": result.get("qc", {})})
                except Exception as e:
                    st.error(f"Recovery did not find a usable new video yet: {e}")
        resume_clicked = c2.button("▶️ Resume saved job", key=f"resume-paused-{job_id}")
    else:
        st.info("You opted in to pausing unresolved Flow requests. Resume checks the saved request for the exact pending image or video; image downloads retry without a new prompt, and one replacement is allowed only after the original asset is proven absent (may use image credits). "
                "With this option off, auto-mode images use the free fallback; strict Flow/video requests fail without another generation and remain available for explicit Resume. "
                "See the request's recovery.json diagnostic if the asset cannot be matched.")
        resume_clicked = st.button("▶️ Retry saved request and resume",
                                   key=f"resume-paused-{job_id}", type="primary")
    if resume_clicked:
        st.session_state.pending_resume_job = job_id
        st.rerun()

    st.caption("CLI recovery (safe to repeat):")
    # Old saved pause states may still contain the retired manual MP4 action.
    actions = [a for a in state.get("actions", [])
               if " v3 associate " not in a.get("command", "")]
    if actions:
        st.code("\n".join(a.get("command", "") for a in actions if a.get("command")), language="bash")
    with st.expander("Export pause diagnostics — no browser or generation requests"):
        st.caption("Includes the pause reason, recent log lines and pending Flow request evidence. "
                   "Excludes .env, settings, browser profiles and media; redacts known credentials and signed URL values. "
                   "Review the report before sharing it.")
        try:
            report = build_support_report(F.pm.job_dir(job_id))
            st.download_button("⬇️ Download redacted pause report", json.dumps(report, indent=2, ensure_ascii=False),
                               file_name=f"{job_id}-support-report.json", mime="application/json",
                               key=f"support-report-{job_id}")
        except (ValueError, OSError) as exc:
            st.warning(f"Diagnostic export unavailable: {exc}")
        st.code(f"python3 cli.py v3 support-report {job_id}", language="bash")


def run_with_ui(job_id, dry_label):
    bar = st.progress(0)
    status = st.empty()
    logbox = st.empty()
    def refresh_live_view():
        try:
            log_dir = os.path.join(F.pm.job_dir(job_id), "logs")
            progress_path = os.path.join(log_dir, "progress.json")
            if os.path.exists(progress_path):
                event = json.loads(Path(progress_path).read_text(encoding="utf-8"))
                status.info(f"{event.get('stage', 'Running')} {event.get('info', '')} · "
                            f"elapsed {event.get('elapsed', '--:--:--')}")
                bar.progress(min(100, int(float(event.get("percent", 0) or 0))))
            path = os.path.join(log_dir, "runtime.log")
            if os.path.exists(path):
                lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
                logbox.code("\n".join(lines[-18:]), language="text")
        except Exception:
            pass
    box = {}
    def worker():
        try:
            box["result"] = F.run_job(job_id, progress_cb=None)
        except BaseException as exc:
            box["error"] = exc
    try:
        with st.spinner(f"{dry_label} Running production... (Flow jobs take a while)"):
            thread = threading.Thread(target=worker, name=f"autovideo-{job_id[-12:]}", daemon=True)
            thread.start()
            while thread.is_alive():
                refresh_live_view()
                time.sleep(0.75)
            thread.join()
            refresh_live_view()
            if "error" in box:
                raise box["error"]
            r = box.get("result", {})
        bar.progress(100)
        result_message = f"{r.get('status')}: {r.get('message', r.get('video', ''))}"
        if r.get("status") == "failed":
            status.error(result_message)
        elif r.get("status") == "paused":
            status.warning(result_message)
        else:
            status.success(result_message)
        if r.get("status") == "failed" and r.get("resume"):
            st.caption("This request was not paused automatically. If you want to retry its exact recovery, run:")
            st.code(r["resume"], language="bash")
        if r.get("video"):
            st.video(r["video"])
            with open(r["video"], "rb") as f:
                st.download_button("⬇️ Download final MP4", f, file_name=os.path.basename(r["video"]))
        st.json({k: v for k, v in r.items() if k in ("job_id", "status", "renderer", "warnings")})
        if r.get("status") in ("paused", "assisted"):
            pause_panel(job_id, r.get("message", ""))
    except NeedsDecision as e:
        status.warning(f"⏸️ PAUSED (no silent downgrade): {e}")
        st.markdown("**Alternatives:**")
        for a in e.alternatives:
            st.write(f"- {a}")
        pause_panel(job_id, str(e))
    except AssistedNeeded as e:
        status.warning(f"🧑‍✈️ Assisted Flow Mode: {e.reason}")
        st.session_state.assisted = {"job_id": e.job_id, "shot_id": e.shot_id,
                                     "prompt": e.prompt, "watch_dir": e.watch_dir}
        pause_panel(job_id, e.reason)
    except Exception as e:
        status.error(f"Failed: {e}")
        if "Coverage QC:" in str(e):
            D = F.pm.dirs(job_id)
            coverage_path = os.path.join(D["render"], "coverage_qc.json")
            st.warning("The render stopped before encoding because at least one shot is not accepted. This is a deliberate review gate; no replacement media or Flow generation was submitted.")
            try:
                with open(coverage_path, encoding="utf-8") as handle:
                    coverage = json.load(handle)
                for issue in coverage.get("issues", []):
                    st.write(f"- {issue}")
                st.caption(f"Read-only report: `{coverage_path}`. Review the listed shot in STORYBOARD or DIRECTOR REVIEW, then render the same job after resolving its acceptance state.")
                with st.expander("Unaccepted shot statuses — no provider calls"):
                    manifest = F.pm.load_manifest(job_id)
                    rows = [{"shot_id": shot.shot_id, "status": shot.status,
                             "provider": shot.actual_provider or shot.provider,
                             "model": shot.actual_model or shot.model,
                             "accepted_take": shot.accepted_take or ""}
                            for shot in manifest.shots if shot.status != "accepted"]
                    st.dataframe(rows, use_container_width=True)
            except (OSError, ValueError, KeyError) as report_error:
                st.caption(f"Coverage details remain saved at `{coverage_path}` ({type(report_error).__name__}).")


def presentation_editor(job_id):
    from engine.presentation import resolve_presentation
    current = F._settings(job_id)
    recipe = resolve_presentation(current)
    with st.expander("🎵 Audio & text cards — edit without regenerating visuals", expanded=True):
        st.caption("These controls affect rendering only. They preserve accepted takes, Flow bindings and pending request journals. Speech captions are separate from text cards.")
        modes = ["Voiceover", "Music only", "Silent"]
        initial_mode = "Voiceover" if recipe.voiceover else ("Music only" if recipe.music_mode != "off" else "Silent")
        edit_audio_mode = st.radio("Output audio mode", modes, index=modes.index(initial_mode),
                                   horizontal=True, key=f"edit-audio-mode-{job_id}")
        voice_on = edit_audio_mode == "Voiceover"
        with st.form(f"presentation-{job_id}"):
            a, b, c = st.columns(3)
            a.caption("Voice synthesis enabled" if voice_on else "No voiceover / speech captions")
            cards_on = b.checkbox("Include text cards", value=recipe.text_cards)
            styles = ["auto", "bold", "playful", "clean"]
            card_style = c.selectbox("Card style", styles, index=styles.index(recipe.card_style))
            d, e = st.columns(2)
            music_modes = ["off", "auto", "local", "browser"]
            music_default = "auto" if edit_audio_mode == "Music only" and recipe.music_mode == "off" else recipe.music_mode
            music_mode = d.selectbox("Background music", music_modes, index=music_modes.index(music_default), disabled=edit_audio_mode == "Silent")
            music_path = e.text_input("Licensed local music path", value=recipe.music_path)
            f, g = st.columns(2)
            cap_modes = ["auto", "full", "none"]
            cap_display = f.selectbox("Speech captions", cap_modes, index=cap_modes.index(str(current.get('caption_display', 'auto'))), disabled=not voice_on)
            volume_default = .55 if not voice_on and recipe.voiceover else recipe.music_volume
            volume = g.slider("Music gain", 0.0, 1.0, volume_default, .01)
            h, i = st.columns(2)
            sounds = h.checkbox("Sound effects", value=recipe.sound_effects if voice_on else False, disabled=edit_audio_mode == "Silent")
            ambience = i.checkbox("Ambience", value=recipe.ambience if voice_on else False, disabled=edit_audio_mode == "Silent")
            if st.form_submit_button("Save audio & text choices"):
                F.set_presentation_options(job_id, voiceover_enabled=voice_on,
                                           text_cards_enabled=cards_on, text_card_style=card_style,
                                           background_music="off" if edit_audio_mode == "Silent" else music_mode, background_music_path=music_path,
                                           caption_display=cap_display if voice_on else "none", music_volume=volume,
                                           sound_effects_enabled=sounds if edit_audio_mode != "Silent" else False,
                                           ambience_enabled=ambience if edit_audio_mode != "Silent" else False)
                st.success("Saved. Use Render now below. No new visual generation was submitted.")
        preview_style = st.selectbox("Preview typography", ["bold", "playful", "clean"], key=f"card-preview-style-{job_id}")
        if st.button("Preview card — local only", key=f"card-preview-{job_id}"):
            from engine.render.graphics import OverlayEvent, render_overlay_png
            from PIL import Image
            preview = os.path.join(F.pm.dirs(job_id)['render'], 'card-style-preview.png')
            event = OverlayEvent('keypoint', 0, 3, 'Tiny steps. Big adventures.')
            render_overlay_png(event, preview, 540, 960, style=preview_style)
            with Image.open(preview) as image:
                st.image(image, caption="Transparent overlay preview; the video remains visible behind it.")


def pipeline_view(job_id):
    try:
        m = F.pm.load_manifest(job_id)
    except Exception:
        return
    D = F.pm.dirs(job_id)
    from engine.presentation import resolve_presentation
    recipe = resolve_presentation(F._settings(job_id))
    steps = [("SCRIPT", os.path.exists(os.path.join(D["root"], "script.json"))),
             ("VOICE", os.path.exists(os.path.join(D["narration"], "voice.mp3")) if recipe.voiceover else "OFF"),
             ("STORYBOARD", bool(m.shots)),
             ("FLOW", f"{m.accepted_count()}/{len(m.shots)}"),
             ("QC", f"{m.accepted_count()}/{len(m.shots)}"),
             ("RENDER", m.status == "done")]
    cols = st.columns(len(steps))
    for (name, ok), c in zip(steps, cols):
        c.metric(name, "✓" if ok is True else ("·" if ok is False else ok))


# ================= STUDIO =================
queued_resume = st.session_state.pop("pending_resume_job", None)
if queued_resume:
    run_with_ui(queued_resume, "")

if page == "STUDIO":
    st.title("🎛️ AutoVideoAI Studio")
    st.caption("Create from friendly controls. The same settings can be saved in video_config.yaml and reproduced from CLI.")
    studio_audio_mode = st.radio("Audio mode", ["Voiceover", "Music only", "Silent"], horizontal=True, key="studio-audio-mode")
    studio_voice_on = studio_audio_mode == "Voiceover"
    st.caption("Music only skips voice synthesis and speech captions. Silent also turns music, ambience and SFX off. Text cards can be switched independently.")
    from engine.languages import LANGUAGES
    language_code = st.selectbox('Production language', list(LANGUAGES), format_func=lambda code: LANGUAGES[code].label)
    destination = st.selectbox('Destination recipe', ['automatic','instagram_reel','facebook_reel','youtube_short','youtube_long'])
    approved_plan_path = st.text_input('Approved script/storyboard JSON (optional)', help='Use CONTENT INBOX or your own writer, review the JSON, then approve it. Imported text is not automatically rewritten.')
    narration_input_path = st.text_input('Imported native narration file (optional)', help='An audio file you own/are licensed to use; useful for native-language review.')
    with st.form("studio-create"):
        topic = st.text_input("Topic / idea", placeholder="5 habits winners build for a successful life")
        a, b, c, d = st.columns(4)
        production_mode = a.selectbox("Production mode", ["youtube_pro", "reels_pro", "legacy"])
        theme = b.selectbox("Theme", list(THEMES))
        duration = c.number_input("Duration (seconds)", 10, 7200, 45 if production_mode == "reels_pro" else 300)
        profile = d.selectbox("Generation profile", PROFILES, index=0)
        e, f, g = st.columns(3)
        script_provider = e.selectbox("Script provider", ["auto", "gemini-web", "gemini", "groq", "openai", "planner"])
        tts_provider = f.selectbox("TTS", ["auto", "gemini", "gemini-lite", "groq", "elevenlabs", "kokoro", "edge", "gtts"], disabled=not studio_voice_on)
        render_quality = g.selectbox("Render quality", ["high", "standard", "preview"])
        with st.expander("Flow, visuals, audio and branding", expanded=True):
            h, i, j = st.columns(3)
            flow_workers = h.selectbox("Parallel Flow image workers", [1, 2, 3], index=0,
                                       disabled=profile == "STORYBOARD_ECONOMY",
                                       help="Used by per-shot candidate image generation in Flow profiles. Storyboard Economy's master/continuity-frame pipeline is sequential and does not use this setting. Each worker uses a separate Flow project and browser tab/profile to keep asset matching safe. Start with 1; Google may throttle 2–3.")
            if profile == "STORYBOARD_ECONOMY":
                st.caption("Parallel workers are not used by Storyboard Economy's continuity-first frame pipeline.")
            frame_source = i.selectbox("Frame source", ["auto", "flow", "free"])
            flow_approval = j.selectbox("Flow credit approval", ["once", "manual", "always"])
            flow_project_url = st.text_input("Existing Google Flow project URL (optional)",
                                             placeholder="https://flow.google.com/project/<uuid>",
                                             help="Stored with the job and automatically reused on resume.")
            flow_pause_on_unresolved_request = st.checkbox(
                "Pause when a Flow request cannot be safely recovered (opt-in)",
                value=_flow_pause_setting_default(),
                help="Off by default: ambiguous images use the free fallback in auto mode; strict image/video requests fail without PAUSED status and can be explicitly resumed. On: save the request and pause for your choice. Recovery retries download-only first; at most one replacement may use image credits, and only after two full scans prove the original absent.")
            k, l, n = st.columns(3)
            reuse_mode = k.selectbox("Flow reuse scope", ["exact", "topic", "project"])
            gemini_cleanup = l.selectbox("Gemini temporary chat", ["delete-after-read", "keep"])
            background_music = n.selectbox("Background music", ["off", "auto", "local", "browser"],
                                           index=1 if studio_audio_mode == "Music only" else 0,
                                           disabled=studio_audio_mode == "Silent")
            music_path = st.text_input("Licensed local music path (optional)", help="Use a WSL/Linux path. Choose local above to avoid browser lookup.")
            pc1, pc2, pc3 = st.columns(3)
            text_cards_enabled = pc1.checkbox("Include text cards", value=True,
                                               help="Title, chapter, key-point, recap and structured cards. Off is respected even in Pro mode.")
            text_card_style = pc2.selectbox("Text card style", ["auto", "bold", "playful", "clean"],
                                            help="auto selects rounded playful type for cartoon stories, bold display type otherwise.")
            music_volume = pc3.slider("Music gain", 0.0, 1.0, .10 if studio_voice_on else .55, .01)
            o, p, q = st.columns(3)
            caption_display = o.selectbox("Speech captions", ["auto", "full", "none"], disabled=not studio_voice_on)
            channel_name = p.text_input("Channel name")
            channel_logo = q.text_input("Channel logo path")
            r1, r2, r3 = st.columns(3)
            max_credits = r1.number_input("Max credits/video", 0, 5000, 30)
            flow_scenes = r2.number_input("Exact Flow motion scenes (0=auto)", 0, 500, 0)
            images_per_shot = r3.number_input("Candidate images/shot", 0, 10, 2)
        plan_only = st.checkbox("Create plan only (run later with Resume)")
        submitted = st.form_submit_button("🚀 Create production", type="primary")
    if submitted:
        if not topic.strip():
            st.warning("Enter a topic first.")
        else:
            cfg = dict(DEFAULTS)
            cfg.update({"topic": topic.strip(), "production_mode": production_mode,
                        "production_mode_engine": "youtube_pro" if production_mode == "reels_pro" else production_mode,
                        "video_type": "shorts" if production_mode == "reels_pro" else "faceless_youtube",
                        "aspect": "9:16" if production_mode == "reels_pro" else "16:9",
                        "theme": theme, "duration": int(duration), "profile": profile,
                        "language":language_code, "destination":None if destination=='automatic' else destination,
                        "approved_plan_path":approved_plan_path.strip(), "narration_input_path":narration_input_path.strip(),
                        "script_provider": script_provider, "tts_provider": tts_provider,
                        "render_quality": render_quality, "flow_image_workers": flow_workers,
                        "frame_source": frame_source, "flow_approval": flow_approval,
                        "flow_project_url": flow_project_url.strip(), "flow_reuse_mode": reuse_mode,
                        "flow_pause_on_unresolved_request": flow_pause_on_unresolved_request,
                        "gemini_chat_cleanup": gemini_cleanup,
                        "background_music": "off" if studio_audio_mode == "Silent" else background_music,
                        "background_music_path": music_path.strip(), "music_volume": music_volume,
                        "voiceover_enabled": studio_voice_on, "text_cards_enabled": text_cards_enabled,
                        "text_card_style": text_card_style,
                        "sound_effects_enabled": studio_voice_on, "ambience_enabled": studio_voice_on,
                        "caption_display": ("none" if not studio_voice_on else
                                            ("full" if production_mode == "reels_pro" and caption_display == "auto" else caption_display)),
                        "channel_name": channel_name, "channel_logo": channel_logo,
                        "max_credits": int(max_credits), "flow_scenes": int(flow_scenes) or None,
                        "images_per_shot": int(images_per_shot), "graphics_overlays": production_mode != "legacy"})
            from engine.languages import default_voice
            cfg['voice'] = default_voice(language_code)
            for key, value in THEMES[theme].items():
                cfg[key] = value
            kwargs = config_to_factory_kwargs(cfg)
            job_id = F.create_job(topic=cfg["topic"], video_type=cfg["video_type"],
                                  aspect=cfg["aspect"], **kwargs)
            resolved = os.path.join(F.pm.job_dir(job_id), "input_config.resolved.yaml")
            with open(resolved, "w", encoding="utf-8") as fh:
                yaml.safe_dump({k: v for k, v in cfg.items() if k != "production_mode_engine"}, fh,
                               sort_keys=False, allow_unicode=True)
            st.session_state.job_id = job_id
            st.success(f"Job created: `{job_id}`")
            if plan_only:
                st.info(f"Resume from QUEUE or run: python3 cli.py v3 resume {job_id}")
            else:
                run_with_ui(job_id, "🎛️ STUDIO ·")
    if st.session_state.job_id:
        st.divider()
        pipeline_view(st.session_state.job_id)

# ================= MINI REELS =================
elif page == "MINI REELS":
    st.title("📱 Mini Reels · Gemini Web → Google Flow/Veo")
    st.caption("Trend, article, or manual idea → a reviewable prompt from your visible Gemini Web session → one 8-second, 9:16 Flow/Veo clip in your browser. This is separate from the long-form storyboard, voiceover, and render pipeline.")
    st.info("Start with a Google Trends topic, a public article RSS idea, or your own text. Trends indicate search interest—not social virality—and article excerpts are inspiration, not verified facts. Gemini Web must be signed in through AutoVideoAI's browser session; there is no Gemini API fallback. You review the final prompt and explicitly approve before Flow generation.")

    from engine.mini_reels import (
        AUDIO_LABELS, FLOW_MODEL_LABELS, LANGUAGE_LABELS, TREND_REGIONS,
        VISUAL_STYLES, build_content_idea_input, compose_flow_prompt,
        fetch_content_ideas, fetch_trend_ideas, generate_flow_reel,
        generate_prompt_brief, get_content_idea_sources, list_pending_reels,
        new_reel_id, read_reel, recover_flow_reel,
    )

    idea_modes = {
        "manual": "Manual idea",
        "trends": "Google Trends",
        "articles": "Article websites",
    }
    idea_source_mode = st.radio(
        "Choose where to start",
        list(idea_modes), index=1, horizontal=True,
        format_func=lambda key: idea_modes[key], key="mini-reel-idea-source")
    previous_idea_mode = st.session_state.get("_mini_reel_last_idea_mode")
    source_context = None

    if idea_source_mode == "trends":
        left, right = st.columns([2, 1])
        region_name = left.selectbox("Google Trends region", list(TREND_REGIONS), index=0,
                                     key="mini-reel-region")
        region_code = TREND_REGIONS[region_name]
        if right.button("↻ Refresh trend ideas", key="mini-reel-refresh-trends"):
            try:
                found = fetch_trend_ideas(region_code, count=10)
                cache = dict(st.session_state.get("mini_reel_trends", {}))
                cache[region_code] = found
                st.session_state["mini_reel_trends"] = cache
                st.success(f"Loaded {len(found)} current Google Trends search ideas for {region_name}.")
            except Exception as exc:
                st.warning(f"Trend feed unavailable: {exc}. You can enter an idea manually.")

        trends_by_region = st.session_state.get("mini_reel_trends", {})
        trend_rows = trends_by_region.get(region_code, [])
        trend_titles = [str(row.get("title", "")) for row in trend_rows if row.get("title")]
        selected_trend = st.selectbox(
            "Recent search trend (optional)", [""] + trend_titles,
            format_func=lambda value: value or "Choose a trend or enter your own idea",
            key="mini-reel-trend-choice")
        if selected_trend and (
                st.session_state.get("_mini_reel_last_trend") != selected_trend
                or previous_idea_mode != idea_source_mode):
            st.session_state["mini-reel-topic"] = selected_trend
        st.session_state["_mini_reel_last_trend"] = selected_trend
        if selected_trend:
            matched = next((row for row in trend_rows if row.get("title") == selected_trend), {})
            details = " · ".join(x for x in (matched.get("approx_traffic", ""), matched.get("published", "")) if x)
            st.caption(f"Google Trends Trending Now RSS · {region_name}" + (f" · {details}" if details else ""))

    elif idea_source_mode == "articles":
        st.subheader("Browse ideas from article websites")
        st.caption("Refresh a public RSS feed, choose an article, and use its title and excerpt as inspiration for Gemini Web. The article page and media are not downloaded; the final Flow prompt remains editable and reviewable.")
        st.info("FactZone.com resolved to a parked for-sale page when these feeds were checked, so it is not included as an active idea feed. For fact and curiosity topics, choose The Fact Site or Interesting Facts instead.")
        source_rows = get_content_idea_sources()
        source_by_id = {row["id"]: row for row in source_rows}
        source_col, refresh_col = st.columns([3, 1])
        content_source_id = source_col.selectbox(
            "Article website", list(source_by_id),
            format_func=lambda key: source_by_id[key]["name"],
            key="mini-reel-content-source")
        if refresh_col.button("↻ Refresh articles", key="mini-reel-refresh-articles"):
            try:
                found = fetch_content_ideas(content_source_id, count=12)
                cache = dict(st.session_state.get("mini_reel_articles", {}))
                cache[content_source_id] = found
                st.session_state["mini_reel_articles"] = cache
                st.success(f"Loaded {len(found)} recent article ideas from {source_by_id[content_source_id]['name']}.")
            except Exception as exc:
                st.warning(f"Article feed unavailable: {exc}. Choose another website or enter an idea manually.")
        st.caption(source_by_id[content_source_id]["description"])

        articles_by_source = st.session_state.get("mini_reel_articles", {})
        article_rows = articles_by_source.get(content_source_id, [])
        article_by_id = {row["id"]: row for row in article_rows if row.get("id")}
        if article_by_id:
            selected_article_id = st.selectbox(
                "Article idea (optional)", [""] + list(article_by_id),
                format_func=lambda key: (
                    "Choose an article" if not key else
                    article_by_id[key]["title"] + (f" · {article_by_id[key]['published'][:16]}" if article_by_id[key].get("published") else "")
                ), key="mini-reel-article-choice")
            selected_article = article_by_id.get(selected_article_id)
            if selected_article:
                try:
                    article_input = build_content_idea_input(selected_article)
                    source_context = article_input["source_context"]
                    if (st.session_state.get("_mini_reel_last_article") != selected_article_id
                            or previous_idea_mode != idea_source_mode):
                        st.session_state["mini-reel-topic"] = article_input["idea"]
                    st.session_state["_mini_reel_last_article"] = selected_article_id
                    st.caption(f"Selected from {source_context['source_name']} · {source_context.get('published') or 'date not supplied'}")
                    if source_context.get("summary"):
                        with st.expander("Article excerpt used as idea context", expanded=True):
                            st.write(source_context["summary"])
                    st.link_button("Open selected article", source_context["url"],
                                   key=f"mini-reel-article-link-{selected_article_id}")
                except ValueError as exc:
                    st.warning(f"This feed item cannot be used safely: {exc}")
                    source_context = None
            else:
                st.session_state["_mini_reel_last_article"] = ""
        else:
            st.caption("No articles loaded yet. Use **Refresh articles** to fetch the selected website's feed.")
            st.session_state["_mini_reel_last_article"] = ""

    st.session_state["_mini_reel_last_idea_mode"] = idea_source_mode
    placeholders = {
        "manual": "Type a fresh idea, or edit a selected trend/article title",
        "trends": "Choose a trend above, or type a fresh idea",
        "articles": "Choose an article above, or type a fresh idea",
    }
    idea = st.text_input("Starting idea", key="mini-reel-topic", max_chars=300,
                         placeholder=placeholders[idea_source_mode])

    c1, c2, c3 = st.columns(3)
    style_keys = list(VISUAL_STYLES)
    visual_style = c1.selectbox(
        "Visual treatment", style_keys, index=0,
        format_func=lambda key: {
            "miniature-diorama": "Miniature diorama / macro",
            "miniature-stop-motion": "Miniature stop-motion",
            "macro-realism": "Macro realism",
            "cinematic-short": "Cinematic short",
            "playful-3d": "Playful original 3D",
        }.get(key, key), key="mini-reel-style")
    language = c2.selectbox("Voiceover language (when requested)", list(LANGUAGE_LABELS),
                            format_func=lambda key: LANGUAGE_LABELS[key], key="mini-reel-language")
    audio_modes = list(AUDIO_LABELS)
    audio_mode = c3.selectbox("Flow audio request", audio_modes,
                               format_func=lambda key: AUDIO_LABELS[key], key="mini-reel-audio")
    st.caption("Audio intent is included in the prompt to Flow/Veo. Native speech/ambience—and even a silence request—depends on the selected model and account. AutoVideoAI makes no separate TTS request; review the returned clip and any Hindi/Odia pronunciation.")

    d1, d2, d3 = st.columns(3)
    model_options = list(FLOW_MODEL_LABELS)
    model = d1.selectbox("Flow/Veo model", model_options, index=1,
                         format_func=lambda key: FLOW_MODEL_LABELS[key], key="mini-reel-model")
    flow_project_url = d2.text_input("Existing Flow project URL (optional)", key="mini-reel-project-url",
                                     placeholder="https://flow.google.com/project/…")
    max_generation_credits = d3.number_input("Flow Agent approval cap (when shown)", min_value=0, max_value=5000,
                                              value=30, step=1, key="mini-reel-max-credits",
                                              help="Applied when Flow's current Agent UI exposes a credit-approval card. This is not a price estimate and may not be enforceable in every Flow UI mode; review any Flow credit prompt and your account's terms before proceeding.")
    st.caption("The numeric cap is conditional on Flow showing a credit-approval card. If your current Flow UI does not show one, account-level pricing/limits apply; AutoVideoAI still requires this separate one-generation confirmation and never automatically re-submits an uncertain request.")

    pending_reels = list_pending_reels()
    draft = st.session_state.get("mini_reel_draft")
    if st.button("✨ Ask Gemini Web for an original reel prompt", type="primary",
                 key="mini-reel-generate-prompt"):
        if not idea.strip():
            st.warning("Choose a trend or enter an idea first.")
        else:
            try:
                with st.spinner("Asking the visible Gemini Web session for one original eight-second concept…"):
                    brief = generate_prompt_brief(
                        idea, visual_style=visual_style, language=language,
                        audio_mode=audio_mode, source_context=source_context)
                    flow_prompt = compose_flow_prompt(
                        brief, visual_style=visual_style, language=language,
                        audio_mode=audio_mode, model=model)
                draft = {
                    "reel_id": new_reel_id(), "brief": brief, "flow_prompt": flow_prompt,
                    "visual_style": visual_style, "language": language,
                    "audio_mode": audio_mode, "model": model,
                    "flow_project_url": flow_project_url.strip(),
                }
                st.session_state["mini_reel_draft"] = draft
                st.success("Gemini Web returned a draft. Review or edit the exact Flow prompt below; no video has been generated yet.")
            except Exception as exc:
                st.error(f"Could not create a prompt with Gemini Web: {exc}")

    draft = st.session_state.get("mini_reel_draft")
    if draft:
        st.divider()
        st.subheader(f"Review draft · {draft['brief'].get('title', 'Mini reel')}")
        st.write(draft["brief"].get("angle", ""))
        st.caption(f"Gemini Web · {draft['brief'].get('idea', '')} · 8 seconds · 9:16 · {FLOW_MODEL_LABELS.get(draft.get('model'), draft.get('model'))}")
        draft_source = draft["brief"].get("source_context")
        if draft_source:
            st.caption(f"Idea inspiration: {draft_source.get('source_name', 'article feed')} · verify factual claims before publishing.")
            st.link_button("Review source article", draft_source["url"],
                           key=f"mini-reel-draft-source-{draft['reel_id']}")
        if draft["brief"].get("voiceover_line"):
            st.markdown("**Requested voiceover:** " + draft["brief"]["voiceover_line"])
        if draft["brief"].get("caption"):
            st.markdown("**Suggested post caption:** " + draft["brief"]["caption"])
        if draft["brief"].get("hashtags"):
            st.caption(" ".join(draft["brief"]["hashtags"]))
        prompt_key = f"mini-reel-flow-prompt-{draft['reel_id']}"
        flow_prompt = st.text_area("Final Flow prompt (editable)", value=draft["flow_prompt"],
                                   height=220, key=prompt_key)
        project_key = f"mini-reel-project-{draft['reel_id']}"
        project_for_draft = st.text_input("Flow project URL for this reel (optional)",
                                          value=draft.get("flow_project_url", ""), key=project_key,
                                          placeholder="https://flow.google.com/project/…")
        approval_key = f"mini-reel-credit-approval-{draft['reel_id']}"
        credit_acknowledged = st.checkbox(
            "I reviewed this prompt and approve one Flow/Veo generation using my signed-in Google account. Flow may use my account credits at the price shown by Flow.",
            value=False, key=approval_key)
        saved = None
        try:
            saved = read_reel(draft["reel_id"])
        except (FileNotFoundError, OSError, ValueError):
            pass
        if saved and saved.get("status") == "complete" and Path(saved.get("output_path", "")).is_file():
            st.success("This reel is already generated. Reopening it will not submit another video request.")
            st.video(saved["output_path"])
            if saved.get("audio_mode") == "flow-voiceover":
                if saved.get("audio_stream_present") is True:
                    st.info("An audio track was detected. Listen through and verify that the requested voiceover is present and correct.")
                elif saved.get("audio_stream_present") is False:
                    st.warning("No audio track was detected. The video was not automatically regenerated or replaced, avoiding an unexpected second credit-bearing request.")
                else:
                    st.caption("Audio-track detection was unavailable; please listen to the clip to verify native audio.")
            elif saved.get("audio_mode") == "silent" and saved.get("audio_stream_present") is True:
                st.warning("Flow returned an audio track despite the silence prompt. AutoVideoAI kept the original clip; mute it manually if silence is required.")
            video_bytes = Path(saved["output_path"]).read_bytes()
            st.download_button("⬇️ Download mini reel", video_bytes,
                               file_name=f"{draft['reel_id']}.mp4", mime="video/mp4",
                               key=f"mini-reel-download-{draft['reel_id']}")
            if saved.get("flow_project_url"):
                st.markdown(f"[Open this reel's Flow project]({saved['flow_project_url']})")
        else:
            other_pending = [row for row in pending_reels if row.get("reel_id") != draft["reel_id"]]
            if other_pending:
                st.warning("A different Flow request is unresolved. Recover that exact clip before submitting another generation to avoid duplicate credit-bearing work.")
            if st.button("🎬 Generate once in Google Flow/Veo", type="primary",
                         disabled=(not credit_acknowledged or bool(other_pending)),
                         key=f"mini-reel-generate-video-{draft['reel_id']}"):
                try:
                    with st.spinner("Flow is generating or recovering this one saved request. Keep the browser session open…"):
                        result = generate_flow_reel(
                            draft["reel_id"], brief=draft["brief"], flow_prompt=flow_prompt,
                            model=draft["model"], visual_style=draft["visual_style"],
                            audio_mode=draft["audio_mode"], language=draft["language"],
                            flow_project_url=project_for_draft,
                            flow_approval="once", max_generation_credits=int(max_generation_credits))
                    st.success("Flow video saved. No separate voiceover/TTS job was run.")
                    st.video(result["output_path"])
                    if result.get("audio_mode") == "flow-voiceover":
                        if result.get("audio_stream_present") is True:
                            st.info("An audio track was detected. Listen through and verify the requested voiceover.")
                        elif result.get("audio_stream_present") is False:
                            st.warning("No audio track was detected. AutoVideoAI did not automatically regenerate or replace this clip.")
                        else:
                            st.caption("Audio-track detection was unavailable; please listen to verify native audio.")
                    elif result.get("audio_mode") == "silent" and result.get("audio_stream_present") is True:
                        st.warning("Flow returned an audio track despite the silence prompt. AutoVideoAI kept the original clip; mute it manually if silence is required.")
                    st.download_button("⬇️ Download mini reel", Path(result["output_path"]).read_bytes(),
                                       file_name=f"{draft['reel_id']}.mp4", mime="video/mp4",
                                       key=f"mini-reel-download-now-{draft['reel_id']}")
                    if result.get("flow_project_url"):
                        st.markdown(f"[Open this reel's Flow project]({result['flow_project_url']})")
                except Exception as exc:
                    st.error(f"Flow generation/recovery did not complete: {exc}")
                    st.caption("A saved Flow request is never blindly resubmitted. If generation may have started, recover the same request below.")

    pending_reels = list_pending_reels()
    if pending_reels:
        st.divider()
        st.subheader("Recover a saved Flow request")
        st.caption("Recovery opens the saved project and downloads the exact requested asset; it does not send another generation prompt or intentionally spend another video-generation credit.")
        pending_labels = {
            row["reel_id"]: f"{row.get('title', row['reel_id'])} · {row['reel_id']} · {row.get('status', 'pending')}"
            for row in pending_reels
        }
        pending_id = st.selectbox("Unfinished reel", list(pending_labels),
                                  format_func=lambda key: pending_labels[key], key="mini-reel-pending-id")
        if st.button("♻️ Recover exact saved Flow video", key="mini-reel-recover-saved"):
            try:
                with st.spinner("Scanning the saved Flow project and retrying download only…"):
                    result = recover_flow_reel(pending_id)
                st.success("Saved Flow video recovered.")
                st.video(result["output_path"])
                st.download_button("⬇️ Download recovered mini reel", Path(result["output_path"]).read_bytes(),
                                   file_name=f"{pending_id}.mp4", mime="video/mp4",
                                   key=f"mini-reel-recovered-download-{pending_id}")
            except Exception as exc:
                st.error(f"Recovery did not complete: {exc}")

# ================= CREATE =================
elif page == "CREATE":
    st.title("🎬 Create Production")
    st.caption("Topic → planning → script → narration → storyboard → generation → QC → render.")
    with st.expander("⚡ FIRST TIME HERE? Make a FREE test video in one click (no login, no Chrome, ~3 min)", expanded=True):
        st.caption("Uses free AI images + motion + voiceover. Proves everything works before you touch Flow.")
        with st.form("quickfree"):
            qtopic = st.text_input("Topic", value="Why octopuses have three hearts", key="qtopic")
            qgo = st.form_submit_button("⚡ MAKE MY FIRST FREE VIDEO", type="primary")
        if qgo:
            if not qtopic.strip():
                st.warning("Enter a topic first.")
            else:
                qid = F.create_job(qtopic.strip(), "shorts", 20, "9:16", "en",
                                   "en-IN-PrabhatNeural", "education", "cinematic",
                                   "cinematic_realism", "FREE_HYBRID",
                                   budgets={"MAX_CREDITS_PER_VIDEO": 100, "MAX_RETRIES_PER_SHOT": 2},
                                   dry_run=False, tts_provider="edge", images_per_shot=0)
                st.session_state.job_id = qid
                st.success(f"Job created: `{qid}`")
                run_with_ui(qid, "🆓 LOCAL FREE ·")
    create_audio_mode = st.radio("Audio mode", ["Voiceover", "Music only", "Silent"], horizontal=True, key="create-audio-mode")
    create_voice_on = create_audio_mode == "Voiceover"
    with st.form("create"):
        topic = st.text_input("Topic / idea", placeholder="Why waking up at 5 AM doesn't automatically make you successful")
        c1, c2, c3 = st.columns(3)
        video_type = c1.selectbox("Format", ["shorts", "faceless_youtube", "explainer", "marketing"])
        duration = c2.slider("Target seconds", 15, 600, 45)
        content_type = c3.selectbox("Content type", CONTENT_TYPES)
        c4, c5, c6 = st.columns(3)
        voice = c4.selectbox("Voice", VOICES, disabled=not create_voice_on)
        preset = c5.selectbox("Style preset", PRESETS)
        profile = c6.selectbox("Quality profile", PROFILES, index=0, format_func=lambda p: f"{mode_badge[p]} {p}")
        pr1, pr2 = st.columns(2)
        create_cards = pr1.checkbox("Include text cards", value=False, help="Optional editorial cards; speech captions have a separate control below.")
        create_card_style = pr2.selectbox("Text card style", ["auto", "bold", "playful", "clean"])
        pm1, pm2, pm3 = st.columns(3)
        create_music = pm1.selectbox("Background music", ["off", "auto", "local", "browser"],
                                    index=1 if create_audio_mode == "Music only" else 0, disabled=create_audio_mode == "Silent")
        create_music_path = pm2.text_input("Licensed local music path")
        create_captions = pm3.selectbox("Speech captions", ["auto", "full", "none"], disabled=not create_voice_on)
        with st.expander("Advanced"):
            a1, a2, a3 = st.columns(3)
            tone = a1.selectbox("Tone", ["cinematic", "exciting", "calm", "funny", "documentary"])
            language = a2.selectbox("Language", ["en", "hi", "or"])
            tts_provider = a3.selectbox("TTS", ["edge", "gtts", "kokoro", "chatterbox"], disabled=not create_voice_on)
            b1, b2 = st.columns(2)
            max_credits = b1.number_input("MAX CREDITS PER VIDEO", 0, 2000, 50,
                                          help="Storyboard Economy treats this as a hard planning ceiling; 0 = image/stock only.")
            max_retries = b2.number_input("MAX RETRIES PER SHOT", 0, 5, 1)
            images_per_shot = st.slider("Extra candidate images per shot", 0, 4, 0,
                                        help="Storyboard Economy already makes opening/closing frames. Keep this 0 unless you want extra candidates.")
            st.markdown("**🌱 Storyboard Economy controls**")
            e1, e2, e3, e4 = st.columns(4)
            video_share = e1.slider("AI-video scene share", 0.0, 1.0, 0.20, 0.05,
                                    help="Automatic target fraction of scenes worth spending Flow video credits on.")
            stock_share = e2.slider("Stock-video scene share", 0.0, 1.0, 0.60, 0.05,
                                    help="Meaningful generic B-roll can use your local Pexels/stock library or optional stock APIs.")
            flow_scenes_ui = e3.number_input("Exact Flow scenes (0=auto)", 0, 100, 0,
                                             help="Explicit requested count. Budget safety still wins.")
            max_flow_scenes_ui = e4.number_input("Max Flow scenes (0=no cap)", 0, 100, 0)
            f1, f2, f3 = st.columns(3)
            frame_source = f1.selectbox("Opening/closing frame source", ["auto", "flow", "free"], index=0,
                                        help="auto = try Flow Agent image generation then free/local fallback; free = never use Flow for frames.")
            flow_approval = f2.selectbox("Flow credit approval", ["once", "manual", "always"], index=0,
                                         help="once is safest: AutoVideoAI only approves a generation within your per-generation cap.")
            max_generation_credits = f3.number_input("Max credits per Flow generation", 0, 200, 10,
                                                     help="Credit guard. If Flow asks for more, AutoVideoAI leaves it unapproved.")
            flow_pause_on_unresolved_request = st.checkbox(
                "Pause when a Flow request cannot be safely recovered (opt-in)",
                value=_flow_pause_setting_default(),
                help="Off by default: ambiguous images use the free fallback in auto mode; strict image/video requests fail without PAUSED status and can be explicitly resumed. On: save the request and pause for your choice. Recovery retries download-only first; at most one replacement may use image credits, and only after two full scans prove the original absent.")
        dry = st.checkbox("DRY RUN (plan + estimate, spend nothing)", value=("FLOW" in profile or "MANUAL" in profile or profile == "STORYBOARD_ECONOMY"))
        submitted = st.form_submit_button("🚀 GENERATE", type="primary")
    if submitted:
        if not topic.strip():
            st.warning("Enter a topic first.")
        else:
            aspect = "9:16" if video_type == "shorts" or (video_type == "marketing" and duration <= 65) else "16:9"
            job_id = F.create_job(topic, video_type, duration, aspect, language, voice,
                                   content_type, tone, preset, profile,
                                   budgets={"MAX_CREDITS_PER_VIDEO": max_credits, "MAX_RETRIES_PER_SHOT": max_retries},
                                   dry_run=dry, tts_provider=tts_provider,
                                   images_per_shot=images_per_shot,
                                   video_share=video_share, stock_share=stock_share,
                                   flow_scenes=(int(flow_scenes_ui) or None),
                                   max_flow_scenes=(int(max_flow_scenes_ui) or None),
                                   frame_source=frame_source, flow_approval=flow_approval,
                                   max_generation_credits=int(max_generation_credits),
                                   flow_pause_on_unresolved_request=flow_pause_on_unresolved_request,
                                   voiceover_enabled=create_voice_on, text_cards_enabled=create_cards,
                                   text_card_style=create_card_style,
                                   background_music="off" if create_audio_mode == "Silent" else create_music,
                                   background_music_path=create_music_path.strip(),
                                   caption_display=create_captions if create_voice_on else "none",
                                   sound_effects_enabled=create_voice_on, ambience_enabled=create_voice_on)
            st.session_state.job_id = job_id
            st.success(f"Job created: `{job_id}`" + (" — **DRY RUN** (no credits)" if dry else ""))
            run_with_ui(job_id, "🧪 DRY RUN ·" if dry else ("🌱 ECONOMY STORYBOARD ·" if profile == "STORYBOARD_ECONOMY" else ("💳 FLOW CREDITS ·" if profile.startswith("FLOW") or profile == "MANUAL_DIRECTOR" else "🆓 LOCAL FREE ·")))
    if st.session_state.job_id:
        st.divider()
        pipeline_view(st.session_state.job_id)

# ================= STORYBOARD =================
elif page == "STORYBOARD":
    st.title("🖼️ Storyboard")
    if not st.session_state.job_id:
        st.info("Select a job in the sidebar.")
    else:
        m = F.pm.load_manifest(st.session_state.job_id)
        D = F.pm.dirs(st.session_state.job_id)
        st.caption(f"{m.job_id} · {m.profile} · {len(m.shots)} shots")
        try:
            est = json.load(open(os.path.join(D["root"], "budget.json"), encoding="utf-8"))
            st.info(f"💳 Estimated {est['estimated_credits']} + reserve {est['retry_reserve']} = **{est['projected_total']}** (budget {est['max_per_video']}, within={est['within_budget']})")
        except Exception:
            pass
        rows = [{"shot": s.shot_id, "voice": f"{s.voice_start:.1f}-{s.voice_end:.1f}s",
                 "coverage": s.coverage, "strategy": getattr(s, "media_strategy", ""),
                 "est_credits": getattr(s, "estimated_credits", 0),
                 "priority": s.priority, "provider": s.provider,
                 "model": s.model, "gen_s": s.gen_duration, "takes": s.num_candidates,
                 "status": s.status} for s in m.shots]
        df = pd.DataFrame(rows)
        edited = st.data_editor(df, use_container_width=True, key="sb_table",
                                column_config={"model": st.column_config.SelectboxColumn(options=["omni_draft", "omni_standard", "veo_lite", "veo_fast", "veo_quality", "wan_t2v", "wan_i2v", "ltx_t2v", "stock", "kenburns_plus"]),
                                               "priority": st.column_config.SelectboxColumn(options=["LOW", "NORMAL", "HERO"]),
                                               "status": st.column_config.SelectboxColumn(options=["planned", "approved", "skipped"])})
        if st.button("💾 Save storyboard edits"):
            for _, r in edited.iterrows():
                s = next(x for x in m.shots if x.shot_id == r["shot"])
                s.priority, s.model, s.gen_duration, s.num_candidates, s.status = \
                    r["priority"], r["model"], int(r["gen_s"]), int(r["takes"]), r["status"]
                from engine.routing.credit_router import MODEL2PROVIDER
                s.provider = MODEL2PROVIDER.get(s.model, "flow")
                F.pm.update_shot(m.job_id, s)
            st.success("Saved. Resume from QUEUE to generate with these settings.")
        script_p = os.path.join(D["root"], "script.md")
        if os.path.exists(script_p):
            st.download_button("📜 Download full script (markdown)",
                               open(script_p, "rb"), file_name=f"{m.job_id}_script.md")
        for s in m.shots:
            with st.expander(f"{s.shot_id} · {s.coverage} · {s.status} · {s.model}"):
                c1, c2 = st.columns([1, 2])
                frame = os.path.join(D["storyboard"], f"{s.shot_id}.jpg")
                if os.path.exists(frame):
                    c1.image(frame, caption="Best reference" if s.reference_assets else "Storyboard frame")
                else:
                    c1.caption("(no frame yet)")
                c2.caption(f"🎙️ {s.voice_start:.1f}–{s.voice_end:.1f}s: {s.narration[:220]}")
                c2.code(s.compiled_prompt or "(prompt compiles at generation time)", language="text")
                if s.reference_assets:
                    st.caption(f"🖼️ {len(s.reference_assets)} scene stills (best first)")
                    st.image([p for p in s.reference_assets if os.path.exists(p)],
                             caption=[f"#{i+1}" for i in range(len(s.reference_assets))],
                             width=180)
                if s.retry_history:
                    c2.warning("Retries: " + " | ".join(s.retry_history))

# ================= DIRECTOR REVIEW =================
elif page == "DIRECTOR REVIEW":
    st.title("🎥 Director Review")
    if not st.session_state.job_id:
        st.info("Select a job in the sidebar.")
    else:
        m = F.pm.load_manifest(st.session_state.job_id)
        D = F.pm.dirs(st.session_state.job_id)
        for s in m.shots:
            with st.expander(f"{s.shot_id} · {s.status} · retries {s.retry_count}", expanded=(s.status != "accepted")):
                shot_dir = os.path.join(D["flow"], "shots", s.shot_id)
                takes = sorted(glob.glob(os.path.join(shot_dir, "take_*.mp4")))
                if not takes:
                    st.caption("No takes yet.")
                    continue
                for t in takes:
                    name = os.path.basename(t)
                    qc = {}
                    qp = os.path.join(D["qc"], f"{s.shot_id}_{os.path.splitext(name)[0]}.json")
                    if os.path.exists(qp):
                        qc = json.load(open(qp, encoding="utf-8"))
                    c1, c2 = st.columns([2, 1])
                    c1.video(t)
                    c2.write(f"**{name}**")
                    if qc:
                        c2.write(f"overall **{qc.get('overall')}** · {qc.get('decision')}")
                        c2.caption(f"tech {qc.get('technical')} · cont {qc.get('continuity')} · motion {qc.get('motion')} · fail: {qc.get('failure')}")
                    is_acc = s.accepted_take and os.path.basename(s.accepted_take) == name or (os.path.exists(os.path.join(shot_dir, "accepted.mp4")) and name == sorted(takes)[-1] and False)
                    if st.button(f"✅ Accept {name}", key=f"acc-{s.shot_id}-{name}"):
                        import shutil
                        shutil.copy(t, os.path.join(shot_dir, "accepted.mp4"))
                        s.accepted_take = os.path.join(shot_dir, "accepted.mp4")
                        s.status = "accepted"
                        F.pm.update_shot(m.job_id, s)
                        DB.bump(m.job_id, "accepted_shots")
                        st.success(f"{s.shot_id} accepted: {name}")
                        st.rerun()
                if st.button(f"🔁 Regenerate {s.shot_id} (spends credits!)", key=f"regen-{s.shot_id}"):
                    s.status = "planned"
                    s.accepted_take = None
                    F.pm.update_shot(m.job_id, s)
                    st.info("Marked for regeneration. Resume from QUEUE.")

# ================= QUEUE =================
elif page == "QUEUE":
    st.title("📋 Queue")
    rows = [{"job": j["job_id"][:40], "status": j["status"], "profile": j["profile"],
             "est": j["est_credits"], "gens": j["actual_generations"],
             "✅": j["accepted_shots"], "❌": j["rejected_shots"],
             "retries": j["retry_count"], "updated": j["updated_at"]} for j in jobs]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    if st.session_state.job_id:
        selected_row = DB.get(st.session_state.job_id) or {}
        current_flow_pause = bool(F._settings(st.session_state.job_id).get(
            "flow_pause_on_unresolved_request", False))
        with st.expander("Flow recovery behavior", expanded=False):
            pause_flow_choice = st.checkbox(
                "Pause this job if a Flow request cannot be safely recovered",
                value=current_flow_pause, key=f"flow-pause-policy-{st.session_state.job_id}",
                help="Off: auto-frame images use a free fallback; strict Flow/video requests fail without automatic PAUSED status. On: preserve the request and pause. One proven-missing image replacement is bounded and may use image credits.")
            if st.button("Save Flow recovery choice", key=f"save-flow-pause-policy-{st.session_state.job_id}"):
                F.set_flow_pause_on_unresolved_request(st.session_state.job_id, pause_flow_choice)
                st.success("Saved. This choice applies the next time the job is resumed.")
        if selected_row.get("status") in ("paused", "assisted"):
            pause_panel(st.session_state.job_id)
            st.divider()
        presentation_editor(st.session_state.job_id)
        c1, c2 = st.columns(2)
        if c1.button("▶️ Resume / continue job", type="primary"):
            run_with_ui(st.session_state.job_id, "")
        if c2.button("🎬 Render now (from accepted takes)"):
            with st.spinner("Rendering..."):
                try:
                    r = F.render_job(st.session_state.job_id)
                    st.success(f"Done: {r['video']} ({r['renderer']})")
                    st.video(r["video"])
                except Exception as e:
                    st.error(f"Render failed: {e}")

# ================= FLOW SESSION =================
elif page == "FLOW SESSION":
    st.title("🌊 Flow Session")
    from engine.providers.flow_browser import FlowBrowserProvider, FlowBrowser
    prov = FlowBrowserProvider()
    st.write("Provider:", prov.status().reason or ("available" if prov.status().available else "unavailable"))
    st.caption("Change browser in SETTINGS → Browser (auto = your Chrome first). "
               "Missing bundled browser? Run: `python3 -m playwright install chromium` — "
               "or skip the download and use system/CDP mode.")
    st.caption("First run opens a visible browser — log into Google YOURSELF. Passwords are never automated or stored. Profile: `.flow-profile/` (git-ignored).")
    c1, c2, c3 = st.columns(3)
    if c1.button("🔑 Open Flow (login / check session)"):
        b = FlowBrowser(headless=False)
        with st.spinner("Browser open — complete any Google login manually (5 min max)..."):
            try:
                b.ensure_session(visible_login_seconds=300)
                st.success(f"Session OK. Logged in: {b.is_logged_in()}")
            except Exception as e:
                st.error(str(e))
            finally:
                b.close()
    if c2.button("🌐 Open Flow website"):
        st.markdown("[Open labs.google/fx](https://labs.google/fx)")
    if c3.button("🧪 Dry-run check (no browser)"):
        st.success("Dry runs never launch a browser or spend credits. Use CREATE with DRY RUN checked.")
    if st.button("🩺 Run browser diagnostics"):
        from engine.providers.flow_browser import doctor_report
        st.code(doctor_report(), language="text")
    with st.expander("🔗 Attach to YOUR open Chrome (CDP — recommended on WSL)", expanded=False):
        from engine.providers.flow_browser import probe_cdp, cdp_is_live
        st.caption("This drives your already-open, already-logged-in Chrome — no second login, no bundled download, no profile juggling.")
        st.markdown("**Windows:** run `chrome-debug.bat` (in the project folder). **Mac/Linux:** `./chrome-debug.sh`. Then paste the port below.")
        cdp_in = st.text_input("Chrome debug URL", value="http://127.0.0.1:9222",
                               help="Also settable permanently via FLOW_CDP_URL or SETTINGS → Browser.")
        _r = probe_cdp(cdp_in)
        if cdp_is_live(cdp_in):
            st.success(f"✅ Detected: {_r.get('browser', '?')} — browser mode 'auto' will attach here.")
        else:
            st.warning(f"Not reachable ({_r.get('error', '?')}). Start Chrome with the launcher above, then retry.")
    st.divider()
    st.subheader("🧑‍✈️ Assisted Flow Mode")
    if st.session_state.job_id:
        selected_row = DB.get(st.session_state.job_id) or {}
        if selected_row.get("status") in ("paused", "assisted"):
            pause_panel(st.session_state.job_id)
            st.divider()
    st.caption("Use the saved-request recovery controls above. Manual prompt generation and newest-file association have been removed from this page.")

# ================= CLIP STUDIO =================
elif page == "CLIP STUDIO":
    st.title("✂️ Gemini Hybrid Clip Studio")
    st.caption("Find strong self-contained moments with Gemini video analysis, then verify the exact cuts against local speech timing. Gemini scores are editorial estimates—not promises of virality.")
    source = st.text_input("Source video", placeholder="Public YouTube URL or local video path")
    c1, c2, c3 = st.columns(3)
    count = c1.number_input("Output clips", 1, 10, 3)
    min_seconds = c2.number_input("Minimum seconds", 8, 120, 25)
    max_seconds = c3.number_input("Maximum seconds", 10, 180, 55)
    r1, r2, r3 = st.columns(3)
    ranking = r1.selectbox("Clip selection", ["gemini-hybrid", "auto", "gemini-api-hybrid",
                                               "gemini-web-hybrid", "groq", "local"],
                           help="Gemini hybrid tries API, then the visible signed-in browser, then Groq/local.")
    captions = r2.selectbox("Speech timing", ["auto", "groq", "local"])
    clip_language = st.selectbox('Clip transcript language',['en','hi'],help='Odia source ASR is not certified; use a reviewed transcript in AI RECREATE.')
    rights = r3.selectbox("Source rights", [
        "own_content", "written_permission", "licensed_content", "creative_commons",
        "public_domain", "commentary_or_review", "private_draft_only",
    ])
    st.warning("Captions, music, cropping, zoom or motion alone do not make somebody else's video copyright-safe. AutoVideoAI records your declaration but cannot grant legal rights.")
    output_dir = st.text_input("Output folder", value="outputs/my-clips")
    with st.expander("Optional licensed background music", expanded=True):
        clip_music_on = st.checkbox('Add soft background music', value=False,
                                    help='Off preserves the current source-only audio. On adds a low, ducked music bed without reducing source speech gain.')
        background_music = st.text_input("Local music file", value="")
        m1, m2 = st.columns(2)
        music_license = m1.selectbox("Music licence", [
            "none", "own", "youtube_audio_library", "royalty_free_licensed", "creative_commons",
        ])
        music_volume = m2.slider("Music volume", 0.0, 0.35, 0.08, 0.01)
    gemini_cleanup = st.selectbox("Temporary Gemini browser chat", ["delete-after-read", "keep"])
    framing = st.selectbox("Framing", ["face-crop", "fit"],
                           help="Fit keeps the complete picture. Face crop uses a static estimate and may miss speaker changes.")
    clip_broll_enabled = st.checkbox(
        "Optional: find related stock B-roll cutaways for these highlights",
        value=False,
        help="Search is a separate, explicit step after the clips exist. Each exact stock file must be previewed, rights-reviewed and approved before a separate B-roll copy is rendered; original highlights are preserved.")
    cb1, cb2, cb3 = st.columns(3)
    clip_broll_count = cb1.number_input("Maximum B-roll suggestions", 1, 5, 3, 1,
                                        disabled=not clip_broll_enabled, key="clip-studio-broll-count")
    clip_broll_duration = cb2.slider("Cutaway duration (seconds)", 0.5, 6.0, 2.0, 0.5,
                                      disabled=not clip_broll_enabled, key="clip-studio-broll-duration")
    clip_broll_replace = cb3.checkbox(
        "Replace previous suggestions", value=False,
        disabled=(not clip_broll_enabled or not st.session_state.get('clip_broll_review_path')),
        key="clip-studio-broll-replace")
    confirmed = st.checkbox("I confirm the selected rights/licence declaration is accurate")
    if st.button("✂️ Analyse and create clips", type="primary"):
        if not source.strip():
            st.error("Enter a YouTube URL or local video path.")
        elif not confirmed:
            st.error("Confirm the source-rights declaration before processing.")
        else:
            from engine.clipping import create_highlight_clips
            bar = st.progress(0)
            status = st.empty()
            def clip_progress(message, pct, info=""):
                bar.progress(max(0, min(100, int(pct))))
                status.code(f"{message}" + (f"\n{info}" if info else ""), language="text")
            try:
                result = create_highlight_clips(
                    source.strip(), output_dir.strip() or "outputs/my-clips",
                    count=int(count), min_seconds=float(min_seconds),
                    max_seconds=float(max_seconds), caption_provider=captions,
                    ranking_provider=ranking, source_rights=rights,
                    language=clip_language, background_music_enabled=clip_music_on,
                    background_music=background_music.strip(),
                    music_license=music_license, music_volume=float(music_volume),
                    gemini_chat_cleanup=gemini_cleanup,
                    framing=framing,
                    progress_cb=clip_progress)
                st.session_state['last_clip_result'] = result
                st.session_state.pop('clip_broll_review_path', None)
                st.success(f"Created {len(result['outputs'])} clips using {result['method']}.")
                if result.get("partial_result"):
                    st.warning(result["shortfall_reason"])
                if result.get("ranking_fallback_reason"):
                    st.warning("Gemini fallback: " + result["ranking_fallback_reason"])
                for item in result["highlights"]:
                    st.subheader(item.get("title") or "Highlight")
                    qc = item.get("qc") or {}
                    st.caption(
                        f"{item['start']:.1f}s–{item['end']:.1f}s · "
                        f"quality {qc.get('quality_score', item.get('score', 0))}/100 · "
                        f"QC {qc.get('decision', 'not run')} · {item.get('ranking', 'local')} · "
                        f"{item.get('output_filename', '')}")
                    if qc and not qc.get("ready_to_publish"):
                        st.warning("Clip requires review: " + ", ".join(
                            qc.get("blocking_issues") or qc.get("review_issues") or
                            ["semantic relevance, hook/payoff, framing and publication rights are not certified by technical QC"]))
                    st.video(item["output"])
            except Exception as exc:
                st.error(str(exc))
    if clip_broll_enabled and st.session_state.get('last_clip_result'):
        from engine.broll import (apply_clip_studio_review, load_review as load_clip_broll_review,
                                  prepare_clip_studio_review, save_review as save_clip_broll_review)
        clip_result = st.session_state['last_clip_result']
        st.divider()
        st.subheader("🌿 Preview and approve B-roll cutaways")
        st.caption("Suggestions are full-screen visual cutaways inside the selected highlights. Existing clip audio and duration stay unchanged. The original highlights are never overwritten.")
        if st.button("🔎 Search related stock for these highlights", key="clip-broll-search"):
            try:
                with st.spinner("Searching configured stock sources; no Flow/Veo generation is submitted…"):
                    review_path, review = prepare_clip_studio_review(
                        clip_result, max_candidates=int(clip_broll_count),
                        default_duration=float(clip_broll_duration), replace=clip_broll_replace)
                st.session_state['clip_broll_review_path'] = review_path
                st.success(f"Found {sum(1 for x in review.get('candidates', []) if x.get('status') == 'ready')} preview candidate(s). Nothing is applied until approved.")
            except Exception as exc:
                st.error(str(exc))
        clip_review_path = st.session_state.get('clip_broll_review_path')
        if clip_review_path and os.path.isfile(clip_review_path):
            try:
                review = load_clip_broll_review(clip_review_path)
                updates = {}
                for candidate in review.get('candidates', []):
                    cid = str(candidate.get('candidate_id', 'cutaway'))
                    st.markdown(f"**{candidate.get('label', cid)}**")
                    if candidate.get('path') and os.path.isfile(candidate['path']):
                        cprev, cstock = st.columns(2)
                        if candidate.get('clip_output') and os.path.isfile(candidate['clip_output']):
                            cprev.video(candidate['clip_output'])
                            cprev.caption("Original highlight (unchanged)")
                        cstock.video(candidate['path'])
                        cstock.caption("Exact related stock candidate")
                        st.caption("Query: " + str(candidate.get('query', '')) +
                                   " · Source: " + str(candidate.get('source', 'stock')) +
                                   " · Licence: " + str(candidate.get('license', 'review required')) +
                                   (" · Creator: " + str(candidate.get('creator')) if candidate.get('creator') else ""))
                        if candidate.get('page_url'):
                            st.markdown(f"[Open stock source page]({candidate['page_url']})")
                        clip_duration = float(candidate.get('clip_duration') or 0)
                        max_start = max(0.0, clip_duration - 0.5)
                        cut_start = st.number_input("Cutaway start within this highlight (seconds)", 0.0, max_start,
                                                    min(max_start, max(0.0, float(candidate.get('start', 0) or 0))), 0.25,
                                                    key=f"clip-broll-start-{cid}")
                        max_cut = max(0.5, min(6.0, clip_duration - float(cut_start)))
                        cut_default = min(max_cut, max(0.5, float(candidate.get('duration', clip_broll_duration) or clip_broll_duration)))
                        cut_length = st.slider("Cutaway length (seconds)", 0.5, max_cut, cut_default, 0.5,
                                               key=f"clip-broll-length-{cid}")
                        reviewed = st.checkbox("I reviewed this exact stock clip and its licence/rights",
                                               value=bool(candidate.get('rights_reviewed')),
                                               key=f"clip-broll-rights-{cid}")
                        approved = st.checkbox("Approve this cutaway for this highlight",
                                               value=bool(candidate.get('approved')),
                                               key=f"clip-broll-approve-{cid}")
                        updates[cid] = {"start": float(cut_start), "duration": float(cut_length),
                                        "rights_reviewed": reviewed, "approved": approved}
                    else:
                        st.warning(candidate.get('search_error', 'No valid stock clip was found for this highlight.'))
                if st.button("💾 Save B-roll approvals", key="clip-broll-save"):
                    review = save_clip_broll_review(clip_review_path, updates)
                    n_approved = sum(1 for x in review.get('candidates', [])
                                     if x.get('approved') and x.get('rights_reviewed'))
                    st.success(f"Saved {n_approved} approved insert(s). Apply will create new files and keep originals.")
                n_approved_saved = sum(1 for x in review.get('candidates', [])
                                       if x.get('approved') and x.get('rights_reviewed'))
                if st.button("🎬 Apply saved cutaways to separate copies", disabled=(n_approved_saved == 0),
                             key="clip-broll-apply"):
                    with st.spinner("Compositing approved visuals while preserving each highlight's original audio…"):
                        applied = apply_clip_studio_review(clip_review_path)
                    if applied['outputs']:
                        st.success(f"Created {len(applied['outputs'])} separate B-roll edit(s). The original highlight files are unchanged.")
                        for output_path in applied['outputs']:
                            st.video(output_path)
                            with open(output_path, 'rb') as handle:
                                st.download_button("⬇️ Download B-roll edit", handle,
                                                   file_name=os.path.basename(output_path),
                                                   key=f"clip-broll-download-{os.path.basename(output_path)}")
                    else:
                        st.info("No approved insert was applied.")
            except Exception as exc:
                st.error("B-roll review failed: " + str(exc))

# ================= CONTENT INBOX =================
elif page == 'CONTENT INBOX':
    st.title('Source ideas & approved scripts')
    st.caption('Import an idea, not a licence or an instruction. Public source text is untrusted; no generation is submitted here.')
    from engine.source_inbox import SourceInbox
    from engine.content_plan import longform_template
    title = st.text_input('Source title')
    source_text = st.text_area('Paste permitted post/article text', height=180)
    source_url = st.text_input('Public allowlisted HTTPS article URL (optional)')
    feed_url = st.selectbox('Optional source feed',['https://technivella.com/feed/','https://factozone.com/feed/'])
    if st.button('Import up to 5 feed ideas — no generation'):
        try:
            st.json(SourceInbox().feed(feed_url,count=5))
        except Exception as error:
            st.error(str(error))
    if st.button('Save source idea — no generation'):
        try:
            inbox = SourceInbox()
            item = inbox.paste(source_text,title=title,source_url=source_url) if source_text.strip() else inbox.fetch(source_url)
            st.session_state['source_inbox_item'] = item
        except Exception as error:
            st.error(str(error))
    item = st.session_state.get('source_inbox_item')
    if item:
        st.json({key:value for key,value in item.items() if key != 'text'})
        brief = SourceInbox().brief_prompt(item)
        st.download_button('Download external-writer brief',brief,file_name='original-content-brief.txt')
        st.code(brief)
    st.subheader('Chapter-based long-form template')
    topic = st.text_input('Long-form topic')
    locale = st.selectbox('Template language',['en','hi','or'])
    if topic:
        st.download_button('Download chapter/evidence template',json.dumps(longform_template(topic,locale),indent=2,ensure_ascii=False),
                           file_name='approved-content-plan.json',mime='application/json')
    st.info('Fill narration, chapters/scenes and rights; review facts and set approved=true. Import that JSON from STUDIO. Arena browser automation and automatic commercial-output rights are not provided.')

# ================= CHARACTER LIBRARY =================
elif page == 'CHARACTER LIBRARY':
    st.title('Original fictional character library')
    from engine.content_library import CharacterLibrary
    library = CharacterLibrary()
    name = st.text_input('Character name')
    description = st.text_area('Physical identity, clothes, palette, personality and visual style')
    references = st.text_area('Authorized reference image paths, one per line (optional)')
    original = st.checkbox('This is my original or authorized fictional character; not an impersonation')
    if st.button('Save character identity'):
        try:
            st.json(library.create(name,description,reference_files=references.splitlines(),original_confirmed=original))
        except Exception as error:
            st.error(str(error))
    for character in library.list():
        with st.expander(character['name']+' · '+character['id']):
            st.write(character['description'])
            for reference in character['references']:
                st.image(reference['path'],width=240)
    st.caption('Without a supplied reference, the recreation workflow asks Flow to generate a character master before scene images. Identity still needs visual review.')

# ================= AI RECREATE =================
elif page == 'AI RECREATE':
    st.title('Recreate an authorized clip with an original AI character')
    st.warning('This creates new scenes and narration, not a face swap or automatic copyright clearance. No original person is uploaded as a character reference. New TTS/Flow generation can cost credits after approval.')
    from engine.content_library import CharacterLibrary
    from engine.clip_recreation import create_recreation_job, approve_recreation
    characters = CharacterLibrary().list()
    recent = st.session_state.get('last_clip_result',{}).get('outputs',[])
    if recent:
        st.selectbox('Recently generated clips',recent,key='recreate-recent')
    clip = st.text_input('Generated/local clip path',value=st.session_state.get('recreate-recent',''))
    transcript = st.text_area('Reviewed transcript (optional when matching transcript sidecar exists)')
    locale = st.selectbox('Recreation language',['en','hi','or'])
    rights = st.selectbox('Transcript AND footage adaptation rights',['own_content','written_permission','licensed_content','creative_commons','public_domain'])
    confirmed = st.checkbox('I have reviewed the transcript and have rights to adapt it and the source video')
    budget = st.number_input('Maximum Flow credits for this new recreation',0,5000,50)
    music = st.text_input('Optional licensed soft music file')
    if characters:
        character_id = st.selectbox('Original character',[c['id'] for c in characters],format_func=lambda identifier:next(c['name'] for c in characters if c['id']==identifier))
        if st.button('Create recreation storyboard — no generation',type='primary'):
            try:
                result = create_recreation_job(F,clip,character_id,transcript_text=transcript,language=locale,
                                              source_rights=rights,adaptation_confirmed=confirmed,max_credits=int(budget),background_music=music)
                st.session_state['recreation_job'] = result['job_id'];st.json(result)
            except Exception as error:
                st.error(str(error))
    else:
        st.info('Create an original character in CHARACTER LIBRARY first.')
    recreation = st.session_state.get('recreation_job')
    if recreation:
        root = Path(F.pm.job_dir(recreation))
        st.code(str(root/'approved_content_plan.json'))
        st.json(json.loads((root/'approved_content_plan.json').read_text(encoding='utf-8')))
        approve = st.checkbox('I approve this exact storyboard, character and credit ceiling')
        if st.button('Approve recreation (does NOT start generation)',disabled=not approve):
            try:
                st.json(approve_recreation(F,recreation))
                st.session_state.job_id = recreation
                st.info('Use QUEUE → Resume explicitly to create the narration and new Flow scenes. Existing source clip remains unchanged.')
            except Exception as error:
                st.error(str(error))

# ================= PUBLISHING DESK =================
elif page == 'PUBLISHING DESK':
    st.title('Destination exports & release review')
    st.caption('First-stage local delivery desk. Approval/scheduling below are manual-upload records, not a connected social-account API.')
    from engine.publishing import PROFILES, export_delivery, approve_release, schedule_release
    source = st.text_input('Rendered video path')
    folder = st.text_input('Separate delivery folder',value='outputs/deliveries')
    destination = st.selectbox('Destination',list(PROFILES))
    locale = st.selectbox('Delivery language',['en','hi','or'])
    title = st.text_input('Localized title')
    framing = st.selectbox('Export framing',['fit','crop'])
    if st.button('Encode destination delivery (local only)'):
        try:
            with st.spinner('Encoding a separate destination copy; source is preserved'):
                record = export_delivery(source,folder,destination,language=locale,title=title,framing=framing)
            st.session_state['release_record_path'] = str(Path(folder)/(record['id']+'.release.json'))
            st.video(record['video']);st.json(record)
        except Exception as error:
            st.error(str(error))
    release_path = st.text_input('Delivery review JSON',value=st.session_state.get('release_record_path',''))
    account = st.text_input('Exact destination account/channel identifier')
    rights = st.checkbox('Visual/audio/transcript rights reviewed')
    facts = st.checkbox('Facts, story and intended audience reviewed')
    language_ok = st.checkbox('Native-language narration and text reviewed')
    kids = st.selectbox('Intended for children?',['Choose','Yes','No'])
    ai = st.selectbox('AI disclosure required for this delivery?',['Choose','Yes','No'])
    if st.button('Approve exact file for manual upload'):
        try:
            st.json(approve_release(release_path,account_id=account,rights_confirmed=rights,facts_reviewed=facts,
                                    language_reviewed=language_ok,made_for_kids=None if kids=='Choose' else kids=='Yes',
                                    ai_disclosure_required=None if ai=='Choose' else ai=='Yes'))
        except Exception as error:
            st.error(str(error))
    when = st.text_input('Optional local reminder: future ISO time with timezone',placeholder='2026-10-05T18:00:00+05:30')
    if st.button('Add local manual-upload reminder'):
        try:
            st.json(schedule_release(release_path,when))
        except Exception as error:
            st.error(str(error))

# ================= PRODUCTION QC =================
elif page == "PRODUCTION QC":
    st.title("Production review and local repair")
    st.caption("Checks the rendered job. Sampled semantic review is optional Gemini API use; it is separate from your browser subscription. No publication or Flow generation occurs here.")
    if not st.session_state.job_id:
        st.info("Select a rendered job in the sidebar.")
    else:
        from engine.production import init_review, check_job, stage_repairs, read
        root = Path(F.pm.job_dir(st.session_state.job_id))
        if st.button("Create review templates"):
            st.json(init_review(root))
        st.code(str(root / 'production'))
        st.caption("Edit rights.json, facts.json and graphics.json in this folder. See README section 16 for schemas and repair instructions.")
        model = st.text_input("Vision API model ID (optional)", value="")
        max_calls = st.number_input("Maximum API calls this review", 0, 100, 0)
        if st.button("Run production checks"):
            bar, status = st.progress(0), st.empty()
            def review_progress(message, pct, info=""):
                bar.progress(max(0, min(100, int(pct))))
                status.write(message + (' — ' + info if info else ''))
            try:
                with st.spinner("Checking media and evidence; progress is also recorded in job logs"):
                    check_job(root, model.strip(), int(max_calls), review_progress)
            except Exception as exc:
                st.error(str(exc))
        report = read(root / 'production/review.json', {})
        if report:
            st.json(report)
        plan = st.text_input("Edited local repair plan", value=str(root / 'production/repair_plan.json'))
        if st.button("Validate and stage local replacements"):
            try:
                st.json(stage_repairs(root, plan))
                st.info("Use RENDER for this same job, then run production checks again.")
            except Exception as exc:
                st.error(str(exc))

# ================= ASSETS =================
elif page == "ASSETS":
    st.title("🗂️ Assets")
    if not st.session_state.job_id:
        st.info("Select a job in the sidebar.")
    else:
        D = F.pm.dirs(st.session_state.job_id)
        for key in ("storyboard", "references", "downloads", "captions", "audio", "render"):
            with st.expander(f"📁 {key}", expanded=(key == "storyboard")):
                files = sorted(glob.glob(os.path.join(D[key], "*")))
                if not files:
                    st.caption("(empty)")
                for f in files[:24]:
                    if f.endswith((".jpg", ".png", ".jpeg", ".webp")):
                        st.image(f, caption=os.path.basename(f), width=240)
                    elif f.endswith((".mp4", ".webm", ".mov")):
                        st.video(f)
                    else:
                        st.write(os.path.basename(f), f"({os.path.getsize(f)//1024} KB)")

# ================= RENDER =================
elif page == "RENDER":
    st.title("🎞️ Render")
    if not st.session_state.job_id:
        st.info("Select a job in the sidebar.")
    else:
        from engine.render.ffmpeg_renderer import detect_encoder
        from engine.broll import load_review as load_broll_review, prepare_job_review, save_review as save_broll_review
        st.caption(f"Encoder: `{detect_encoder()}` · Target: 1080p + burned captions + ducked music + loudness.")
        D = F.pm.dirs(st.session_state.job_id)
        broll_review_path = os.path.join(D["render"], "broll_review.json")
        shots_for_broll = F.pm.load_manifest(st.session_state.job_id).shots
        estimated_timeline = sum(max(0.1, float(x.voice_end) - float(x.voice_start)) for x in shots_for_broll)
        with st.expander("🌿 Optional related stock B-roll cutaways", expanded=False):
            st.caption("Search at selected scene boundaries, preview the exact downloaded stock clip, adjust its position, then approve it. Approved cutaways replace only the picture for a few seconds; existing narration/music and final duration remain unchanged. Search uses the configured local stock library or stock provider. It never submits Flow/Veo generations. Review the asset licence before approval.")
            existing_broll = os.path.isfile(broll_review_path)
            b1, b2, b3 = st.columns(3)
            broll_count = b1.number_input("Maximum suggestions", min_value=1, max_value=10, value=3, step=1,
                                         key=f"broll-count-{st.session_state.job_id}")
            broll_duration = b2.slider("Cutaway duration (seconds)", 0.5, 6.0, 2.0, 0.5,
                                        key=f"broll-duration-{st.session_state.job_id}")
            replace_broll = b3.checkbox("Replace existing suggestion list", value=False,
                                        disabled=not existing_broll,
                                        key=f"broll-replace-{st.session_state.job_id}")
            if st.button("🔎 Find related stock cutaways", key=f"broll-search-{st.session_state.job_id}"):
                try:
                    with st.spinner("Searching configured stock sources; no Flow/Veo generation is submitted…"):
                        _path, review = prepare_job_review(
                            F, st.session_state.job_id, max_candidates=int(broll_count),
                            default_duration=float(broll_duration), replace=replace_broll)
                    st.success(f"Prepared {len(review.get('candidates', []))} candidate(s). Nothing is applied until you approve it.")
                except Exception as exc:
                    st.error(str(exc))
            if os.path.isfile(broll_review_path):
                try:
                    review = load_broll_review(broll_review_path)
                    approvals = {}
                    for candidate in review.get("candidates", []):
                        cid = str(candidate.get("candidate_id", "cutaway"))
                        st.markdown(f"**{candidate.get('label', cid)}**")
                        if candidate.get("path") and os.path.isfile(candidate["path"]):
                            st.video(candidate["path"])
                            st.caption("Query: " + str(candidate.get("query", "")) +
                                       " · Source: " + str(candidate.get("source", "stock")) +
                                       " · Licence: " + str(candidate.get("license", "review required")) +
                                       (" · Creator: " + str(candidate.get("creator")) if candidate.get("creator") else ""))
                            if candidate.get("page_url"):
                                st.markdown(f"[Open stock source page]({candidate['page_url']})")
                            max_start = max(0.0, estimated_timeline - 0.5)
                            start_default = min(max_start, max(0.0, float(candidate.get("start", 0) or 0)))
                            cut_start = st.number_input("Start time in final video (seconds)", 0.0, max_start,
                                                        start_default, 0.25, key=f"broll-start-{st.session_state.job_id}-{cid}")
                            max_cut_duration = max(0.5, min(6.0, estimated_timeline - float(cut_start)))
                            duration_default = min(max_cut_duration, max(0.5, float(candidate.get("duration", broll_duration) or broll_duration)))
                            cut_duration = st.slider("Use this many seconds", 0.5, max_cut_duration, duration_default, 0.5,
                                                      key=f"broll-length-{st.session_state.job_id}-{cid}")
                            reviewed = st.checkbox("I reviewed this exact clip and its licence/rights",
                                                   value=bool(candidate.get("rights_reviewed")),
                                                   key=f"broll-rights-{st.session_state.job_id}-{cid}")
                            approved = st.checkbox("Approve this cutaway for the final video",
                                                   value=bool(candidate.get("approved")),
                                                   key=f"broll-approve-{st.session_state.job_id}-{cid}")
                            approvals[cid] = {"start": float(cut_start), "duration": float(cut_duration),
                                              "rights_reviewed": reviewed, "approved": approved}
                        else:
                            st.warning(candidate.get("search_error", "No valid stock video was found for this gap."))
                    if st.button("💾 Save cutaway approvals", key=f"broll-save-{st.session_state.job_id}"):
                        try:
                            review = save_broll_review(broll_review_path, approvals)
                            count_approved = sum(1 for x in review.get("candidates", [])
                                                 if x.get("approved") and x.get("rights_reviewed"))
                            st.success(f"Saved {count_approved} approved cutaway(s). The render will use only these exact reviewed files.")
                        except Exception as exc:
                            st.error(str(exc))
                except Exception as exc:
                    st.error("Could not load B-roll review: " + str(exc))
        quality = st.radio("Quality", ["preview", "standard", "high"], horizontal=True)
        if st.button("🎬 Render final", type="primary"):
            render_bar = st.progress(0)
            render_status = st.empty()
            def render_cb(stage, pct, info=""):
                render_bar.progress(min(100, int(pct)))
                render_status.info(f"{stage} {info}")
            with st.spinner("Rendering..."):
                try:
                    r = F.render_job(st.session_state.job_id, quality=quality, progress_cb=render_cb)
                    st.success(f"Done via {r['renderer']} · {r.get('broll_cutaways', 0)} approved stock cutaway(s)")
                    st.video(r["video"])
                    with open(r["video"], "rb") as f:
                        st.download_button("⬇️ Download MP4", f, file_name=os.path.basename(r["video"]))
                    for k in ("ass", "srt"):
                        p = r["captions"][k]
                        with open(p, "rb") as f:
                            st.download_button(f"⬇️ {k.upper()}", f, file_name=os.path.basename(p))
                    if r.get("warnings"):
                        st.warning(" | ".join(r["warnings"]))
                except Exception as e:
                    st.error(f"Render failed: {e}")

# ================= HISTORY =================
elif page == "HISTORY":
    st.title("📚 History")
    done = [j for j in jobs if j["status"] == "done"]
    if not done:
        st.info("No finished productions yet.")
    for j in done[:15]:
        with st.expander(f"🎬 {j['topic'][:60]} · {j['updated_at']}"):
            st.caption(f"`{j['job_id']}` · {j['profile']} · gens {j['actual_generations']} · retries {j['retry_count']}")
            if j["final_path"] and os.path.exists(j["final_path"]):
                st.video(j["final_path"])
                with open(j["final_path"], "rb") as f:
                    st.download_button("⬇️ Download", f, file_name=os.path.basename(j["final_path"]), key=f"h-{j['job_id']}")

# ================= SETTINGS =================
elif page == "SETTINGS":
    st.title("⚙️ Settings")
    usp = "config/user_settings.yaml"
    cur = {}
    if os.path.exists(usp):
        cur = yaml.safe_load(open(usp, encoding="utf-8")) or {}
    b = cur.get("budgets", {})
    with st.form("settings"):
        s1, s2 = st.columns(2)
        tts = s1.selectbox("Default TTS", ["edge", "gtts", "kokoro", "chatterbox"],
                           index=["edge", "gtts", "kokoro", "chatterbox"].index(cur.get("tts_provider", "edge")))
        monthly = s2.number_input("Monthly Flow credits (your plan)", 0, 50000, int(cur.get("monthly_credits") or 1000))
        c1, c2, c3 = st.columns(3)
        maxv = c1.number_input("MAX_CREDITS_PER_VIDEO", 0, 2000, int(b.get("MAX_CREDITS_PER_VIDEO", 50)))
        maxr = c2.number_input("MAX_RETRIES_PER_SHOT", 0, 5, int(b.get("MAX_RETRIES_PER_SHOT", 2)))
        maxq = c3.number_input("MAX_QUALITY_GENERATIONS", 0, 10, int(b.get("MAX_QUALITY_GENERATIONS", 1)))
        c4, c5 = st.columns(2)
        reserve = c4.number_input("USER_RESERVE", 0, 2000, int(b.get("USER_RESERVE", 50)))
        retrypct = c5.number_input("RETRY_RESERVE_PCT", 0, 100, int(b.get("RETRY_RESERVE_PCT", 15)))
        st.markdown("**🌱 Storyboard Economy defaults**")
        ec1, ec2, ec3, ec4a = st.columns(4)
        g_video_share = ec1.slider("Default AI-video share", 0.0, 1.0, float(cur.get("video_share", 0.20)), 0.05)
        g_stock_share = ec2.slider("Default stock-video share", 0.0, 1.0, float(cur.get("stock_share", 0.60)), 0.05)
        g_flow_scenes = ec3.number_input("Default exact Flow scenes (0=auto)", 0, 100, int(cur.get("flow_scenes") or 0))
        g_max_flow = ec4a.number_input("Default max Flow scenes (0=no cap)", 0, 100, int(cur.get("max_flow_scenes") or 0))
        ec4, ec5, ec6 = st.columns(3)
        fs_opts = ["auto", "flow", "free"]
        g_frame_source = ec4.selectbox("Default frame source", fs_opts, index=fs_opts.index(cur.get("frame_source", "auto")) if cur.get("frame_source", "auto") in fs_opts else 0)
        ap_opts = ["once", "manual", "always"]
        g_approval = ec5.selectbox("Default Flow approval", ap_opts, index=ap_opts.index(cur.get("flow_approval", "once")) if cur.get("flow_approval", "once") in ap_opts else 0)
        g_gen_cap = ec6.number_input("Default per-generation credit cap", 0, 200, int(cur.get("max_generation_credits", 10)))
        g_pause_flow = st.checkbox(
            "Pause unresolved Flow requests by default (opt-in)",
            value=_flow_pause_setting_default(),
            help="When off, unresolved images fall back only in auto frame mode; strict images and videos fail without entering PAUSED. When on, they are saved and paused for a deliberate Resume. Recovery retries download-only first; a replacement may use image credits, but only once after two full scans prove the original absent.")
        st.markdown("**🌐 Flow browser** (which Chrome to drive)")
        br = cur.get("browser", {}) or {}
        bmodes = ["auto", "system", "bundled", "cdp"]
        bmode = st.selectbox("Browser mode", bmodes,
                             index=bmodes.index(br.get("mode", "auto")) if br.get("mode", "auto") in bmodes else 0,
                             help="auto=tries your Chrome first, then bundled. system=your installed Chrome only. cdp=attach to YOUR open browser (uses your existing Google login!). bundled=playwright download.")
        bc1, bc2 = st.columns(2)
        chans = ["chrome", "chromium", "msedge"]
        bchan = bc1.selectbox("System channel", chans,
                              index=chans.index(br.get("channel", "chrome")) if br.get("channel", "chrome") in chans else 0)
        bcdp = bc2.text_input("CDP URL (cdp mode)", value=br.get("cdp_url", ""),
                              placeholder="http://localhost:9222")
        bexe = st.text_input("Chrome executable override (optional)", value=br.get("executable", ""),
                             placeholder="e.g. /usr/bin/google-chrome (native path only — never a /mnt/c/... .exe from WSL)")
        if st.form_submit_button("💾 Save settings"):
            yaml.safe_dump({**cur, "tts_provider": tts, "monthly_credits": monthly,
                            "budgets": {"MAX_CREDITS_PER_VIDEO": maxv, "MAX_RETRIES_PER_SHOT": maxr,
                                        "MAX_QUALITY_GENERATIONS": maxq, "USER_RESERVE": reserve,
                                        "RETRY_RESERVE_PCT": retrypct},
                            "video_share": g_video_share, "stock_share": g_stock_share,
                            "flow_scenes": (int(g_flow_scenes) or None),
                            "max_flow_scenes": (int(g_max_flow) or None),
                            "frame_source": g_frame_source, "flow_approval": g_approval,
                            "max_generation_credits": int(g_gen_cap),
                            "flow_pause_on_unresolved_request": g_pause_flow,
                            "browser": {"mode": bmode, "channel": bchan,
                                        "executable": bexe, "cdp_url": bcdp}},
                           open(usp, "w", encoding="utf-8"))
            st.success("Saved to config/user_settings.yaml")
    from engine.providers import find_system_chrome as _find_chrome, is_wsl as _is_wsl, is_windows_exe as _is_wexe
    _det = _find_chrome()
    if _det and _is_wsl() and _is_wexe(_det):
        st.caption(f"🔍 Windows Chrome visible: `{_det}` — not directly launchable from WSL; use **cdp** mode (chrome-debug.bat) or **bundled**.")
    else:
        st.caption(f"🔍 Detected system Chrome: `{_det}`" if _det else "🔍 No system Chrome detected — CDP or bundled mode, or install Chrome.")
    st.divider()
    st.subheader("🔑 Keys & providers")
    import shutil as _sh
    checks = [("GEMINI_API_KEY (Gemini scripts/TTS)", bool(os.getenv("GEMINI_API_KEY"))),
              ("GROQ_API_KEY (scripts/captions/TTS)", bool(os.getenv("GROQ_API_KEY"))),
              ("ELEVENLABS_API_KEY (optional TTS)", bool(os.getenv("ELEVENLABS_API_KEY"))),
              ("OPENAI_API_KEY (optional scripts)", bool(os.getenv("OPENAI_API_KEY"))),
              ("XAI_API_KEY (optional scripts)", bool(os.getenv("XAI_API_KEY"))),
              ("FAL_KEY (Seedance/Kling)", bool(os.getenv("FAL_KEY"))),
              ("Local stock library (assets/stock_library)", os.path.isdir("assets/stock_library")),
              ("PEXELS_API_KEY (optional stock search)", bool(os.getenv("PEXELS_API_KEY"))),
              ("PIXABAY_API_KEY (optional stock search)", bool(os.getenv("PIXABAY_API_KEY"))),
              ("FFmpeg", bool(_sh.which("ffmpeg"))),
              ("Playwright browser", os.path.exists(os.path.expanduser("~/.cache/ms-playwright"))),
              ("Flow profile (.flow-profile)", os.path.isdir(".flow-profile") and bool(os.listdir(".flow-profile")) if os.path.isdir(".flow-profile") else False)]
    for name, ok in checks:
        st.write(("✅ " if ok else "⬜ ") + name)
    found_env = ENV_REPORT.get("files_found") or []
    st.caption("Environment file: " + (found_env[0] if found_env else "not found"))
    if ENV_REPORT.get("aliases_used"):
        st.caption("Normalized aliases: " + ", ".join(ENV_REPORT["aliases_used"]))
    st.code("pip install playwright\nplaywright install chromium   # one-time, for Flow browser bridge", language="bash")

# ================= Quick v2 =================
else:
    st.title("⚡ Quick (v2 pipeline)")
    st.caption("Legacy fast path: topic → video in one shot (Ken Burns / stock / API).")
    topic = st.text_input("Topic", key="v2t")
    cc1, cc2 = st.columns(2)
    vm = cc1.selectbox("Visuals", ["auto", "flow", "stock", "ai", "kenburns"], key="v2vm")
    vtype = cc2.selectbox("Type", ["shorts", "faceless_youtube", "explainer", "marketing"], key="v2vt")
    if st.button("🚀 Generate (v2)", type="primary"):
        from engine.automation import create_video_from_topic
        bar = st.progress(0)
        stxt = st.empty()
        try:
            with st.spinner("Generating..."):
                r = create_video_from_topic(topic, vtype, 45, "en-IN-NeerjaNeural", "exciting",
                                            outdir="outputs", visual_mode=vm,
                                            progress_cb=lambda s, p: (stxt.info(s), bar.progress(p)))
            st.success(f"Done: {r['video']}")
            st.video(r["video"])
        except Exception as e:
            st.error(str(e))

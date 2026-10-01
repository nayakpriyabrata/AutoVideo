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
page = st.sidebar.radio("Navigate", ["STUDIO", "CREATE", "STORYBOARD", "DIRECTOR REVIEW", "QUEUE",
                                     "FLOW SESSION", "CLIP STUDIO", "PRODUCTION QC", "ASSETS", "RENDER", "HISTORY",
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
        st.info("Resume checks the saved request for the exact pending image or video. "
                "An unresolved request remains paused without generating again. "
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
        status.success(f"{r.get('status')}: {r.get('message', r.get('video', ''))}")
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
                                       help="Each worker uses an isolated browser profile. Start with 1; Google may throttle 2–3.")
            frame_source = i.selectbox("Frame source", ["auto", "flow", "free"])
            flow_approval = j.selectbox("Flow credit approval", ["once", "manual", "always"])
            flow_project_url = st.text_input("Existing Google Flow project URL (optional)",
                                             placeholder="https://flow.google.com/project/<uuid>",
                                             help="Stored with the job and automatically reused on resume.")
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
                        "script_provider": script_provider, "tts_provider": tts_provider,
                        "render_quality": render_quality, "flow_image_workers": flow_workers,
                        "frame_source": frame_source, "flow_approval": flow_approval,
                        "flow_project_url": flow_project_url.strip(), "flow_reuse_mode": reuse_mode,
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
            language = a2.selectbox("Language", ["en", "hi"])
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
    rights = r3.selectbox("Source rights", [
        "own_content", "written_permission", "licensed_content", "creative_commons",
        "public_domain", "commentary_or_review", "private_draft_only",
    ])
    st.warning("Captions, music, cropping, zoom or motion alone do not make somebody else's video copyright-safe. AutoVideoAI records your declaration but cannot grant legal rights.")
    output_dir = st.text_input("Output folder", value="outputs/my-clips")
    with st.expander("Optional licensed background music"):
        background_music = st.text_input("Local music file", value="")
        m1, m2 = st.columns(2)
        music_license = m1.selectbox("Music licence", [
            "none", "own", "youtube_audio_library", "royalty_free_licensed", "creative_commons",
        ])
        music_volume = m2.slider("Music volume", 0.0, 0.35, 0.08, 0.01)
    gemini_cleanup = st.selectbox("Temporary Gemini browser chat", ["delete-after-read", "keep"])
    framing = st.selectbox("Framing", ["face-crop", "fit"],
                           help="Fit keeps the complete picture. Face crop uses a static estimate and may miss speaker changes.")
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
                    background_music=background_music.strip(),
                    music_license=music_license, music_volume=float(music_volume),
                    gemini_chat_cleanup=gemini_cleanup,
                    framing=framing,
                    progress_cb=clip_progress)
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
        st.caption(f"Encoder: `{detect_encoder()}` · Target: 1080p + burned captions + ducked music + loudness.")
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
                    st.success(f"Done via {r['renderer']}")
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

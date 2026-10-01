"""
Automation Orchestrator (v2)
Topic -> Script -> Voiceover -> Visuals -> Video (one call)

visual_mode:
  auto     - Flow folder -> stock video -> AI video -> Ken Burns (first available wins)
  flow     - clips from assets/flow_clips/ (generate in Flow app with your subscription!)
  stock    - free stock motion footage (needs free PEXELS_API_KEY or PIXABAY_API_KEY)
  ai       - AI-generated motion (Veo / Seedance / fal / ComfyUI)
  kenburns - free AI images + zoom (v1 style, always works)
"""
import os
import re
import csv
import glob
import time
import datetime
from .script_generator import generate_script
from .voiceover import text_to_speech
from .visuals import get_visuals
from .video_builder import build_video, build_video_from_clips


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")
    return s[:50] or "video"


def _is_vertical(video_type: str, duration_sec: int) -> bool:
    if video_type == "marketing":
        return duration_sec <= 65
    return video_type in ("shorts",)


def _find_music() -> str | None:
    files = sorted(glob.glob("assets/music/*.mp3") + glob.glob("assets/music/*.wav"))
    return files[0] if files else None


def prepare_flow_shots(topic: str, video_type: str = "shorts",
                       duration_sec: int = 45, tone: str = "exciting",
                       outdir: str = "outputs") -> dict:
    """Stop after script + shot list: for the Flow-app subscription workflow."""
    from .ai_video import plan_shots
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    job = f"{stamp}-{_slug(topic)}-shots"
    workdir = os.path.join(os.path.abspath(outdir), job)
    os.makedirs(workdir, exist_ok=True)
    sc = generate_script(topic, video_type, duration_sec, tone)
    vertical = _is_vertical(video_type, duration_sec)
    plan = plan_shots(sc["scenes"], topic, vertical, workdir)
    with open(os.path.join(workdir, "script.txt"), "w", encoding="utf-8") as f:
        f.write(f"Title: {sc['title']}\n\n{sc['script']}\n")
    return {"workdir": workdir, "title": sc["title"], "script": sc["script"],
            "shots": plan["shots"], "shot_list_md": plan["shot_list_md"],
            "vertical": vertical}


def create_video_from_topic(topic: str, video_type: str = "shorts",
                            duration_sec: int = 45, voice: str = "en-IN-NeerjaNeural",
                            tone: str = "exciting", watermark: str = "",
                            outdir: str = "outputs",
                            visual_mode: str = "auto",
                            ai_provider: str = "veo",
                            caption_style: str = "wordpop",
                            use_music: bool = True,
                            flow_folder: str = "assets/flow_clips",
                            progress_cb=None) -> dict:
    """Fully automated pipeline. Returns dict with all artifacts."""
    from .ai_video import (plan_shots, collect_flow_clips, generate_ai_clips,
                           provider_key_present, COST_PER_SEC)
    from .stock_video import get_stock_videos
    from .captions import get_word_timestamps

    def prog(stage, pct):
        if progress_cb:
            try:
                progress_cb(stage, pct)
            except Exception:
                pass

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    job = f"{stamp}-{_slug(topic)}"
    base = os.path.abspath(outdir)
    workdir = os.path.join(base, job)
    os.makedirs(workdir, exist_ok=True)
    vertical = _is_vertical(video_type, duration_sec)

    # 1) Script
    prog("✍️ Writing script...", 10)
    sc = generate_script(topic, video_type, duration_sec, tone)

    # 2) Voiceover
    prog("🎙️ Generating voiceover...", 30)
    audio_path = os.path.join(workdir, "voice.mp3")
    vo = text_to_speech(sc["script"], audio_path, voice=voice)

    # 3) Visuals (mode cascade)
    prog("🎨 Getting visuals...", 50)
    clips, visual_used, cost = [], "kenburns", 0.0

    if visual_mode in ("auto", "flow"):
        found = collect_flow_clips(flow_folder)
        if found:
            clips, visual_used = found, "flow"
        elif visual_mode == "flow":
            raise FileNotFoundError(
                f"No clips in {flow_folder}/. Generate them in Flow (see the "
                f"'Flow Shot List' tab for copy-paste prompts), save as shot00.mp4... "
                f"into {flow_folder}/, then retry.")

    if not clips and visual_mode in ("auto", "stock"):
        prog("🎥 Fetching stock footage...", 55)
        sv = get_stock_videos(sc["scenes"], topic, os.path.join(workdir, "scenes"), vertical)
        if sv["clips"]:
            clips, visual_used = sv["clips"], f"stock({sv['source']})"
        elif visual_mode == "stock":
            raise RuntimeError("Stock mode needs a free PEXELS_API_KEY or PIXABAY_API_KEY in .env.")

    if not clips and visual_mode in ("auto", "ai"):
        if provider_key_present(ai_provider):
            plan = plan_shots(sc["scenes"], topic, vertical, workdir)
            est = round(COST_PER_SEC.get(ai_provider, 0) * (vo["duration"] or duration_sec), 2)
            print(f"AI video via {ai_provider} — estimated cost ≈ ${est}")
            gen = generate_ai_clips(plan["shots"], ai_provider, vertical,
                                    os.path.join(workdir, "scenes"), prog)
            clips, visual_used, cost = gen["clips"], f"ai({gen['source']})", gen.get("cost_usd", est)
        elif visual_mode == "ai":
            need = "GEMINI_API_KEY" if ai_provider == "veo" else ("FAL_KEY" if ai_provider in ("seedance", "fal") else "running ComfyUI + assets/comfy_workflow.json")
            raise RuntimeError(f"AI mode '{ai_provider}' needs {need}. See README v2 setup.")

    # 4) Build
    suffix = "short" if vertical else "video"
    out_path = os.path.join(workdir, f"{_slug(topic)}-{suffix}.mp4")
    if clips:
        prog("🎬 Editing motion video...", 75)
        words = get_word_timestamps(audio_path) if caption_style == "wordpop" else None
        if caption_style == "wordpop" and not words:
            print("Word captions unavailable -> classic captions.")
        music = _find_music() if use_music else None
        if use_music and not music:
            print("No music in assets/music/ -> skipping music bed.")
        vb = build_video_from_clips(clips, vo["audio"], sc["script"], sc["scenes"],
                                    out_path, title=sc["title"], vertical=vertical,
                                    watermark=watermark, music_path=music,
                                    words=words, caption_style=caption_style)
    else:
        prog("🎨 Creating visuals (Ken Burns)...", 55)
        vis = get_visuals(sc["scenes"], topic, os.path.join(workdir, "scenes"), vertical=vertical)
        prog("🎬 Editing video...", 80)
        vb = build_video(vis["images"], vo["audio"], sc["script"], sc["scenes"],
                         out_path, title=sc["title"], vertical=vertical, watermark=watermark)
        visual_used = f"kenburns({vis['source']})"

    prog("✅ Done!", 100)
    meta = os.path.join(workdir, "details.txt")
    with open(meta, "w", encoding="utf-8") as f:
        f.write(f"Title: {sc['title']}\nTopic: {topic}\nType: {video_type}\n")
        f.write(f"Duration: {vb['duration']:.1f}s | Size: {vb['size']}\n")
        f.write(f"Visuals: {visual_used} | AI cost: ${cost:.2f}\n")
        f.write(f"Script engine: {sc['source']} | Voice: {vo['engine']}\n")
        f.write(f"Captions: {vb.get('captions', 'classic')} | Music: {vb.get('music', False)}\n")
        f.write(f"\n--- SCRIPT ---\n{sc['script']}\n")

    return {
        "job": job, "workdir": workdir, "video": vb["video"],
        "audio": vo["audio"], "script": sc["script"], "title": sc["title"],
        "duration": vb["duration"], "size": vb["size"],
        "visual_used": visual_used, "cost_usd": cost,
        "engines": {"script": sc["source"], "voice": vo["engine"], "visuals": visual_used},
        "vertical": vertical, "meta": meta,
    }


def bulk_create_from_csv(csv_path: str, outdir: str = "outputs", progress_cb=None,
                         visual_mode: str = "auto", ai_provider: str = "veo") -> list:
    """Read topics.csv and create all videos. CSV may override visual_mode/ai_provider per row."""
    results = []
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        topic = (r.get("topic") or "").strip()
        if not topic:
            continue
        try:
            res = create_video_from_topic(
                topic=topic,
                video_type=(r.get("video_type") or "shorts").strip(),
                duration_sec=int(r.get("duration_sec") or 45),
                voice=(r.get("voice") or "en-IN-NeerjaNeural").strip(),
                tone=(r.get("tone") or "exciting").strip(),
                outdir=outdir,
                visual_mode=(r.get("visual_mode") or visual_mode).strip(),
                ai_provider=(r.get("ai_provider") or ai_provider).strip(),
                progress_cb=(lambda s, p, idx=i: progress_cb(f"[{idx+1}/{len(rows)}] {s}", p)) if progress_cb else None,
            )
            res["topic"] = topic
            results.append(res)
        except Exception as e:
            results.append({"topic": topic, "error": str(e)})
        time.sleep(1)
    return results


def fetch_trending_topics(count: int = 10) -> list:
    """Free trending topics via Google Trends RSS (India + World). No key."""
    topics = []
    try:
        import feedparser
        for url in ("https://trends.google.com/trends/trendingsearches/daily/rss?geo=IN",
                    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"):
            d = feedparser.parse(url)
            for e in d.entries[:count]:
                t = e.get("title", "").strip()
                if t and t not in topics:
                    topics.append(t)
            if len(topics) >= count:
                break
    except Exception:
        pass
    if not topics:
        topics = ["AI tools", "Make money online", "Healthy habits",
                  "Stock market basics", "IPL highlights", "Space news",
                  "Movie reviews", "Study motivation", "Tech news", "Travel hacks"]
    return topics[:count]


# ==================== v3 factory wrappers ====================

def v3_create_and_run(topic: str, video_type: str = "shorts", duration_sec: int = 45,
                      profile: str = "FLOW_BALANCED", preset: str = "cinematic_realism",
                      content_type: str = "education", tone: str = "cinematic",
                      voice: str = "en-IN-PrabhatNeural", dry_run: bool = False,
                      progress_cb=None, **kw) -> dict:
    """Create a v3 production job and run it (resumable)."""
    from .factory import Factory
    aspect = "9:16" if video_type in ("shorts",) or (video_type == "marketing" and duration_sec <= 65) else "16:9"
    f = Factory()
    job_id = f.create_job(topic, video_type, duration_sec, aspect,
                           voice=voice, content_type=content_type, tone=tone,
                           preset=preset, profile=profile, dry_run=dry_run)
    return f.run_job(job_id, progress_cb=progress_cb)


def v3_resume(job_id: str, progress_cb=None) -> dict:
    from .factory import Factory
    return Factory().run_job(job_id, progress_cb=progress_cb)


def v3_render(job_id: str, quality: str = "standard", progress_cb=None) -> dict:
    from .factory import Factory
    return Factory().render_job(job_id, quality=quality, progress_cb=progress_cb)

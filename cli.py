"""
CLI - Full automation without browser (v2)
Examples:
  python cli.py --topic "5 AI tools" --type shorts
  python cli.py --topic "5 AI tools" --visual-mode flow
  python cli.py --topic "5 AI tools" --visual-mode ai --ai-provider veo
  python cli.py --shot-list "My topic" --type shorts     (Flow subscription workflow)
  python cli.py --bulk topics.csv
  python cli.py --trending 5
"""
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from engine.env_config import load_environment, format_environment_report


def _load_env_with_migration():
    """Load local .env, then fill any *missing* API keys from older installs.

    Older builds returned as soon as one key existed. A folder containing only a
    Gemini key could therefore make ``--script-provider groq`` look unconfigured
    even when a sibling version had the Groq key. v5.4 merges missing secrets
    without overriding values from the current installation.
    """
    load_dotenv()
    keys = ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY")
    missing_before = {k for k in keys if not os.getenv(k)}
    if not missing_before:
        return
    candidates = []
    shared = Path.home() / ".config" / "autovideoai" / ".env"
    if shared.is_file():
        candidates.append(shared)
    here = Path(__file__).resolve().parent
    parent = here.parent
    siblings = []
    for q in parent.glob("AutoVideoAI-v*/.env"):
        try:
            if q.resolve() != (here / ".env").resolve():
                siblings.append(q)
        except Exception:
            siblings.append(q)
    siblings.sort(key=lambda q: q.stat().st_mtime if q.exists() else 0, reverse=True)
    candidates.extend(siblings)
    loaded_from = []
    for env_path in candidates:
        before = {k for k in keys if os.getenv(k)}
        load_dotenv(env_path, override=False)
        after = {k for k in keys if os.getenv(k)}
        if after - before:
            loaded_from.append(env_path.parent.name)
        if all(os.getenv(k) for k in keys):
            break
    if loaded_from:
        print("[Config] Filled missing API credentials from " + ", ".join(loaded_from) + " (secrets not copied).")


_load_env_with_migration()
_ENV_REPORT = load_environment(Path(__file__).resolve().parent)


def main_v3(argv):
    from pathlib import Path
    """Factory CLI: python cli.py v3 <create|resume|status|render|queue|support-report>."""
    from engine.factory import Factory
    ap = argparse.ArgumentParser(prog="cli.py v3", description="AutoVideoAI v3 factory")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="Create + run a production")
    c.add_argument("--topic", required=True)
    c.add_argument("--type", dest="video_type", default="shorts",
                   choices=["shorts", "faceless_youtube", "explainer", "marketing"])
    c.add_argument("--duration", type=int, default=45)
    c.add_argument("--language", default="en", choices=["en","hi","or"])
    c.add_argument("--destination", default=None, choices=["instagram_reel","facebook_reel","youtube_short","youtube_long"])
    c.add_argument("--approved-plan-path", default="", help="reviewed external JSON script/storyboard")
    c.add_argument("--narration-input-path", default="", help="native narration file you own/are licensed to use")
    c.add_argument("--character-id", default="", help="original character from the local library")
    c.add_argument("--profile", default="FLOW_BALANCED",
                   choices=["FLOW_CINEMATIC", "FLOW_BALANCED", "FLOW_ECONOMY", "STORYBOARD_ECONOMY", "LOCAL_FREE", "FREE_HYBRID", "MANUAL_DIRECTOR"])
    c.add_argument("--preset", default="cinematic_realism")
    c.add_argument("--content-type", default="education")
    c.add_argument("--cartoon-provider", default="flow", choices=["flow", "movieflow"],
                   help="cartoon/kids-story visual engine: flow keeps the Google Flow workflow; movieflow uses MovieFlow Studio")
    c.add_argument("--movieflow-mode", default="full_story", choices=["full_story", "scenes"],
                   help="MovieFlow: full_story sends the complete cartoon story once; scenes uses MovieFlow only for AI-motion shots")
    c.add_argument("--movieflow-project-url", default="",
                   help="optional existing MovieFlow Studio project/workspace URL to reuse")
    c.add_argument("--movieflow-wait-seconds", type=int, default=1800,
                   help="maximum time to wait for a submitted MovieFlow video/story generation (default 1800s)")
    c.add_argument("--movieflow-recovery-wait-seconds", type=int, default=300,
                   help="if the MovieFlow tab/session closes after submit, reopen the project and wait this long for the already-running job instead of generating again")
    c.add_argument("--tone", default="cinematic")
    c.add_argument("--voiceover", dest="voiceover_enabled", action=argparse.BooleanOptionalAction, default=None,
                   help="include narration; --no-voiceover skips TTS/ASR entirely and uses a visual story clock")
    c.add_argument("--text-cards", dest="text_cards_enabled", action=argparse.BooleanOptionalAction, default=None,
                   help="editorial title/key-point/recap cards; --no-text-cards also overrides Pro mode and custom graphics")
    c.add_argument("--text-card-style", choices=["auto", "bold", "playful", "clean"], default="auto")
    c.add_argument("--background-music-path", default="", help="licensed local music file; choose --background-music local")
    c.add_argument("--music-volume", type=float, default=None, help="music gain 0..1; auto defaults to a foreground instrumental level without voiceover")
    c.add_argument("--sound-effects", dest="sound_effects_enabled", action=argparse.BooleanOptionalAction, default=None)
    c.add_argument("--ambience", dest="ambience_enabled", action=argparse.BooleanOptionalAction, default=None)
    c.add_argument("--voice", default="en-IN-PrabhatNeural",
                   help="legacy/Edge voice name; provider-specific voice can be set with --tts-voice")
    c.add_argument("--script-provider", default="auto",
                   choices=["auto", "gemini", "gemini-web", "groq", "openai", "grok", "ollama", "planner"],
                   help="v5 script director; gemini-web uses your signed-in Gemini browser; auto can include it when AUTOVIDEO_ENABLE_GEMINI_WEB=1")
    c.add_argument("--script-model", default="auto",
                   help="optional exact model ID for the chosen script provider")
    c.add_argument("--script-quality", default="publish", choices=["standard", "high", "publish"],
                   help="publish (default) requires an AI writer and passes strict editorial/list/topic-drift QC before visuals are generated")
    c.add_argument("--tts-provider", default="auto",
                   choices=["auto", "gemini", "gemini-lite", "groq", "elevenlabs", "kokoro", "edge", "gtts", "mock"],
                   help="narration provider; auto is quality/free-first and keeps gTTS last")
    c.add_argument("--tts-model", default="", help="optional provider-specific TTS model ID")
    c.add_argument("--tts-voice", default="", help="provider-specific voice ID/name (Gemini/ElevenLabs/Kokoro)")
    c.add_argument("--tts-style", default="warm, confident YouTube narrator; conversational and human; varied emphasis; medium energy; short natural pauses before numbered sections; brighter tone when introducing each new point; slower on key takeaways; never salesy or robotic",
                   help="delivery direction for controllable TTS providers")
    c.add_argument("--caption-provider", default="auto", choices=["auto", "groq", "local", "script-timed"],
                   help="caption timing; script-timed uses exact authored text + measured audio duration and needs no Whisper/API")
    c.add_argument("--caption-model", default="whisper-large-v3-turbo",
                   help="Groq speech-to-text model for timing")
    c.add_argument("--caption-local-model", default="small",
                   help="faster-whisper fallback model (small is much more accurate than old tiny default)")
    c.add_argument("--no-caption-script-align", dest="caption_align_script", action="store_false", default=True,
                   help="disable exact-script caption correction (not recommended)")
    c.add_argument("--max-tts-speedup", type=float, default=1.08,
                   help="maximum final narration speed-up; v5 rewrites overlong scripts first")
    c.add_argument("--no-auto-retime-script", dest="auto_retime_script", action="store_false", default=True,
                   help="disable automatic script rewrite when measured TTS is much longer than target")
    c.add_argument("--render-quality", default="high", choices=["preview", "standard", "high"],
                   help="final FFmpeg quality used by automatic render; high is the publish-ready default")
    c.add_argument("--production-mode", default="legacy", choices=["legacy", "youtube_pro"],
                   help="youtube_pro enables mixed stock/Flow motion, editorial graphics, stereo master and publish QC")
    c.add_argument("--dynamic-video-scenes", type=int, default=None,
                   help="youtube_pro target number of true-motion clips across the video (default ~= one every 30s)")
    c.add_argument("--stock-scenes", type=int, default=None,
                   help="exact target number of royalty-free stock-video slots; youtube_pro auto-fills the balance")
    c.add_argument("--stock-source", default="auto", choices=["auto", "api", "browser", "local"],
                   help="stock footage: local library first; auto uses free Pexels/Pixabay APIs when keys exist then isolated browser fallback")
    c.add_argument("--caption-display", default="auto", choices=["auto", "full", "none"],
                   help="burn transcript captions into video; youtube_pro auto=none while SRT/ASS are still generated for YouTube CC")
    c.add_argument("--background-music", default="off", choices=["off", "auto", "local", "browser"],
                   help="soft royalty-free music; auto uses local assets then isolated Pixabay browser fallback")
    c.add_argument("--music-mood", default="",
                   help="search/style hint for background music, e.g. 'soft motivational ambient instrumental'")
    c.add_argument("--channel-name", default="", help="channel name used for subtle watermark and end-screen branding")
    c.add_argument("--channel-logo", default="", help="optional PNG/JPG logo path for intro/outro graphics")
    c.add_argument("--graphics-overlays", action="store_true",
                   help="enable editorial cards/key points; automatically enabled by youtube_pro")
    c.add_argument("--watermark", action="store_true",
                   help="enable a subtle channel-name watermark (off unless explicitly requested)")
    c.add_argument("--max-credits", type=int, default=100)
    c.add_argument("--max-retries", type=int, default=2)
    c.add_argument("--images-per-shot", type=int, default=2,
                   help="Scene stills per shot via Flow image gen (0=skip)")
    c.add_argument("--video-share", type=float, default=0.20,
                   help="STORYBOARD_ECONOMY: target fraction of scenes that deserve paid AI motion")
    c.add_argument("--stock-share", type=float, default=0.60,
                   help="STORYBOARD_ECONOMY: target fraction of generic B-roll scenes to use stock")
    c.add_argument("--flow-scenes", type=int, default=None,
                   help="exact target number of paid Flow motion scenes; budget cap still applies")
    c.add_argument("--max-flow-scenes", type=int, default=None,
                   help="hard cap on paid Flow motion scenes (not a requested count; budget cap still applies)")
    c.add_argument("--frame-source", default="auto", choices=["auto", "flow", "free"],
                   help="opening/closing stills: auto=retry Flow then visibly fall back; flow=strict Flow only; free=free provider only")
    c.add_argument("--pause-on-unresolved-flow-request", dest="flow_pause_on_unresolved_request",
                   action=argparse.BooleanOptionalAction, default=None,
                   help="opt in to PAUSED jobs when a Flow request cannot be safely recovered; default is no automatic pause. Image recovery retries downloads first and permits at most one credit-bearing replacement after two scans prove absence")
    c.add_argument("--flow-approval", default="once", choices=["once", "manual", "always"],
                   help="Flow Agent credit confirmation behavior for paid motion scenes")
    c.add_argument("--max-generation-credits", type=int, default=10,
                   help="hard safety cap for any one Flow video generation")
    c.add_argument("--shot-max-seconds", type=float, default=None,
                   help="maximum narration seconds per visual shot; useful for long-form pacing (e.g. 8)")
    c.add_argument("--flow-frame-retries", type=int, default=3,
                   help="Flow still-image attempts before strict failure/fallback (default 3)")
    c.add_argument("--network-wait-seconds", type=int, default=300,
                   help="pause this long for temporary Internet loss before failing (default 300s)")
    c.add_argument("--flow-capacity-wait-seconds", type=int, default=900,
                   help="maximum time to recover Flow Agent high-demand responses before pausing (default 900s)")
    c.add_argument("--flow-capacity-retries", type=int, default=8,
                   help="Try-again clicks for Flow Agent high-demand recovery (default 8)")
    c.add_argument("--flow-project-url", default="",
                   help="reuse an exact https://flow.google.com/project/<uuid> project; resume stores/reuses it automatically")
    c.add_argument("--flow-video-retries", type=int, default=1,
                   help="extra Flow video attempts after recovery is exhausted (default 1 = retry once)")
    c.add_argument("--flow-video-ready-grace-seconds", type=int, default=20,
                   help="after Flow stops showing generation progress, keep waiting for a real video/download-ready tile before probing an untyped tile (default 20s)")
    c.add_argument("--flow-video-recovery-wait-seconds", type=int, default=180,
                   help="when the Flow page/session closes after generation, wait this long for the already-generated video to appear before submitting a new video request (default 180s)")
    c.add_argument("--flow-reuse-mode", default="exact", choices=["exact", "topic", "project"],
                   help="Flow-project reuse scope: exact=prompt fingerprint only (publish-safe default); topic/project are faster but may reuse visuals from an older script")
    c.add_argument("--no-flow-reuse-project-media", dest="flow_reuse_project_media", action="store_false", default=True,
                   help="disable frame/media reuse for a reused Flow project")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--plan-only", action="store_true", help="Create the job configuration only; run v3 resume to execute it")

    cc = sub.add_parser("create-config", help="Create + run from a simple commented YAML file")
    cc.add_argument("config", help="path to video_config.yaml")
    cc.add_argument("--plan-only", action="store_true", help="create the resumable job without running it")

    sub.add_parser("themes", help="List Studio themes and their defaults")
    dash = sub.add_parser("dashboard", help="Open the HTML Studio dashboard")
    dash.add_argument("--port", type=int, default=8501)

    r = sub.add_parser("resume", help="Resume a job")
    r.add_argument("job_id")
    r.add_argument("--gemini-chat-cleanup", choices=["keep", "delete-after-read"], default=None,
                   help="Persist this cleanup policy for the existing job before resuming")
    r.add_argument("--pause-on-unresolved-flow-request", dest="flow_pause_on_unresolved_request",
                   action=argparse.BooleanOptionalAction, default=None,
                   help="explicitly enable/disable PAUSED status for unresolved Flow requests on this job")

    rv = sub.add_parser(
        "recover-flow-video",
        help="Recover/download an already-generated video from the saved Flow project (submits no generation)")
    rv.add_argument("job_id")
    rv.add_argument("--shot-id", default="", help="unfinished shot to associate; defaults to the first pending shot")
    rv.add_argument("--wait-seconds", type=int, default=120,
                    help="how long to scan the existing project for a downloadable video tile")
    rv.add_argument("--allow-latest", action="store_true",
                    help="allow newest-tile recovery without a saved baseline; use only after visually confirming it belongs to this shot")

    fp = sub.add_parser("flow-project", help="Bind/rebind an AutoVideoAI job to an exact Google Flow project URL")
    fp.add_argument("job_id")
    fp.add_argument("url")

    s = sub.add_parser("status", help="Show job status")
    s.add_argument("job_id")

    support = sub.add_parser("support-report", help="Export redacted pause diagnostics offline (no generation)")
    support.add_argument("job_id")
    support.add_argument("--outputs-root", default="outputs", help="Folder containing saved jobs")
    support.add_argument("--output", help="New .json file; existing files are never overwritten")

    rd = sub.add_parser("render", help="Render accepted takes")
    rd.add_argument("job_id")
    rd.add_argument("--quality", default="high", choices=["preview", "standard", "high"])
    rd.add_argument("--voiceover", dest="voiceover_enabled", action=argparse.BooleanOptionalAction, default=None)
    rd.add_argument("--text-cards", dest="text_cards_enabled", action=argparse.BooleanOptionalAction, default=None)
    rd.add_argument("--text-card-style", choices=["auto", "bold", "playful", "clean"], default=None)
    rd.add_argument("--caption-display", choices=["auto", "full", "none"], default=None)
    rd.add_argument("--background-music", choices=["off", "auto", "local", "browser"], default=None)
    rd.add_argument("--background-music-path", default=None)
    rd.add_argument("--music-volume", type=float, default=None)
    rd.add_argument("--sound-effects", dest="sound_effects_enabled", action=argparse.BooleanOptionalAction, default=None)
    rd.add_argument("--ambience", dest="ambience_enabled", action=argparse.BooleanOptionalAction, default=None)

    au = sub.add_parser("audit", help="Audit shot density, provider fallbacks and observed credit use")
    au.add_argument("job_id")

    a = sub.add_parser("associate", help="Assisted mode: map a downloaded clip to a shot")
    a.add_argument("job_id")
    a.add_argument("shot_id")
    a.add_argument("file")

    sub.add_parser("queue", help="List jobs")
    sub.add_parser("doctor", help="Diagnose Flow browser setup (no browser launched)")
    sub.add_parser("env-doctor", help="Check environment-file discovery and provider variables (values hidden)")
    sub.add_parser("browser-test", help="Launch bundled Chromium with progressive "
                   "flag sets and report what works (takes a few minutes)")
    eb = sub.add_parser("extension-bridge", help="Run localhost bridge for Chrome companion extension")
    eb.add_argument("--host", default="127.0.0.1")
    eb.add_argument("--port", type=int, default=8765)
    ep = sub.add_parser("extension-prompt", help="Queue one prompt to the signed-in Flow Chrome tab")
    ep.add_argument("prompt")
    ep.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"])
    ep.add_argument("--model", default="")
    ep.add_argument("--review", action="store_true", help="insert prompt but do not click Generate")

    mo = sub.add_parser("movieflow-open", help="Open persistent MovieFlow Studio browser for one-time manual login/project setup")
    mo.add_argument("--project-url", default="")

    go = sub.add_parser("gemini-open", help="Open persistent Gemini browser for one-time manual Google login and web-script setup")

    fo = sub.add_parser("flow-open", help="Open a persistent visible Flow browser without any Chrome extension")
    fo.add_argument("--browser", default="bundled", choices=["auto", "bundled", "cdp", "system"])
    fo.add_argument("--cdp-url", default="")

    fi = sub.add_parser("flow-inspect", help="Open Flow and save current UI screenshot/text diagnostics")
    fi.add_argument("--browser", default="bundled", choices=["auto", "bundled", "cdp", "system"])
    fi.add_argument("--cdp-url", default="")

    fd = sub.add_parser("flow-direct", help="Send one prompt directly to Flow via Playwright; no extension/API")
    fd.add_argument("prompt")
    fd.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"])
    fd.add_argument("--model", default="", help="Visible Flow model label. If omitted, uses a credit-safe default instead of premium Quality.")
    fd.add_argument("--duration", type=int, default=None, choices=[4, 6, 8, 10], help="requested clip length in seconds; economy defaults to 10s, otherwise 8s")
    fd.add_argument("--economy", action="store_true", help="credit-saving mode: Gemini Omni Flash 360p + 10s default")
    fd.add_argument("--approval", default="once", choices=["once", "always", "manual"],
                    help="Agent credit confirmation: once=Approve, always=Always approve (persistent), manual=do not click")
    fd.add_argument("--max-generation-credits", type=int, default=None,
                    help="safety cap for one Agent generation; defaults to 10 in --economy, 20 otherwise")
    fd.add_argument("--count", type=int, default=1, choices=[1, 2, 3, 4], help="number of video variations")
    fd.add_argument("--project", default="AutoVideoAI")
    fd.add_argument("--browser", default="bundled", choices=["auto", "bundled", "cdp", "system"])
    fd.add_argument("--cdp-url", default="")
    fd.add_argument("--review", action="store_true", help="fill the prompt but do not click Generate")
    fd.add_argument("--download", default="", help="optional output .mp4 path; waits for generation and downloads")

    cl = sub.add_parser("clip", help="Create Opus-style vertical highlights from a local video or permitted URL")
    cl.add_argument("input", help="local video path or YouTube/video URL")
    cl.add_argument("--output", default="outputs/clips", help="output folder")
    cl.add_argument("--count", type=int, default=3, help="maximum non-overlapping highlights; fewer valid moments return an explicit partial result")
    cl.add_argument("--min-seconds", type=float, default=25)
    cl.add_argument("--max-seconds", type=float, default=55)
    cl.add_argument("--caption-provider", default="auto", choices=["auto", "groq", "local"])
    cl.add_argument("--ranking-provider", default="auto",
                    choices=["auto", "gemini-hybrid", "gemini-api-hybrid",
                             "gemini-web-hybrid", "gemini", "groq", "local"],
                    help="gemini-hybrid tries API, then visible Gemini browser, then Groq/local")
    cl.add_argument("--gemini-model", default="",
                    help="optional Gemini video-analysis model; defaults to GEMINI_CLIP_MODEL/GEMINI_SCRIPT_MODEL")
    cl.add_argument("--gemini-chat-cleanup", default="delete-after-read",
                    choices=["keep", "delete-after-read"],
                    help="cleanup policy for temporary Gemini browser clip-analysis chats")
    cl.add_argument("--source-rights", default="unknown",
                    choices=["unknown", "own_content", "written_permission", "licensed_content",
                             "creative_commons", "public_domain", "commentary_or_review",
                             "private_draft_only"],
                    help="required rights/licence declaration for URL input; stored in highlights.json")
    cl.add_argument("--rights-confirmed", action="store_true",
                    help="legacy compatibility flag; prefer the specific --source-rights declaration")
    cl.add_argument("--background-music", default="",
                    help="optional local licensed music file mixed softly under the source")
    cl.add_argument("--background-music-enabled", action=argparse.BooleanOptionalAction, default=None,
                    help="explicit optional music switch; off ignores any saved music path")
    cl.add_argument("--language", choices=['en','hi','or'],default='en')
    cl.add_argument("--music-license", default="none",
                    choices=["none", "own", "youtube_audio_library",
                             "royalty_free_licensed", "creative_commons"],
                    help="required declaration when --background-music is used")
    cl.add_argument("--music-volume", type=float, default=0.08,
                    help="background music gain from 0.0 to 0.35 (default 0.08)")
    clf = sub.add_parser("clip-config", help="Create highlights from a simple YAML input file")
    clf.add_argument("config", help="path to clip_config.yaml or a copy of it")
    cl.add_argument("--framing", choices=["face-crop", "fit"], default="face-crop",
                    help="fit preserves the complete source frame; face-crop uses a static face estimate")
    for command in ("production-init", "production-check", "production-repair"):
        review = sub.add_parser(command, help="Post-render review and local scene repair")
        review.add_argument("job_id")
        if command == "production-check":
            review.add_argument("--model", default="", help="Optional Gemini vision API model ID")
            review.add_argument("--max-model-calls", type=int, default=0,
                                help="Explicit API call budget; default zero")
        if command == "production-repair":
            review.add_argument("--plan", required=True)
    source_in = sub.add_parser('source-import', help='Import untrusted pasted text/public allowlisted article without generation')
    source_in.add_argument('--url', default='')
    source_in.add_argument('--feed', action='store_true', help='Import up to 10 items from the chosen public RSS URL')
    source_in.add_argument('--text-file', default='')
    source_in.add_argument('--title', default='')
    source_in.add_argument('--output-root', default='data/content/inbox')
    source_in.add_argument('--brief-output', default='', help='new text file for an external writer')
    chars = sub.add_parser('character-create', help='Create an original fictional character identity contract')
    chars.add_argument('--name', required=True); chars.add_argument('--description', required=True)
    chars.add_argument('--reference', action='append', default=[]); chars.add_argument('--original-confirmed', action='store_true')
    chars.add_argument('--library-root', default='data/content/characters')
    rec = sub.add_parser('recreate-clip', help='Create a review-gated AI character recreation plan; submits no generation')
    rec.add_argument('clip'); rec.add_argument('--character-id', required=True)
    rec.add_argument('--library-root', default='data/content/characters'); rec.add_argument('--transcript-file', default='')
    rec.add_argument('--language', choices=['en','hi','or'], default='en')
    rec.add_argument('--source-rights', default='unknown');rec.add_argument('--adaptation-confirmed', action='store_true')
    rec.add_argument('--max-credits', type=int, default=50);rec.add_argument('--background-music', default='')
    approve = sub.add_parser('approve-recreation', help='Approve the exact storyboard/identity/budget; no generation')
    approve.add_argument('job_id')
    tpl = sub.add_parser('longform-template', help='Create a local chapter/evidence template')
    tpl.add_argument('--topic', required=True);tpl.add_argument('--language', default='en');tpl.add_argument('--output',required=True)
    exp = sub.add_parser('export-delivery', help='Encode a local destination export; no publishing')
    exp.add_argument('video');exp.add_argument('--folder',required=True)
    exp.add_argument('--destination', required=True, choices=['instagram_reel','facebook_reel','youtube_short','youtube_long'])
    exp.add_argument('--language', choices=['en','hi','or'], default='en');exp.add_argument('--title',default='')
    exp.add_argument('--framing',choices=['fit','crop'],default='fit')
    metrics=sub.add_parser('metrics-import',help='Import owned-account analytics JSON; does not scrape social sites')
    metrics.add_argument('input');metrics.add_argument('--output',required=True)
    args = ap.parse_args(argv)

    if args.cmd == "support-report":
        from engine.support_report import resolve_job_dir, write_support_report
        try:
            job_dir = resolve_job_dir(args.outputs_root, args.job_id)
            report_path = write_support_report(job_dir, args.output)
        except (ValueError, OSError) as exc:
            raise SystemExit(f"Diagnostic export failed: {exc}") from exc
        print(f"Redacted diagnostic report: {report_path}")
        print("No browser opened and no generation submitted. Review this JSON before sharing; never send .env or browser profiles.")
        return

    f = Factory()
    from engine.runtime_log import timestamp_prefix
    cb = lambda s, p, i="": print(f"{timestamp_prefix()} [{int(p):3d}%] {s} {i}".rstrip())
    if args.cmd == 'source-import':
        from engine.source_inbox import SourceInbox
        inbox = SourceInbox(args.output_root)
        if bool(args.url) == bool(args.text_file):
            ap.error('Choose exactly one --url or --text-file')
        if args.feed:
            if not args.url or args.text_file:
                ap.error('--feed requires --url and no --text-file')
            print(json.dumps(inbox.feed(args.url),indent=2,ensure_ascii=False));return
        item = inbox.fetch(args.url) if args.url else inbox.paste(Path(args.text_file).read_text(encoding='utf-8'),title=args.title)
        if args.brief_output:
            with open(args.brief_output,'x',encoding='utf-8') as output:
                output.write(inbox.brief_prompt(item))
        print(json.dumps(item,indent=2,ensure_ascii=False));return
    elif args.cmd == 'character-create':
        from engine.content_library import CharacterLibrary
        print(json.dumps(CharacterLibrary(args.library_root).create(args.name,args.description,reference_files=args.reference,
                         original_confirmed=args.original_confirmed),indent=2,ensure_ascii=False));return
    elif args.cmd == 'recreate-clip':
        from engine.clip_recreation import create_recreation_job
        text = Path(args.transcript_file).read_text(encoding='utf-8') if args.transcript_file else ''
        print(json.dumps(create_recreation_job(f,args.clip,args.character_id,library_root=args.library_root,
                         transcript_text=text,language=args.language,source_rights=args.source_rights,
                         adaptation_confirmed=args.adaptation_confirmed,max_credits=args.max_credits,
                         background_music=args.background_music),indent=2));return
    elif args.cmd == 'approve-recreation':
        from engine.clip_recreation import approve_recreation
        print(json.dumps(approve_recreation(f,args.job_id),indent=2));return
    elif args.cmd == 'longform-template':
        from engine.content_plan import longform_template
        with open(args.output,'x',encoding='utf-8') as output:
            json.dump(longform_template(args.topic,args.language),output,indent=2,ensure_ascii=False)
        print('Template written; fill and approve it before importing.');return
    elif args.cmd == 'export-delivery':
        from engine.publishing import export_delivery
        print(json.dumps(export_delivery(args.video,args.folder,args.destination,language=args.language,
                         title=args.title,framing=args.framing),indent=2));return
    elif args.cmd == 'metrics-import':
        from engine.publishing import import_metrics
        print(json.dumps(import_metrics(args.output,json.loads(Path(args.input).read_text(encoding='utf-8'))),indent=2));return
    if args.cmd.startswith("production-"):
        from engine.production import init_review, check_job, stage_repairs
        root = f.pm.job_dir(args.job_id)
        if args.cmd == "production-init":
            result = init_review(root)
        elif args.cmd == "production-check":
            result = check_job(root, args.model, args.max_model_calls, cb)
        else:
            result = stage_repairs(root, args.plan)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.cmd == "clip-config":
        import yaml
        from engine.clipping import create_highlight_clips
        with open(args.config, encoding="utf-8") as handle:
            clip_cfg = yaml.safe_load(handle) or {}
        allowed = {
            "source", "output", "count", "min_seconds", "max_seconds",
            "caption_provider", "ranking_provider", "source_rights",
            "background_music", "music_license", "music_volume", "gemini_model",
            "gemini_chat_cleanup", "framing", "language", "background_music_enabled",
        }
        unknown = sorted(set(clip_cfg) - allowed)
        if unknown:
            ap.error("Unknown clip config option(s): " + ", ".join(unknown))
        if not str(clip_cfg.get("source") or "").strip():
            ap.error("clip config requires a non-empty source")
        result = create_highlight_clips(
            str(clip_cfg["source"]), str(clip_cfg.get("output") or "outputs/my-clips"),
            language=clip_cfg.get('language','en'), background_music_enabled=clip_cfg.get('background_music_enabled'),
            count=int(clip_cfg.get("count", 3)),
            min_seconds=float(clip_cfg.get("min_seconds", 25)),
            max_seconds=float(clip_cfg.get("max_seconds", 55)),
            caption_provider=str(clip_cfg.get("caption_provider") or "auto"),
            ranking_provider=str(clip_cfg.get("ranking_provider") or "auto"),
            source_rights=str(clip_cfg.get("source_rights") or "unknown"),
            background_music=str(clip_cfg.get("background_music") or ""),
            music_license=str(clip_cfg.get("music_license") or "none"),
            music_volume=float(clip_cfg.get("music_volume", 0.08)),
            gemini_model=str(clip_cfg.get("gemini_model") or ""),
            framing=str(clip_cfg.get("framing") or "face-crop"),
            gemini_chat_cleanup=str(clip_cfg.get("gemini_chat_cleanup") or "delete-after-read"),
            progress_cb=lambda message, pct, info="": cb(message, pct, info))
        print("Highlights report:", os.path.join(
            str(clip_cfg.get("output") or "outputs/my-clips"), "highlights.json"))
        for path in result["outputs"]:
            print("  ", path)
    elif args.cmd == "clip":
        from engine.clipping import create_highlight_clips
        result = create_highlight_clips(
            args.input, args.output, count=args.count,
            min_seconds=args.min_seconds, max_seconds=args.max_seconds,
            caption_provider=args.caption_provider, rights_confirmed=args.rights_confirmed,
            ranking_provider=args.ranking_provider,
            source_rights=args.source_rights, language=args.language,
            background_music_enabled=args.background_music_enabled,
            background_music=args.background_music,
            music_license=args.music_license,
            music_volume=args.music_volume,
            gemini_model=args.gemini_model,
            framing=args.framing,
            gemini_chat_cleanup=args.gemini_chat_cleanup,
            progress_cb=lambda message, pct, info="": cb(message, pct, info))
        print("Highlights report:", os.path.join(args.output, "highlights.json"))
        for path in result["outputs"]:
            print("  ", path)
    elif args.cmd == "create":
        aspect = "9:16" if args.video_type == "shorts" else "16:9"
        job = f.create_job(args.topic, args.video_type, args.duration, aspect,
                            voice=args.voice, language=args.language, destination=args.destination,
                            approved_plan_path=args.approved_plan_path, narration_input_path=args.narration_input_path,
                            character_id=args.character_id, content_type=args.content_type, tone=args.tone,
                            preset=args.preset, profile=args.profile,
                            cartoon_provider=args.cartoon_provider,
                            movieflow_mode=args.movieflow_mode,
                            movieflow_project_url=args.movieflow_project_url,
                            movieflow_wait_seconds=args.movieflow_wait_seconds,
                            movieflow_recovery_wait_seconds=args.movieflow_recovery_wait_seconds,
                            budgets={"MAX_CREDITS_PER_VIDEO": args.max_credits,
                                     "MAX_RETRIES_PER_SHOT": args.max_retries},
                            dry_run=args.dry_run,
                            tts_provider=args.tts_provider,
                            script_provider=args.script_provider,
                            script_model=args.script_model,
                            script_quality=args.script_quality,
                            tts_model=args.tts_model,
                            tts_voice=args.tts_voice,
                            tts_style=args.tts_style,
                            caption_provider=args.caption_provider,
                            caption_model=args.caption_model,
                            caption_local_model=args.caption_local_model,
                            caption_align_script=args.caption_align_script,
                            max_tts_speedup=args.max_tts_speedup,
                            auto_retime_script=args.auto_retime_script,
                            render_quality=args.render_quality,
                            production_mode=args.production_mode,
                            dynamic_video_scenes=args.dynamic_video_scenes,
                            stock_scenes=args.stock_scenes, stock_source=args.stock_source,
                            caption_display=args.caption_display, background_music=args.background_music,
                            music_mood=args.music_mood, channel_name=args.channel_name, channel_logo=args.channel_logo,
                            graphics_overlays=args.graphics_overlays, watermark=args.watermark,
                            voiceover_enabled=args.voiceover_enabled, text_cards_enabled=args.text_cards_enabled,
                            text_card_style=args.text_card_style, background_music_path=args.background_music_path,
                            music_volume=args.music_volume, sound_effects_enabled=args.sound_effects_enabled,
                            ambience_enabled=args.ambience_enabled,
                            images_per_shot=args.images_per_shot,
                            video_share=args.video_share, stock_share=args.stock_share,
                            flow_scenes=args.flow_scenes, max_flow_scenes=args.max_flow_scenes, frame_source=args.frame_source,
                            flow_approval=args.flow_approval,
                            max_generation_credits=args.max_generation_credits,
                            shot_max_seconds=args.shot_max_seconds,
                            flow_frame_retries=args.flow_frame_retries,
                            network_wait_seconds=args.network_wait_seconds,
                            flow_capacity_wait_seconds=args.flow_capacity_wait_seconds,
                            flow_capacity_retries=args.flow_capacity_retries,
                            flow_project_url=args.flow_project_url,
                            flow_video_retries=args.flow_video_retries,
                            flow_video_ready_grace_seconds=args.flow_video_ready_grace_seconds,
                            flow_video_recovery_wait_seconds=args.flow_video_recovery_wait_seconds,
                            flow_reuse_project_media=args.flow_reuse_project_media,
                            flow_reuse_mode=args.flow_reuse_mode,
                            flow_pause_on_unresolved_request=args.flow_pause_on_unresolved_request)
        print("JOB:", job)
        if args.plan_only:
            print("(plan-only created the job configuration only; run 'v3 resume' to execute script/TTS/media generation)")
            return
        print(f.run_job(job, progress_cb=cb))
    elif args.cmd == "create-config":
        import json
        import yaml
        from engine.studio_config import load_video_config, config_to_factory_kwargs
        cfg = load_video_config(args.config)
        kwargs = config_to_factory_kwargs(cfg)
        job = f.create_job(topic=cfg["topic"], video_type=cfg["video_type"],
                           aspect=cfg["aspect"], **kwargs)
        resolved = os.path.join(f.pm.job_dir(job), "input_config.resolved.yaml")
        with open(resolved, "w", encoding="utf-8") as fh:
            yaml.safe_dump({k: v for k, v in cfg.items() if k not in ("config_source", "production_mode_engine")},
                           fh, sort_keys=False, allow_unicode=True)
        settings_path = os.path.join(f.pm.job_dir(job), "settings.json")
        settings = json.load(open(settings_path, encoding="utf-8"))
        settings.update({"theme": cfg["theme"], "studio_production_mode": cfg["production_mode"],
                         "config_source": cfg["config_source"]})
        with open(settings_path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
        print("JOB:", job)
        print("Resolved configuration:", resolved)
        if args.plan_only or cfg.get("plan_only"):
            print(f"Resume later: python3 cli.py v3 resume {job}")
            return
        print(f.run_job(job, progress_cb=cb))
    elif args.cmd == "themes":
        from engine.studio_config import THEMES
        for name, values in THEMES.items():
            print(f"{name:24s} {values}")
    elif args.cmd == "dashboard":
        import subprocess
        raise SystemExit(subprocess.call([
            sys.executable, "-m", "streamlit", "run", os.path.join(os.path.dirname(__file__), "app.py"),
            "--server.port", str(args.port)]))
    elif args.cmd == "resume":
        if args.gemini_chat_cleanup is not None:
            f.set_gemini_cleanup(args.job_id, args.gemini_chat_cleanup)
        if args.flow_pause_on_unresolved_request is not None:
            f.set_flow_pause_on_unresolved_request(
                args.job_id, args.flow_pause_on_unresolved_request)
        print(f.run_job(args.job_id, progress_cb=cb))
    elif args.cmd == "recover-flow-video":
        print(f.recover_flow_video(args.job_id, shot_id=args.shot_id or None,
                                   wait_seconds=args.wait_seconds,
                                   allow_latest=args.allow_latest))
    elif args.cmd == "gemini-open":
        from engine.providers.gemini_web import GeminiWebBrowser
        b = GeminiWebBrowser()
        try:
            b.ensure_session(visible_login_seconds=600)
            print("Gemini web is ready:", getattr(b._page, "url", "https://gemini.google.com/app"))
            print("Login/profile is persisted. Press Ctrl+C when setup is complete.")
            try:
                while True:
                    import time as _time
                    _time.sleep(60)
            except KeyboardInterrupt:
                pass
        finally:
            b.close()
    elif args.cmd == "movieflow-open":
        from engine.providers.movieflow_browser import MovieFlowBrowser
        b = MovieFlowBrowser()
        try:
            b.ensure_session(visible_login_seconds=600)
            url = b.ensure_project("AutoVideoAI-MovieFlow", project_url=args.project_url or None)
            print("MovieFlow Studio ready:", url or b.current_project_url() or getattr(b._page, "url", ""))
            print("Keep the browser open if using CDP, or press Ctrl+C after login/setup is complete.")
            try:
                while True:
                    import time as _time
                    _time.sleep(60)
            except KeyboardInterrupt:
                pass
        finally:
            b.close()
    elif args.cmd == "flow-project":
        from engine.providers.flow_browser import FlowBrowser
        import json
        url = FlowBrowser.normalize_project_url(args.url)
        if not url:
            raise SystemExit("Invalid Flow project URL. Expected https://flow.google.com/project/<uuid>")
        # Persist in both DB and per-job settings so the binding survives resume
        # even if the DB is later rebuilt from the output folder.
        settings_path = os.path.join(f.pm.job_dir(args.job_id), "settings.json")
        cfg = {}
        if os.path.exists(settings_path):
            with open(settings_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        cfg["flow_project_url"] = url
        with open(settings_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        f.db.upsert(args.job_id, flow_project=url)
        f.pm.log(args.job_id, "flow_project_bound_manual", {"url": url})
        print(f"Bound {args.job_id} -> {url}")
    elif args.cmd == "status":
        from engine.project.manager import ProjectManager
        m = ProjectManager().load_manifest(args.job_id)
        row = f.db.get(args.job_id) or {}
        print(f"{m.job_id}\n  status={m.status} profile={m.profile} shots={len(m.shots)} accepted={m.accepted_count()}"
              + (f"\n  flow_project={row.get('flow_project')}" if row.get("flow_project") else ""))
        for s in m.shots:
            print(f"  {s.shot_id} {s.status} {s.media_strategy} {s.provider}/{s.model} "
                  f"est={s.estimated_credits}cr takes={len(s.takes)} retries={s.retry_count}")
        pause = f.pause_state(args.job_id)
        if pause and (m.status in ("paused", "assisted") or not pause.get("resolved")):
            print("\nPAUSE / RECOVERY GUIDANCE")
            print(f"  stopped_at={pause.get('paused_at', '?')} shot={pause.get('shot_id', '?')}")
            print(f"  reason={pause.get('reason', 'unknown')}")
            if pause.get("flow_project_url"):
                print(f"  flow_project={pause['flow_project_url']}")
            print(f"  completed={pause.get('accepted_shots', 0)}/{pause.get('total_shots', 0)} (saved)")
            for n, action in enumerate(pause.get("actions", []), 1):
                print(f"  {n}. {action.get('label')}:\n     {action.get('command')}")
    elif args.cmd == "audit":
        import json
        m = f.pm.load_manifest(args.job_id)
        ds = [float(x.duration_target or 0) for x in m.shots]
        planned = {}
        actual = {}
        fallbacks = []
        for sh in m.shots:
            planned[sh.media_strategy] = planned.get(sh.media_strategy, 0) + 1
            ap = sh.actual_provider or sh.provider or "unknown"
            actual[ap] = actual.get(ap, 0) + 1
            if sh.fallback_reason:
                fallbacks.append((sh.shot_id, sh.provider, ap, sh.fallback_reason))
        print(f"Job: {m.job_id}")
        print(f"Target: {m.target_seconds}s | shots: {len(m.shots)} | accepted: {m.accepted_count()}")
        if ds:
            print(f"Shot duration: avg={sum(ds)/len(ds):.1f}s max={max(ds):.1f}s")
            if max(ds) > 15:
                print("WARNING: visual shots are too long for normal long-form pacing; create a new v4.1 job or use --shot-max-seconds 8")
        print(f"Planned strategies: {planned}")
        if m.dry_run:
            print("Actual providers: NOT EXECUTED (dry run; provider names in the manifest are only planned routes)")
            print("Observed/recorded credits: 0 (dry run)")
        else:
            print(f"Actual providers: {actual}")
            print(f"Observed/recorded credits: {sum(int(x.credits_spent or 0) for x in m.shots)}")
        frame_sources = {}
        for sh in m.shots:
            for src in (getattr(sh, 'opening_frame_source', ''), getattr(sh, 'closing_frame_source', '')):
                if src:
                    frame_sources[src] = frame_sources.get(src, 0) + 1
        if frame_sources:
            print(f"Frame sources: {frame_sources}")
        print(f"Fallbacks: {len(fallbacks)}")
        for row in fallbacks[:12]:
            print(f"  {row[0]}: {row[1]} -> {row[2]} | {row[3][:140]}")
        gs = os.path.join(f.pm.job_dir(args.job_id), "generation_summary.json")
        if os.path.exists(gs):
            print("Generation summary:", gs)
    elif args.cmd == "render":
        from engine.presentation import PRESENTATION_KEYS
        edits = {key: getattr(args, key) for key in PRESENTATION_KEYS
                 if hasattr(args, key) and getattr(args, key) is not None}
        if edits:
            f.set_presentation_options(args.job_id, **edits)
        print(f.render_job(args.job_id, quality=args.quality, progress_cb=cb))
    elif args.cmd == "associate":
        print(f.associate_download(args.job_id, args.shot_id, args.file))
    elif args.cmd == "queue":
        from engine.project.database import JobDB
        for j in JobDB().list():
            print(f"{j['job_id'][:44]} {j['status']:10s} {j['profile']:16s} +{j['accepted_shots']}/-{j['rejected_shots']} est={j['est_credits']}")
    elif args.cmd == "doctor":
        from engine.providers.flow_browser import doctor_report
        print(doctor_report())
    elif args.cmd == "env-doctor":
        print(format_environment_report(_ENV_REPORT))
    elif args.cmd == "extension-bridge":
        from engine.bridge.server import run
        run(args.host, args.port)
    elif args.cmd == "extension-prompt":
        from engine.providers.flow_extension import FlowExtensionClient
        c = FlowExtensionClient()
        try:
            print("Bridge:", c.health())
        except Exception as e:
            raise SystemExit(f"Bridge is not running: {e}. Start: python3 cli.py v3 extension-bridge")
        tid = c.enqueue_scene(args.prompt, aspect=args.aspect, model_hint=args.model, auto_generate=not args.review)
        print("Queued:", tid)
        print("Keep https://flow.google.com/ open in Chrome with the AutoVideoAI companion extension enabled.")
    elif args.cmd == "flow-open":
        os.environ["FLOW_BROWSER_MODE"] = args.browser
        if args.cdp_url:
            os.environ["FLOW_CDP_URL"] = args.cdp_url
        from engine.providers.flow_browser import FlowBrowser
        b = FlowBrowser()
        try:
            b.ensure_session(visible_login_seconds=600)
            print(f"Flow browser ready: {b.active_browser}")
            print("Log in if needed. This profile is persistent, so the login is reused next time.")
            input("Press ENTER when you are finished with the Flow browser... ")
        finally:
            b.close()
    elif args.cmd == "flow-inspect":
        os.environ["FLOW_BROWSER_MODE"] = args.browser
        if args.cdp_url:
            os.environ["FLOW_CDP_URL"] = args.cdp_url
        from engine.providers.flow_browser import FlowBrowser
        b = FlowBrowser()
        try:
            b.ensure_session(visible_login_seconds=600)
            print(f"Browser: {b.active_browser}")
            path = b.snapshot_failure("flow-inspect", "ui", Exception("manual UI inspection"))
            print("Saved screenshot:", path)
            print("Saved UI text:", path[:-4] + ".json")
            try:
                print("URL:", b._page.url)
                print("TITLE:", b._page.title())
            except Exception:
                pass
            input("Press ENTER when you are finished inspecting Flow... ")
        finally:
            b.close()
    elif args.cmd == "flow-direct":
        os.environ["FLOW_BROWSER_MODE"] = args.browser
        if args.cdp_url:
            os.environ["FLOW_CDP_URL"] = args.cdp_url
        from engine.providers.flow_browser import FlowBrowser, FlowUIChanged
        b = FlowBrowser()
        try:
            b.ensure_session(visible_login_seconds=600)
            print(f"Browser: {b.active_browser}")
            print("[1/5] Entering or creating a Flow project...")
            b.ensure_project(args.project)
            print("[2/5] Detecting the current Flow editor and preparing VIDEO generation...")
            effective_duration = args.duration if args.duration is not None else (10 if args.economy else 8)
            effective_model = args.model or ("Gemini Omni Flash 360p" if args.economy else "Veo 3.1 - Lite")
            credit_cap = args.max_generation_credits if args.max_generation_credits is not None else (10 if args.economy else 20)
            if args.economy:
                print(f"[Flow] ECONOMY mode: {effective_model}, {effective_duration}s, one output; credit guard <= {credit_cap} credits.")
            strategy = b.prepare_text_video(
                aspect=args.aspect, model_label=effective_model, duration=effective_duration, count=args.count
            )
            print(f"[Flow] Editor strategy: {strategy}")
            if strategy == "agent":
                print("[Flow] Flow Agent is active. Video/orientation/model instructions will be sent as natural language; obsolete Text-to-Video tabs are not used.")
            elif strategy == "standard":
                print("[Flow] Migrated standard editor configured through its settings panel.")
            print(f"[3/5] Requested: aspect={args.aspect}, duration={effective_duration}s, count={args.count}, model={effective_model}")
            print("[4/5] Inserting the video instruction/prompt...")
            b.fill_text_video_prompt(
                args.prompt, strategy, aspect=args.aspect, model_label=effective_model,
                duration=effective_duration, count=args.count
            )
            if args.review:
                print("[5/5] Prompt inserted. Review mode is ON; nothing was submitted and no credits should be spent by this command.")
                input("Press ENTER after you finish reviewing in Flow... ")
            else:
                print("[5/5] Submitting to Flow...")
                b.submit_prepared_text_video(strategy)
                print("Prompt submitted.")
                if strategy == "agent":
                    print("[Flow] Waiting briefly for the Agent's credit confirmation, if your account requires one...")
                    clicked = b.confirm_agent_generation(timeout_s=25, approval=args.approval, max_credits=credit_cap)
                    info = getattr(b, "last_agent_confirmation", {}) or {}
                    if clicked:
                        cost = info.get("cost")
                        print(f"[Flow] Agent confirmation clicked: {info.get('clicked') or 'Approve'}" + (f" ({cost} credits shown by Flow)." if cost is not None else "."))
                    elif info.get("blocked"):
                        print(f"[Flow] Generation NOT approved: {info.get('reason', 'blocked by safety policy')}. The browser is left open for review.")
                    else:
                        print(f"[Flow] Confirmation was not clicked: {info.get('reason', 'none detected')}. Generation may already be running if Flow did not require approval.")
                if args.download:
                    if strategy == "agent":
                        print("Warning: automatic download from the expanded Agent UI is not reliable yet. The video will remain saved in the Flow project; --download is skipped in Agent mode in v3.6.")
                    else:
                        ok = b.wait_for_generation()
                        if not ok:
                            raise SystemExit("Flow did not report completion before timeout or reported a generation failure.")
                        out = b.download_generation(0, args.download)
                        print("Downloaded:", out)
                else:
                    info = getattr(b, "last_agent_confirmation", {}) or {}
                    if strategy == "agent" and info.get("blocked"):
                        input("Generation is paused at Flow confirmation. Review it in the browser, then press ENTER to close this session... ")
                    else:
                        input("Generation started (or Flow is processing the request). Press ENTER when you are finished with this Flow session... ")
        except FlowUIChanged as e:
            snap = b.snapshot_failure(args.project, "flow-direct", e)
            print(f"Flow UI changed or a control was not found: {e}")
            print(f"Diagnostic screenshot: {snap}")
            print(f"Diagnostic UI dump: {snap[:-4]}.json")
            raise
        finally:
            b.close()
    elif args.cmd == "browser-test":
        from engine.providers.flow_browser import browser_self_test
        print("Probing bundled Chromium (up to ~4 min, watch for windows popping up)...")
        r = browser_self_test()
        for i, v in enumerate(r.get("variants", []), 1):
            mark = "PASS" if v["ok"] else "FAIL"
            print(f"[{mark}] {i}. {v['name']}\n     {v['detail']}"
                  + (f"  (shot: {v['screenshot']})" if v.get("screenshot") else ""))
        print("\nVERDICT:", r.get("verdict", "?"))




from engine.automation import (create_video_from_topic, bulk_create_from_csv,
                               fetch_trending_topics, prepare_flow_shots)


def main():
    ap = argparse.ArgumentParser(description="Auto Video AI - free CLI")
    ap.add_argument("--topic", help="Video topic")
    ap.add_argument("--type", dest="video_type", default="shorts",
                    choices=["shorts", "faceless_youtube", "explainer", "marketing"])
    ap.add_argument("--duration", type=int, default=45)
    ap.add_argument("--voice", default="en-IN-NeerjaNeural")
    ap.add_argument("--tone", default="exciting")
    ap.add_argument("--watermark", default="")
    ap.add_argument("--visual-mode", default="auto",
                    choices=["auto", "flow", "stock", "ai", "kenburns"])
    ap.add_argument("--ai-provider", default="veo",
                    choices=["veo", "seedance", "fal", "comfy"])
    ap.add_argument("--caption-style", default="wordpop", choices=["wordpop", "classic"])
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--bulk", help="Path to topics CSV for bulk mode")
    ap.add_argument("--shot-list", help="Only prepare script + Flow shot list for TOPIC (no video)")
    ap.add_argument("--trending", type=int, default=0, help="Auto-create N videos from trending topics")
    ap.add_argument("--outdir", default="outputs")
    args = ap.parse_args()

    def cb(stage, pct):
        print(f"[{pct:3d}%] {stage}")

    if args.shot_list:
        r = prepare_flow_shots(args.shot_list, args.video_type, args.duration, args.tone, args.outdir)
        print(f"\n📋 {len(r['shots'])} shots ready: {r['shot_list_md']}")
        print("Next: paste prompts into Flow → save clips to assets/flow_clips/ → rerun with --visual-mode flow")
        return

    if args.bulk:
        print(f"📦 Bulk mode: {args.bulk} (visual={args.visual_mode})")
        results = bulk_create_from_csv(args.bulk, args.outdir, cb, args.visual_mode, args.ai_provider)
        for r in results:
            print(("✅ " + r["video"]) if "video" in r else f"❌ {r}")
        return

    if args.trending:
        topics = fetch_trending_topics(args.trending)
        print(f"🔥 Trending: {topics}")
        for t in topics:
            r = create_video_from_topic(t, args.video_type, args.duration, args.voice,
                                        args.tone, args.watermark, args.outdir,
                                        args.visual_mode, args.ai_provider,
                                        args.caption_style, not args.no_music, progress_cb=cb)
            print("✅", r["video"], f"[{r['visual_used']}]")
        return

    if not args.topic:
        ap.error("Provide --topic, --bulk, --shot-list, or --trending")
    r = create_video_from_topic(args.topic, args.video_type, args.duration, args.voice,
                                args.tone, args.watermark, args.outdir,
                                args.visual_mode, args.ai_provider,
                                args.caption_style, not args.no_music, progress_cb=cb)
    print("\n🎉 VIDEO READY:", r["video"])
    print(f"Title: {r['title']} | {r['duration']:.0f}s | {r['size']} | visuals: {r['visual_used']} | AI cost: ${r['cost_usd']:.2f}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "v3":
        from engine.routing.provider_router import NeedsDecision
        try:
            main_v3(sys.argv[2:])
        except NeedsDecision as exc:
            print(f"PAUSED: {exc}")
            for action in exc.alternatives:
                print(f"Next action: {action}")
            raise SystemExit(2)
    else:
        main()

# AutoVideoAI v6.0.18 — precise Flow gallery video matching

This repository includes **editable application source**. Run commands from the folder containing `cli.py` and `app.py`. Older release archives are preserved as reference builds.

**New in v6.0.18:** [Precise Flow gallery video matching](V6_0_18_FLOW_GALLERY_VIDEO_MATCHING.md). A live recovery diagnostic returned 17 video candidates: generic “video” text promoted 15 ordinary stills, and a sidebar preview was promoted by its play icon. The classifier now requires stronger tile evidence, so the fresh clip can be matched without guessing by order.

**Previous in v6.0.17:** [Flow gallery tile recovery](V6_0_17_FLOW_GALLERY_CLASSIFICATION.md). Queue-status text in Flow's chat no longer demotes a separate generated gallery video tile; queue text is scoped to the tile's card, with exact fresh-asset matching retained.

**Previous in v6.0.16:** [Flow video tile recovery](V6_0_16_FLOW_VIDEO_TILE_RECOVERY.md). A fresh typed video tile is not blocked by stale page-wide status text; AutoVideo attempts the exact asset sooner, validates the downloaded video, and reports recovery causes without silently submitting a duplicate. Includes Storyboard Economy workers and prompt-only/frame-guided Flow input.

**Previous in v6.0.15:** [Flow queue recovery and Storyboard Economy workers](V6_0_15_FLOW_QUEUE_STORYBOARD_WORKERS.md). Scheduled queue thumbnails remain pending; bounded waits and exact-request Resume avoid duplicate video generation. Storyboard Economy parallelizes independent Flow stills without breaking continuity-linked frames.

**Previous in v6.0.14:** [Clip workflow and Gemini Web repairs](V6_0_14_CLIP_WORKFLOW_REPAIRS.md). Fit preserves landscape/portrait orientation; enabled B-roll search prepares reviewable previews automatically; Pixabay music lookup validates actual downloads; Streamlit's width deprecation is removed; and Gemini Web detection targets the current Quill composer without exposing page text.

**Previous in v6.0.13:** [Workspace navigation and UI audit](V6_0_13_UI_NAVIGATION.md). Groups the 18 dashboard pages into five workspaces, clarifies Guided Studio versus Advanced Create, and includes an independent feature-coverage and production-readiness review.

**Previous in v6.0.12:** [Safe RSS parsing and Indic font cache repair](V6_0_12_XML_INDIC_CACHE.md). DTD/entity declarations are now blocked even when feed XML uses UTF-16, and the Indic font fallback keeps its render cache per font instance so completed jobs can release FreeType/HarfBuzz resources. Includes the v6.0.11 CLI JSON repair.

**Previous in v6.0.11:** [CLI JSON output repair](V6_0_11_CLI_JSON_REPAIR.md). Fixes Python's local-import scoping error that made several v3 JSON-producing commands fail, adds offline regression coverage, and makes Mini Reels feed User-Agent version labels follow `VERSION` automatically.

**Previous in v6.0.10:** [Mini Reels website ideas and Google Trends RSS repair](V6_0_10_MINI_REEL_ARTICLE_IDEAS.md). Pick a manual idea, current Google Trends topic, or recent article from TechniVella, The Fact Site, Interesting Facts, or ScienceDaily. Article titles/excerpts seed the visible Gemini Web prompt as unverified inspiration; the Flow prompt remains editable and generation still requires explicit approval. Google Trends now uses its current `/trending/rss?geo=…` feed route.

**Previous in v6.0.9:** [Flow video type and recovery repair](V6_0_9_FLOW_VIDEO_RECOVERY.md). Select the visible Image/Video mode before Agent generation, never accept a fresh still as a completed video, repair wrong-kind pending signatures through unique post-baseline video matching, and recover image downloads when a Flow viewer closes during `save_as`—without blind video resubmission or weakening media validation.

**Previous in v6.0.8:** [Clip caption timing repair](V6_0_8_CLIP_CAPTION_TIMING.md). Source-derived clip generation now normalizes occasional out-of-order/invalid ASR word times before caption rendering; the shared caption renderer remains strict for other workflows.

**Previous in v6.0.7:** [Review-first stock B-roll cutaways](V6_0_7_REVIEW_FIRST_BROLL.md). Find related stock footage at production scene boundaries or within CLIP STUDIO highlights, preview each exact file, adjust placement/length, and approve its rights before rendering. Cutaways replace picture only: existing audio and duration remain unchanged, originals are preserved, and no Flow/Veo generation is submitted.

**Previous in v6.0.6:** [Flow resume safety](V6_0_6_FLOW_RESUME_SAFETY.md). Reuse existing Flow tabs in CDP sessions, preserve the saved project route, avoid opening duplicate tabs while a project is still loading, and show video-vs-image-specific recovery guidance with the provider's failure reason. Coverage-QC failures now show read-only shot statuses in the dashboard.

**New in v6.0.5:** [Mini Reels workflow](V6_0_5_MINI_REELS.md). Discover current Google Trends search ideas, ask the visible Gemini Web session for an original short-form prompt, then review and generate one vertical Flow/Veo clip in-browser. Native Flow voiceover/ambience is optional and best-effort; no separate TTS is run, and uncertain video requests are recovered without blind re-submission.

**Previous in v6.0.4:** [long-form voiceover resilience](V6_0_4_LONGFORM_VOICEOVER_ROBUSTNESS.md). Adds duration headroom and deterministic caption-timing fallback for robust long-form production.

**New in v6.0.0:** [Content Studio testing guide](V6_0_0_CONTENT_STUDIO.md).
English/Hindi/Odia configuration and shaped text, source/approved-script imports,
original characters, review-gated AI clip recreation, optional speech-preserving
clip music, and destination exports/manual release review. This is the first
implementation stage; social OAuth publishing and automatic research/localization
remain planned, not silently enabled.

**New in v5.8.6:** [music-only reels and readable text cards](V5_8_6_MUSIC_ONLY_TEXT_CARDS.md).
Independent voiceover/text-card switches, actual no-TTS music-only and silent
rendering, large pixel-measured display typography, bundled licensed fonts,
phone-safe transparent layouts and render-only edits of saved accepted footage.
Choose **Music only** + **Include text cards off** for a clean cartoon reel.

**Full ZIP / paused-job upgrade:** [v5.8.5 quality and pause diagnostics](V5_8_5_QUALITY_PAUSE_DIAGNOSTICS.md).
Includes explicit pause/download logs, an offline redacted support report, safe
upgrade guidance and a source-only ZIP builder. The supplied log did not include
the final pause reason; this build does not claim to resolve that unidentified
live Flow issue or disable exact matching / duplicate-credit protection.

**New quality improvements:** [audio mixing and caption quality](VIDEO_QUALITY.md).
Fixes background-audio render failures, preserves narration gain and stereo
music, and improves caption wrapping, timing, safe zones, and duration limits.
Includes offline regression tests and a GitHub Actions test workflow. This remains
a production-review testing build, not an unattended publishing guarantee.

Settings hotfix: [v5.8.4 effective cleanup policy](V5_8_4_SETTINGS.md). Corrects saved cleanup and image-worker settings being ignored during execution. Flow asset-not-visible recovery remains under investigation.

Latest hotfix: [v5.8.3 download callback and script-length recovery](V5_8_3_DOWNLOAD_CALLBACK.md). Fixes the Playwright callback failure shown in the pause screenshot and removes manual MP4 recovery suggestions.

Current cleanup update: [v5.8.2 policy and resume instructions](V5_8_2_GEMINI_POLICY.md). New Studio/YAML jobs enable cleanup; existing jobs can use `resume JOB-ID --gemini-chat-cleanup delete-after-read`.

Previous hotfix: [v5.8.1 resume and reels notes](V5_8_1_RESUME_REELS.md). Restores cropped reels, removes the incorrect manual-download panel and fixes duplicate Resume controls. See section 18.

AutoVideoAI turns a topic into a resumable YouTube video or vertical reel: script, narration, storyboard, Google Flow/free/stock visuals, captions, editorial graphics, audio mix, QC, and final FFmpeg render.

v5.8.0 includes the v5.7.10 Flow/Gemini/repetition fixes, adds full-frame clip framing, optional sampled Gemini vision review, rights/fact evidence records, local scene replacement, and timed list/comparison/chart overlays. Full-video rendering uses timestamp-normalized hard cuts. Technical QC is **not** editorial approval. This is a testing release, not a promise of unattended publication or viral performance. The complete production roadmap is not implemented; section 17 states the boundaries explicitly.

Read the [v5.8.0 release notes](V5_8_0_PRODUCTION_REVIEW.md) and section 15 before upgrading. Existing manifests and Flow URLs remain compatible; a badly timed old job may stop at coverage QC rather than render a repetitive video. Do not delete old outputs or regenerate paid scenes just to clear this check.

## 1. Install

Requirements: Python 3.10+, FFmpeg/FFprobe, and Chrome/Chromium for browser providers. WSL2 is supported.

```bash
cd AutoVideo                            # Git checkout
# ZIP download: cd AutoVideoAI-v6.0.18
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m playwright install chromium    # only for bundled browser mode
cp .env.example .env
```

Add only the API keys you use to `.env`. Google Flow and `gemini-web` use your visible signed-in browser session; the tool never asks for or stores your Google password.

```bash
python3 cli.py v3 env-doctor      # keys shown only as OK/MISSING
python3 cli.py v3 doctor
python3 cli.py v3 flow-open       # first Flow login
python3 cli.py v3 gemini-open     # first Gemini-web login
```

Use ordinary KEY=value lines without Markdown fences:

```dotenv
GEMINI_API_KEY=your_google_ai_studio_key
GROQ_API_KEY=your_groq_key
ELEVENLABS_API_KEY=your_elevenlabs_key
```

`GOOGLE_API_KEY` is accepted as an alias for `GEMINI_API_KEY`. v5.7.5
searches the installation folder, `.env.local`, the parent Auto folder, the
shared user configuration, and recent AutoVideoAI version folders. The first
non-empty value wins.

On WSL, the most reliable way to reuse signed-in Windows Chrome is `chrome-debug.bat`, then CDP mode as explained in `FLOW_SETUP.md`.

## 2. Studio dashboard

```bash
./dashboard.sh
# Windows: dashboard.bat
# or: python3 cli.py v3 dashboard
```

Open <http://localhost:8501>. The sidebar is organized into five workspaces: **Create**, **Review & Render**, **Jobs & Recovery**, **Content & Delivery**, and **Setup & Legacy**. **Guided Studio** is the recommended starting point; **Advanced Create** exposes provider, scene, retry, and credit-budget controls. The older Quick v2 path is under Setup & Legacy.

**Guided Studio** provides controls for production mode, theme, script/TTS providers, Flow workers, frame source, project reuse, Gemini cleanup, music, captions, branding, credits, and render quality.

Select **Mini Reels** for the separate 8-second vertical workflow: optional Google Trends/article ideas → visible Gemini Web prompt → reviewed Flow/Veo generation. The page can request Flow-native voiceover/ambience but does not run separate TTS; see [v6.0.5 notes](V6_0_5_MINI_REELS.md) for account, audio, credit, and recovery limitations.

The dashboard and CLI use the same engine. The dashboard refreshes the log while Flow is waiting; it no longer updates only when a pipeline stage finishes. Progress is shown on screen and written to:

```text
outputs/<JOB-ID>/logs/runtime.log
outputs/<JOB-ID>/logs/progress.json
```

Every runtime line includes local wall-clock time, timezone, and elapsed job time, for example:

```text
[2026-09-27T10:31:04+05:30] [+00:18:42] [Flow] Agent is at capacity; waiting 60s; next attempt at 10:32:04...
```

During FFmpeg encoding, percentage is computed from encoded timeline time instead of showing a frozen spinner.

## 3. Simple YAML workflow

```bash
cp video_config.yaml my_video.yaml
# Edit the topic and uncomment only what you need.
python3 cli.py v3 create-config my_video.yaml
```

Create without starting generation:

```bash
python3 cli.py v3 create-config my_video.yaml --plan-only
```

Every YAML job saves its effective input as `outputs/<JOB-ID>/input_config.resolved.yaml`. Unknown options and invalid values fail before job creation, preventing silent typos.

## 4. Resume, recover, and reuse the same Google Flow project

Resume never starts a new job:

```bash
python3 cli.py v3 resume <JOB-ID>
```

Completed script, narration, images, and clips are reused. The exact Flow URL is stored in job settings and the database as soon as the first image project opens, so later image workers, video generation, download recovery, and resume all target one project.

```yaml
flow_project_url: "https://flow.google.com/project/<uuid>"
flow_reuse_project_media: true
flow_reuse_mode: exact
```

Bind or change it later:

```bash
python3 cli.py v3 flow-project <JOB-ID> "https://flow.google.com/project/<uuid>"
python3 cli.py v3 status <JOB-ID>
python3 cli.py v3 resume <JOB-ID>
```

Reuse modes:

- `exact`: prompt fingerprint + project + aspect must match; safest.
- `topic`: broader reuse from the same project/topic.
- `project`: broadest and fastest; review older visuals carefully.

Interrupted Flow work keeps completed assets. Fix login/network/UI problems and resume the same job.

### If Flow created the video but AutoVideoAI did not download it

Do **not** create a new job and do **not** click Generate again. First run recovery-only mode:

```bash
python3 cli.py v3 status <JOB-ID>
python3 cli.py v3 recover-flow-video <JOB-ID> --shot-id shot_005 --wait-seconds 120
python3 cli.py v3 resume <JOB-ID>
```

`recover-flow-video` opens the saved project and scans existing playable video tiles. It never fills/submits a prompt, so it requests zero new generation credits. For v5.7.1+ pauses, it uses the saved pre-generation media baseline and will only download a tile proven newer than the stopped shot. v5.7.2 opens that tile's **⋮ → Download → 720p/360p** menu while staying on the stable project page; it no longer enters the media viewer that was closing during `Download.save_as`. It then validates the file as time-based media, runs QC, and associates it.

After upgrading the failed job shown in the issue report, use recovery—not repeated `resume`—first:

```bash
python3 cli.py v3 recover-flow-video 20260927-083456-winners-habit-9fb7 \
  --shot-id shot_005 --wait-seconds 180
python3 cli.py v3 resume 20260927-083456-winners-habit-9fb7
```

An older pause created before v5.7.1 has no baseline. Automatic recovery then refuses to guess, because the newest tile might belong to the previous accepted shot. Wait for Flow to reset and resume the same job, or manually associate a visually confirmed MP4. Advanced users can add `--allow-latest` only after confirming the newest tile is the stopped shot.

If automatic recovery cannot identify the right tile, download the correct MP4 yourself and associate it:

```bash
python3 cli.py v3 associate <JOB-ID> <SHOT-ID> /path/to/downloaded-video.mp4
python3 cli.py v3 resume <JOB-ID>
```

`status` prints the stop time, exact reason, saved Flow URL, completed-shot count, and recovery commands whenever a job is paused.

### First-project credit approval

The default is deliberately safe:

```yaml
flow_approval: once
max_generation_credits: 10
```

AutoVideoAI keeps looking for a delayed `Approve`/`Approve once` card while generation is pending. It will not select `Always approve` unless you explicitly set `flow_approval: always`. The per-generation credit cap is still enforced.

## 5. Modes and themes

- `youtube_pro`: 16:9 long-form defaults, mixed Flow/stock motion, editorial overlays, publish-quality master.
- `reels_pro`: 9:16 Shorts/Reels defaults, full captions and overlays, using the proven voiceover/audio master pipeline.
- `legacy`: older behavior.

```bash
python3 cli.py v3 themes
```

Themes: `kids_cartoon`, `devotional_cartoon`, `devotional_real`, `motivational`, `cooking`, `health`, `personal_finance`, `personality_development`, `cartoon_story`. Themes provide content, tone, preset, and music defaults; explicit YAML values win.

For `youtube_pro`, automatic routing now targets the whole shot plan as:

- 60% meaningful royalty-free/local stock video
- 20% Google Flow motion for hero/action beats, subject to the credit cap
- 20% generated stills with local cinematic motion

If no configured local/API/browser stock source is available, those slots safely fall back to image motion rather than blocking the job.

Reel example:

```yaml
topic: "Discipline beats motivation"
production_mode: reels_pro
theme: motivational
duration: 45
profile: STORYBOARD_ECONOMY
caption_display: full
```

## 6. Parallel Flow candidate images

```yaml
images_per_shot: 2
flow_image_workers: 3
```

Workers use separate persistent profiles and never share one Playwright context. Before workers start, AutoVideoAI creates/opens one canonical project and gives that exact URL to every worker. Results merge on the main thread; one failure does not discard successful files. Start with `1`, test `2`, then `3` because Google may throttle concurrency.

Parallel workers apply to independent candidate-image generation. Continuity-dependent Storyboard Economy opening/closing pairs remain ordered so adjacent-scene continuity and first/last-frame guidance are not corrupted.

## 7. Gemini temporary-chat cleanup

```yaml
script_provider: gemini-web
gemini_chat_cleanup: delete-after-read
```

The answer is captured locally first. The tool then attempts the visible current-chat menu → Delete → confirmation flow. If Gemini’s UI is ambiguous, cleanup is skipped and the chat is kept; the tool never guesses which conversation to delete. Use `keep` while diagnosing.

## 8. Gemini-hybrid important clips from a long video

Local file:

```bash
python3 cli.py v3 clip "/path/to/my-long-video.mp4" \
  --output outputs/my-clips --count 3 --min-seconds 25 --max-seconds 55
```

Public YouTube URL with an explicit rights declaration:

```bash
python3 cli.py v3 clip "https://www.youtube.com/watch?v=..." \
  --source-rights own_content \
  --output outputs/my-clips --count 3 \
  --caption-provider groq --ranking-provider gemini-hybrid
```

The easiest reusable input is:

```bash
cp clip_config.yaml my_clip.yaml
python3 cli.py v3 clip-config my_clip.yaml
```

The dashboard also has **CLIP STUDIO**, with the same Gemini/local selection, source-rights confirmation, duration and optional-music controls. When B-roll is enabled, creating highlights automatically searches for up to the selected maximum (at most one candidate per highlight). Preview each exact suggestion and explicitly approve or skip every one, save decisions, then apply approved cutaways as separate copies; original highlights/audio remain unchanged. v6.0.7 added the review-first cutaway workflow for production renders and individual Clip Studio highlights; see [the cutaway guide](V6_0_7_REVIEW_FIRST_BROLL.md).

For a public YouTube URL, `--ranking-provider gemini-hybrid` now follows this visible chain:

```text
Gemini API (up to 4 attempts for 429/503/5xx)
  → signed-in Gemini browser
  → Groq/local editorial fallback
```

The browser is not expected to open when the API succeeds. It opens only after the API retry window is exhausted, or immediately with `--ranking-provider gemini-web-hybrid`. Use `gemini-api-hybrid` to prohibit browser fallback. `auto` stays non-intrusive unless `AUTOVIDEO_CLIP_BROWSER_FALLBACK=1` is set.

Clip API calls now require an explicitly configured model (`--gemini-model`, `GEMINI_CLIP_MODEL`, or `GEMINI_SCRIPT_MODEL`); the clipper no longer invents a model-version default. List IDs available to your key with `python3 -m engine.providers.gemini_models`, then confirm the chosen model supports video input. Listing does not guarantee quota or availability. If no model is configured, hybrid mode immediately reports that reason and proceeds to its browser fallback. Existing `.env` model values are preserved; remove/update an unavailable value or use browser-only ranking. Provider 503 outages themselves cannot be fixed by a client build.

Gemini proposes multiple timestamped hooks using both audio and visuals. AutoVideoAI then snaps every proposal to complete local sentence boundaries, rejects invalid/context-dependent ranges, combines Gemini and deterministic editorial scores, removes overlaps, and renders the top results. Every failed provider transition is printed and recorded in `highlights.json`; it is never a silent fallback.

Temporary browser-analysis chats default to `delete-after-read`. Override with `--gemini-chat-cleanup keep` when diagnosing Gemini UI behavior.

Downloads prefer H.264/AVC instead of AV1 for WSL compatibility. Five-minute mono audio chunks reduce Groq upload size. FFmpeg burns active-word captions without an opaque card. `--framing fit` preserves the entire source picture and its display aspect/orientation: landscape stays landscape, portrait stays portrait, and the long edge is capped at 1920 pixels. It does not crop the source or force every clip into a vertical canvas. The default `--framing face-crop` still makes a filled 1080×1920 reel using one median face position per clip; it is not active-speaker tracking and can miss people after camera cuts. Use the original uncropped video as input.

Optional quiet background music has no separate music-acknowledgement gate. Keep it off by default, or explicitly turn it on to search Pixabay for a soft instrumental bed. The exact source page, licence label and file SHA-256 are retained in `highlights.json`; review the item page and current terms rather than treating a provider label as automatic clearance. YouTube Audio Library remains a YouTube Studio/manual-download workflow; some tracks require attribution. Download those tracks yourself and record the source/credit in CLIP STUDIO or with `--music-source-url`.

```bash
python3 cli.py v3 clip "my-video.mp4" --source-rights own_content \
  --background-music-enabled --background-music-source pixabay \
  --music-mood "soft ambient instrumental" --music-volume 0.08
```

A local track needs no music-specific declaration:

```bash
python3 cli.py v3 clip "my-video.mp4" --source-rights own_content \
  --background-music "assets/music/my-track.mp3" \
  --music-source-url "https://example.com/track-page" --music-volume 0.08
```

The source-video rights confirmation remains separate and unchanged.

Accepted source declarations are `own_content`, `written_permission`, `licensed_content`, `creative_commons`, `public_domain`, `commentary_or_review`, and `private_draft_only`. The declaration and warnings are saved in the report. `--rights-confirmed` remains available only for compatibility with older commands.

**Copyright warning:** captions, crop, background music, zoom or generated motion alone do not make copied footage copyright-safe. The tool records your declaration but does not grant or independently verify rights. `commentary_or_review` and `private_draft_only` are deliberately marked as not cleared for public upload by the declaration alone. Review every clip before publishing.

Outputs:

```text
outputs/my-clips/
├── unlock-your-future-3-mindset-shifts.mp4
├── unlock-your-future-3-mindset-shifts.qc.json
├── train-your-brain-before-sleep.mp4
├── train-your-brain-before-sleep.qc.json
└── highlights.json       # timestamps, scores, reasons and output paths
```

Each `.qc.json` checks that the result has video and audio streams, the selected framing dimensions (1080×1920 for face-crop or the source-matched size for fit), expected duration, clean decoding, acceptable black/frozen intervals, and captions. A broken decode, missing stream, severe black interval, or stuck picture is `BLOCK` and is not marked upload-ready. A size mismatch or caption issue is `REVIEW`; healthy output is `PASS`. The 0–100 score combines the editorial candidate score with technical readiness.

OpusClip uses a proprietary model, so identical rankings or viral predictions are not promised. AutoVideoAI's score is an explainable editorial/technical readiness score, not a guarantee that a clip will become viral.

## 9. Transparent text and blank-render protection

Editorial intro/chapter/key-point/recap/outro graphics are transparent overlays on the footage. The outro no longer paints a full black frame. Word-pop captions use white outlined text, a highlighted active word, and only a subtle translucent lower-third when the fallback renderer needs one.

Before encoding, coverage QC blocks oversized short-source extensions and excessive identical-footage reuse. The full-video renderer starts with normalized hard-cut concat, then measures near-black intervals, frozen-picture duration and video-stream coverage. Invalid output stops with a QC error. Older direct renderer integrations retain a bounded recovery path. Technical QC does not prove that footage illustrates the narration correctly.

For people-focused vertical clips, the clipper detects the median face position and reframes around it, while captions stay in a lower safe zone. This prevents ordinary text-over-head failures. A genuine “text behind the moving head” depth effect requires per-frame person segmentation and is intentionally not faked by a static mask in this release.

## 10. Local editors and zero-credit rendering

AutoVideoAI uses FFmpeg/OpenCV/Pillow for repeatable, scriptable local editing: cuts, crops, overlays, captions, audio mixing, QC and export require no AI-video credits. This is the recommended automation engine.

- **Kdenlive** is a strong free GUI finishing option and can render generated MLT scripts from a terminal.
- **Shotcut/MLT** is also free and supports MLT XML plus command-line `melt` rendering.
- **CapCut Desktop** is useful for optional manual polish and provides Auto Reframe, Auto Captions and Auto Cut, but AutoVideoAI does not automate private CapCut UI controls. CapCut features and licenses can change, and Pro is not a free dependency.

The final MP4, SRT and ASS files can be imported into any of these editors.

## 11. Full CLI remains available

```bash
python3 cli.py v3 create \
  --topic "How AI agents will change work" \
  --type faceless_youtube \
  --duration 300 \
  --production-mode youtube_pro \
  --profile STORYBOARD_ECONOMY \
  --flow-project-url "https://flow.google.com/project/<uuid>" \
  --render-quality high
```

```bash
python3 cli.py v3 queue
python3 cli.py v3 status <JOB-ID>
python3 cli.py v3 recover-flow-video <JOB-ID> --wait-seconds 120
python3 cli.py v3 audit <JOB-ID>
python3 cli.py v3 render <JOB-ID> --quality high
python3 cli.py v3 flow-inspect
```

## 12. Output layout

```text
outputs/<JOB-ID>/
├── input_config.resolved.yaml
├── settings.json
├── production_manifest.json
├── pause_state.json                 # present after an actionable pause
├── script.json
├── narration/
├── storyboard/
├── flow/shots/
├── captions/
├── audio/
├── qc/
├── render/<JOB-ID>-final.mp4
└── logs/
    ├── runtime.log
    └── progress.json
```

`runtime.log` is append-only across resumes. `progress.json` is the latest event for dashboards or monitoring. `pause_state.json` records the stopped shot, timestamp, Flow URL, reason, protected completed work, and exact next commands.

## 13. Troubleshooting

**Flow asks for login:** run `python3 cli.py v3 flow-open`, sign in manually, then resume.

**WSL cannot drive Windows Chrome.exe:** use `chrome-debug.bat`/CDP or bundled Playwright Chromium. Never point Linux Playwright directly at `/mnt/c/.../chrome.exe`.

**Flow says “usage limit” although credits remain:** this is an account/rate limit, not necessarily a zero credit balance. v5.7.1 stops immediately instead of spending about 14 minutes on capacity retries. Existing project media remains safe. Try recovery-only mode first, then wait for access to reset and resume.

**Flow is temporarily at high demand:** the log prints the wait start, elapsed time, and next retry clock time. Retries are bounded. When exhausted, the job pauses with exact recovery/resume actions.

**Flow created a video but download failed:** run `recover-flow-video` instead of repeatedly running `resume`; it compares against the saved pre-generation baseline and downloads from the matched project tile's three-dot menu. Older pauses without a baseline require visual confirmation/manual association rather than a risky guess.

**Final video has black/blank sections:** v5.7.2 refuses a render with 20% near-black/missing picture and automatically retries the safe renderer. Existing broken MP4s are not modified in place; rerun `python3 cli.py v3 render <JOB-ID> --quality high` after upgrading.

**Clip transcription returned Groq HTTP 413:** upgrade to v5.7.3. The clipper now sends compact five-minute audio chunks rather than the complete video file.

**AV1 / Missing Sequence Header messages while clipping YouTube:** upgrade to v5.7.4. URL downloads now prefer H.264 and face analysis uses FFmpeg software-decoded frames instead of OpenCV's unavailable WSL hardware path.

**A long final video freezes for minutes:** upgrade to v5.7.4 and rerender. Narration alignment now must cover the measured audio duration, and final motion QC rejects a render when frozen time exceeds the safety threshold.

**Stock footage is unrelated to a professional topic:** v5.7.4 adds domain-anchored searches (for example, communication advice stays in office/meeting/speaker footage) and explicit negative context in generated-video prompts.

**`yt-dlp` was installed but AutoVideoAI says it is missing:** upgrade to v5.7.3. It now falls back to the current interpreter's `python3 -m yt_dlp` entry point, so `~/.local/bin` does not need to be on PATH.

**Browser closes:** AutoVideoAI reopens the saved canonical project. Strict Flow mode pauses before a fresh generation can spend more credits.

**First generation waits for approval:** leave the visible Flow window open. The tool detects a late one-time approval card. With `flow_approval: once`, it clicks only Approve/Approve once; use `always` only if you intentionally want persistent approval.

**Parallel workers are throttled:** set `flow_image_workers: 1`; completed images remain valid.

**Render is slow:** watch encoded-time percentage. Use `preview` for review and `high` for publishing. Hardware encoding safely falls back to `libx264`.

**Low disk:** the engine stops before unsafe writes. Archive finished videos before deleting old outputs.

**Audit a run:** inspect `input_config.resolved.yaml`, `settings.json`, `generation_log.json`, `generation_summary.json`, and `logs/runtime.log`.

## 14. Tests

```bash
python3 -m pytest -q
```

The suite covers planning, Flow project binding/reuse/recovery, delayed approval, quota-vs-capacity handling, tile-menu downloads, routing, highlight scoring, captions, transparent graphics, FFmpeg/QC, content quality, timestamps, and Studio configuration. Live Google Flow behavior depends on the current account/UI; first test with a short, low-credit job.

## Safety

- Use `dry_run: true` before expensive production.
- Keep `flow_approval: once` and a small generation cap until validated.
- Browser automation uses visible UI only; it does not bypass authentication, CAPTCHA, quotas, or service limits.
- Review generated factual, health, financial, or legal content before publishing.

## 15. Upgrade and first testing sequence

Stop Studio and running jobs. Check the installed version using `cat VERSION`; the old folder name does not identify its patched version. Keep your original installation intact.

For **exactly 5.7.10**, use the supplied incremental patch from inside that installation:

```bash
# First back up the whole installation from its parent folder.
cp -a AutoVideoAI-v5.7.0 AutoVideoAI-backup-before-v580
cd AutoVideoAI-v5.7.0
patch --dry-run -p1 < ../AutoVideoAI-v5.7.10-to-v5.8.0.patch
# Apply only if the dry run completes without failures.
patch -p1 < ../AutoVideoAI-v5.7.10-to-v5.8.0.patch
python3 -m compileall -q cli.py app.py engine
cat VERSION
```

For any other version, use the complete ZIP and a fresh virtual environment. Copy `.env` locally and preserve `outputs/`, `data/`, custom `assets/`, and the browser/CDP configuration. Old manifests can contain absolute media paths: keep the old installation in place while testing, or upgrade a backed-up installation in place. Do not remove the old tree until its jobs have been verified. No credentials, browser profiles, or user outputs are in the build.

Recommended order:

1. Run `env-doctor` and `doctor` as shown in section 1.
2. For an existing Flow pause, run recovery-only or manually associate a verified MP4 as shown in section 4. Preserve request sidecars and the saved project URL.
3. Test a single short owned clip with `--ranking-provider gemini-web-hybrid --framing fit` to isolate browser capture/cleanup from API availability. Inspect `logs/gemini/cleanup-latest.json` and saved response files.
4. Run `production-init` for an existing rendered full-video job; add a timed card, rerender, and inspect the result.
5. Run `production-check` with its zero-call default before opting into vision API calls.

Rollback: stop processes and restore the complete pre-upgrade backup. Do not reverse patches over new local edits. Run only one process per job directory; CLI and Studio must not mutate the same job concurrently.

## 16. Production review, graphics, and repair

These commands target full-video job folders, not standalone `clip` output folders. Clip technical results remain in each `.qc.json` and `highlights.json`.

```bash
python3 cli.py v3 production-init JOB-ID
python3 cli.py v3 production-check JOB-ID
```

Studio has the same controls under **PRODUCTION QC**. Select an active job first. Templates are created only if missing, so repeated initialization preserves your edits.

### Review gates and explicit API budget

The local check measures video/audio duration, decode errors, near-black intervals, freezes, loudness and peak. It samples three frames from each final rendered shot, flags long holds and possible perceptual duplicates, and inventories visual/audio sources by SHA256. Defaults flag near-black duration over 8%, a freeze over eight seconds, integrated loudness outside −20 to −10 LUFS, and peaks above −0.1 dBTP. Thresholds are heuristics: a deliberate still or dark scene may need editorial interpretation.

Without a model, semantic review remains incomplete; a local technical pass cannot label the film publish-ready. To explicitly enable Gemini **API** vision review:

```bash
python3 cli.py v3 production-check JOB-ID \
  --model YOUR_AVAILABLE_VISION_MODEL_ID --max-model-calls 5
```

This sends three sampled final frames plus the shot's narration and visual intent to Gemini per uncached shot. It requires `GEMINI_API_KEY`, a model available to that key, and may incur provider charges. A browser subscription is separate. Default budget is zero; the maximum is 100 calls per invocation. Failed attempts consume the call budget, there are no automatic retries, and unused budget is not carried over. Cached responses are keyed to the final video hash, shot interval, narration, intent and model. Changed renders need new review. A 503 produces an incomplete review, never a false pass. The API uses Google's documented [inline image request format](https://ai.google.dev/gemini-api/docs/image-understanding).

The reviewer checks sampled visual relevance, text accuracy, face obstruction, visible watermarks and artifacts. This is **not** continuous video comprehension or an accuracy guarantee. It cannot certify lip sync, full-motion continuity, copyright, factual truth or virality. Perceptual duplicate warnings can flag legitimate repeated framing; they never delete scenes automatically.

Outputs inside `outputs/JOB-ID/production/`:

| File | Purpose |
|---|---|
| `review.json` | Gates, technical issues, per-shot reasons, model and call count |
| `review-progress.json` | Saved partial progress and completion flag |
| `semantic_cache/` | Sampled frames and cached model verdicts |
| `asset_inventory.json` | Existing visual/audio paths and content hashes |
| `rights.json`, `facts.json` | Your provenance and research evidence |
| `repair_plan.json` | Flagged scenes with editable replacement paths |
| `media_overrides.json` | Validated local replacement mapping |
| `ATTRIBUTION.txt` | Required attribution text from the rights records |

`GATES_PASSED` means only the implemented checks passed for that hash. It does not trigger publication. Missing semantic/research/rights evidence yields `NEEDS_REVIEW`. Rerendering invalidates the saved review status. A render now reports `NEEDS_EDITORIAL_REVIEW` even if all recipe/technical checks pass.

### Rights and factual evidence

Run a check to obtain `asset_inventory.json`. For each hash, add exactly one record to `production/rights.json`. Evidence paths are relative to the job root (absolute paths also work). Use `sha256sum FILE` to calculate hashes. Record real permission evidence; do not fabricate licences or assume an entire channel allows reuse.

```json
{
  "assets": [{
    "sha256": "SHA256_FROM_ASSET_INVENTORY",
    "creator": "Asset creator",
    "source_url": "https://source.example/asset-page",
    "license": "Actual licence or written permission",
    "verified_at": "2026-09-29",
    "commercial_use_allowed": true,
    "adaptation_allowed": true,
    "third_party_audio_cleared": true,
    "evidence_file": "production/evidence/permission.txt",
    "evidence_sha256": "SHA256_OF_PERMISSION_DOCUMENT",
    "attribution_required": true,
    "attribution": "Required credit text"
  }]
}
```

The gate checks completeness and matching hashes only. It cannot decide whether a licence actually grants your intended rights. Include narration and music as well as video sources. The current inventory does not independently audit embedded graphics, logos or stock-site terms; those still require review.

`production/facts.json` uses this schema:

```json
{
  "research_complete": true,
  "claims": [{
    "claim": "The exact factual statement used in the narration",
    "verified": true,
    "sources": ["https://authoritative.example/supporting-page"]
  }]
}
```

This is a research record, not automated fact checking. Empty claims fail the research gate. For fictional work, document the fictional premise explicitly. `series_bible.json` is a reference inventory only; it does not implement cartoon rigs or character consistency enforcement.

### Meaningful timed text cards

Edit `production/graphics.json`. Times are seconds on the final narration timeline. With nonempty custom events, these replace automatic editorial cards; any automatic branding watermark remains. Empty events retain the existing automatic graphics workflow. Custom graphics validation errors stop rendering rather than silently dropping your cards.

```json
{
  "events": [
    {"kind": "list", "start": 5, "end": 12,
     "title": "Three steps to speak clearly", "active": 0,
     "rows": [{"label": "Pause and breathe"}, {"label": "Choose one message"}, {"label": "Give one example"}]},
    {"kind": "list", "start": 12, "end": 19,
     "title": "Three steps to speak clearly", "active": 1,
     "rows": [{"label": "Pause and breathe"}, {"label": "Choose one message"}, {"label": "Give one example"}]},
    {"kind": "list", "start": 19, "end": 26,
     "title": "Three steps to speak clearly", "active": 2,
     "rows": [{"label": "Pause and breathe"}, {"label": "Choose one message"}, {"label": "Give one example"}]},
    {"kind": "list", "start": 26, "end": 30,
     "title": "Remember all three", "rows": [{"label": "Pause and breathe"}, {"label": "Choose one message"}, {"label": "Give one example"}]}
  ]
}
```

`active` is zero-based and optional; omit it for the recap. Other kinds:

```json
{"kind":"comparison","start":30,"end":35,"title":"Before and after",
 "rows":[{"label":"Before","detail":"Several competing ideas"},{"label":"After","detail":"One clear message"}]}
```

```json
{"kind":"bar_chart","start":35,"end":40,"title":"Measured response times",
 "unit":"seconds","source":"Your actual experiment, date and reference",
 "rows":[{"label":"First trial","value":4},{"label":"Second trial","value":2}]}
```

Chart numbers above are examples, not researched claims. Supply real evidence. Values must be finite and nonnegative, with at least one positive value. Charts use a zero baseline and scale to the largest value. Cards allow one to five rows, at least one second each, no overlaps, and must fit the final duration. Long labels fail readability validation. PNGs have a transparent canvas and a small translucent rail rather than full-screen darkening. Behind-head compositing/segmentation is not provided.

Rerender without regenerating paid media:

```bash
python3 cli.py v3 render JOB-ID --quality preview
# After visual inspection:
python3 cli.py v3 render JOB-ID --quality high
```

### Replace a bad scene without regenerating the whole job

After checking an existing rendered job, edit its `repair_plan.json`. Keep only scenes you intend to replace and fill each `replacement_path` with a relevant local video. Use one nonduplicate clip long enough for the entire shot window. The old final video's hash must still match.

```bash
python3 cli.py v3 production-repair JOB-ID \
  --plan outputs/JOB-ID/production/repair_plan.json
python3 cli.py v3 render JOB-ID --quality preview
python3 cli.py v3 production-check JOB-ID
```

All selected clips are probed/decoded before committing the replacement map. They are copied into `production/repairs/`, hashed, and checked again at render time. Replacement consumes zero generation credits. Original takes and the Flow project remain intact. Invalid, short, changed, duplicate-shot or stale-plan input is rejected. This workflow is for rendered jobs with a timeline; a job blocked before its first render should use `associate` and correct its timing/coverage first. Replacement does not automatically shorten an oversized narration window or change the script. To remove an override, back up and edit `media_overrides.json`, then rerender and review again.

## 17. Feature status and remaining roadmap

| Area | Included in this build | Still incomplete / requires live validation |
|---|---|---|
| Flow | Saved project reuse, durable request guard, tile download recovery, manual association, bounded waits | Actual Google/WSL browser closure and current UI must be tested with your account; downloading is not guaranteed |
| Gemini cleanup | Exact submitted-chat targeting, saved answer, scoped delete, diagnostic JSON | UI changes can safely prevent deletion; old chats are not bulk deleted |
| Long-form | Timing checks, exact duplicate exposure gate, hard-cut render, semantic sample review, local repair | Autonomous global director, automatic multimodal stock replacement, research agent |
| Graphics | Automatic short headings plus explicit timed lists/comparisons/bar charts | Remotion, general table/layout authoring, behind-head masking, automatic verified chart research |
| Clips | Gemini/API/browser fallback, valid partial selections, titles, preserved source framing, caption/QC reports | Dynamic active-speaker tracking, reliable automatic hook/payoff certification, complete interrupted-clip resume |
| Reels | Existing vertical production mode, native-audio options, captions and branding | Automated multiple hook variants and platform performance optimization |
| Cartoons | Existing themes, reference assets, series-bible template | Persistent rigs, enforced multi-episode character consistency, lip-sync/pose QA, Blender production workflow |
| Rights | Per-asset hash/evidence registry and attribution export | Automated legal clearance; no channel-wide reuse whitelist |
| Publication | Review reports and local export | Social account publishing, trending-content discovery, similarity audit, analytics feedback loop |
| Autonomy | Resumable generation and deterministic failure states | No guarantee of production-grade output with zero human intervention |

The main engine remains Python/Pillow/FFmpeg with optional configured providers. This build does not bundle CapCut Pro, Remotion, paid subscriptions, GPU models or automatic access to external editing applications.


## 18. v5.8.1 resume and reels correction

The default clip framing is `face-crop`: a filled 1080×1920 reel. `fit` keeps the complete source frame and matches its orientation/aspect (landscape remains landscape; portrait remains portrait). Existing YAML with `framing: fit` continues to use that source-matched behavior; existing MP4 files are not changed. Static face cropping can still miss speaker changes.

The session log confirms Gemini cleanup succeeded and four verified selections were retained from the requested ten. Those parts should not be retried solely to fix framing. To reprocess the original source, append `--framing face-crop` to your clip command and use a new output folder.

Studio resume is now queued for a new script run and each job has only one pause panel per run. The misleading manual prompt/MP4 download panel is removed from FLOW SESSION; the advanced CLI associate command remains. A pending JPG opening frame is not a pending MP4 shot.

Flow recovery compares media identity without tile dimensions/labels and tolerates known signing-parameter changes only when a separate asset ID is present. It never replaces an unmatched asset with an arbitrary newest tile. Failed matching writes `<pending-path>.recovery.json` with the expected signature and visible candidates, and preserves the actual exception reason. This fixes layout-dependent matching, but does not prove which mismatch occurred in your old request because the old log did not include its signature. If the asset is still unidentifiable, resume remains paused without new generation. Do not delete the request journal.

Expected CLI pauses now print PAUSED and next actions, exiting with status 2 instead of a traceback.

Upgrade from exactly VERSION 5.8.0 using `patch --dry-run -p1 < AutoVideoAI-v5.8.0-to-v5.8.1.patch`, then apply without `--dry-run` only if successful. Back up first. Other versions should use the full ZIP. Resume the existing job with:

```bash
python3 cli.py v3 resume 20260929-125429-7-habits-to-build-your-m-8a59
```

If it still cannot identify the frame, share the resulting `shot_001_open.jpg.recovery.json` with sensitive URL query values redacted, along with a screenshot of the Flow project grid. The asset-matching issue may need that evidence; repeatedly resuming an unchanged failure cannot resolve a missing asset.

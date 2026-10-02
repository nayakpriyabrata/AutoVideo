# v6.0.0 Content Studio — first-stage testing release

This implements the first testable part of the publishing roadmap, not all of its
future research, translation, analytics and social-API features. No live Google
credits, native-language voice auditions or account publishing were used in the
offline validation.

## Included

- **STUDIO:** English/Hindi/Odia selection; conservative Instagram/Facebook/
  YouTube Shorts/YouTube long-form delivery recipes; approved external JSON
  script/storyboard import and optional owned/licensed native narration import.
- **CONTENT INBOX:** pasted article/post ideas, bounded allowlisted HTTPS article
  imports, RSS imports from Technivella/Factozone, and downloadable external-writer
  briefs. Source data stays untrusted, unverified and unapproved for generation.
- **CHARACTER LIBRARY:** original fictional identity descriptions and optional
  authorized local image references, with version/hash snapshots per job.
- **AI RECREATE:** an authorized local clip + matching transcript sidecar or
  reviewed pasted transcript → new review-gated original-character job. Planning
  and approval submit no TTS/image/video requests. Explicit Resume runs the
  existing TTS/Flow pipeline with its saved project, credit guard and journals.
- **CLIP STUDIO:** explicit optional soft music switch, licensed local track,
  adjustable low gain, speech-preserving mix and music ducking. Default is off.
  Generated clips get hash-linked transcript sidecars for recreation.
- **PUBLISHING DESK:** separate 30fps destination copies, language/account review
  records, rights/facts/language/audience/AI-disclosure choices and local manual-
  upload reminders. No account is uploaded to or scheduled remotely.
- **CLI:** corresponding imports, character creation, recreation, approval,
  template, delivery export and owned-account metric JSON import commands.
- **Indic text:** licensed Noto Sans Oriya/Devanagari fonts; HarfBuzz/FreeType
  shaping when Pillow lacks libraqm, plus correct ASS font-family selection.

## First tests to try

### 1. Existing clips with optional music

Open **CLIP STUDIO**. Leave **Add soft background music** off to preserve the
source-only audio. Enable it to choose a local music file, licence declaration
and soft gain (default 0.08). This mixes the source speech at unity gain after
normal stereo conversion; it no longer halves speech just because a music bed
exists. Review actual output loudness; this path is not loudness certification.

```bash
python3 cli.py v3 clip /path/to/your-video.mp4 --source-rights own_content \
  --background-music-enabled --background-music /path/to/licensed.mp3 \
  --music-license royalty_free_licensed --music-volume 0.08

# Explicit off ignores a supplied/saved music path:
python3 cli.py v3 clip /path/to/your-video.mp4 --source-rights own_content \
  --no-background-music-enabled
```

English/Hindi speech timing can be selected. The Whisper clip route does not
certify Odia transcription; use a reviewed Odia transcript in AI RECREATE or an
approved narration plan instead. Clip extraction requires system FFmpeg/FFprobe
(and yt-dlp for a permitted URL); no browser verification is bypassed.

### 2. Recreate with an original AI character

1. In **CHARACTER LIBRARY**, describe an original fictional presenter/character,
   confirm authorization, and optionally supply PNG/JPEG/WebP reference paths.
2. In **AI RECREATE**, select a generated/local clip. A matching
   `clip-name.transcript.json` sidecar can supply its transcript; otherwise paste
   a reviewed transcript. Confirm rights to adapt BOTH the transcript and source.
3. Choose language, character, optional licensed music and the Flow credit ceiling.
4. **Create recreation storyboard** creates a separate job and makes no generation.
5. Inspect/edit `approved_content_plan.json`: scene text must cover the narration
   exactly in order. Image/visual intent and motion directions must be usable.
6. Approve the exact storyboard/character/budget. This still submits no generation.
7. Select that job in **QUEUE**, then explicitly **Resume**. Flow creates the
   character master if no reference exists, then storyboard frames and scene
   videos through the existing reference-first generation workflow. Authored
   narration is synthesized separately; original source speech is not cloned.
8. Review the result. Repair individual scenes instead of blindly resubmitting
   pending generations. Preserve the original source and request journals.

```bash
python3 cli.py v3 character-create --name "Our garden robot" \
  --description "Original small green robot, round yellow eyes, blue gardening jacket, consistent rounded cartoon proportions" \
  --original-confirmed

python3 cli.py v3 recreate-clip /path/to/clip.mp4 --character-id CHARACTER_ID \
  --source-rights own_content --adaptation-confirmed --language en --max-credits 50

python3 cli.py v3 approve-recreation JOB_ID
python3 cli.py v3 resume JOB_ID
```

This is **new scene reconstruction, not person removal from the exact original
pixels**, not motion transfer, not voice cloning and not guaranteed lip-sync.
The source person/frame is not uploaded as an identity reference by this path.
A copied transcript still needs adaptation rights; replacing a person with an
avatar does not establish originality, fair use or monetization eligibility.

The Flow budget can stop a recreation that needs more scenes than its allowance.
Planning does not promise a fixed total clip cost; actual submitted model charges,
reference generation, rejected takes and retries still matter. Unknown/missing
journals are never assumed duplicate-credit-safe.

### 3. Language and approved script import

Choose **Production language** in STUDIO. Odia defaults to explicitly estimated
script timing rather than pretending the Whisper route supports it. With Odia,
auto TTS requires Gemini; unavailable Gemini does not silently use an English
voice. Native narration import avoids TTS and is useful for reviewed recordings.
The supported-language configuration has offline coverage, but native voice
naturalness and timing must be auditioned with your actual provider/account.

To import a script from your own writer, download the chapter template from
CONTENT INBOX, fill it, record rights and set `approved: true`. Use its path in
STUDIO or `--approved-plan-path`. Imported narration is preserved; automated
script rewriting is disabled. You cannot replace its script after shot planning
without creating a separate project.

```bash
python3 cli.py v3 longform-template --topic "Practical balcony gardening" \
  --language or --output garden-plan.json

# After editing/reviewing the JSON:
python3 cli.py v3 create --topic "Practical balcony gardening" --language or \
  --destination youtube_long --duration 360 --approved-plan-path garden-plan.json \
  --narration-input-path /path/to/approved-odia.wav --plan-only
```

The template supports chapters, evidence and scene directions; this is not yet
an autonomous source-verifying research agent or a fully multilingual shared
visual-project manager. Estimated caption timing always needs review.

### 4. Source ideas and external writer briefs

```bash
python3 cli.py v3 source-import --text-file permitted-article.txt \
  --title "My source idea" --brief-output original-brief.txt

python3 cli.py v3 source-import --url https://factozone.com/feed/ --feed
```

Public fetches validate domains, HTTPS, current DNS address scope, redirects,
robots rules, content type and size. They do not run site JavaScript, follow
advertising/download links or turn article instructions into commands. Use
paste/import if a site denies access. This is not a full general web crawler or
proof that a source has granted reuse rights. Public-network controls are a
limited first-stage client, not a network-level guarantee against all DNS races.

The downloadable brief requests an original angle and marks facts for review.
It does not automatically call a writer or submit media. Arena automated access
and commercial-output permission are not added or assumed; use authorized
production services or permitted manual workflows.

### 5. Destination files and manual release review

```bash
python3 cli.py v3 export-delivery /path/to/master.mp4 \
  --folder outputs/deliveries --destination instagram_reel --language hi
```

The source remains unchanged. `fit` preserves the full frame with padding;
`crop` is explicitly selectable. Neither performs active-speaker tracking or
editorial reframing. Recipes are conservative application ceilings, not claims
of every platform's current maximum (short recipes use 180 seconds).

Review the destination, actual account ID, rights, native-language quality,
facts/story, kids audience and disclosure in PUBLISHING DESK. Scheduling records
**local reminders only**. Connected OAuth publication, remote scheduling, account
analytics downloads, thumbnails/covers and performance experiments are not yet
implemented. Owned-account metric JSON can be imported from CLI, but there is no
automatic metric scraping or cross-platform virality scoring.

## Configuration additions

`video_config.yaml` accepts `language: en|hi|or`, `destination`,
`approved_plan_path`, `narration_input_path`, and `character_id`. Existing
voiceover/text-card/music flags remain compatible. Relative import paths in YAML
are resolved beside that file. Native fonts/licenses and shaping dependencies
ship with this source release; reinstall requirements when upgrading.

`clip_config.yaml` accepts `language` (verified Whisper path: en/hi) and
`background_music_enabled`. False explicitly overrides a saved music path;
true requires a music file. Existing configurations without this flag retain
the previous path-driven optional music behavior.

## Delivered versus still planned

**Delivered:** first-stage UI/CLI, safe local approvals, source/library/import
schemas, clip recreation dispatch, Indic text, destination encodes and test
coverage. **Still planned:** automatic factual research/refinement, tested new
Meta/xAI video adapters, persistent provider-independent prompt-library search,
shared multilingual visual timelines, complete chapter-directed autonomous edits,
cover/thumbnail generation, official publishing OAuth, remote analytics and
human-reviewed production calibration. There is no guarantee of virality,
copyright clearance, world-class rendering or zero-review publication.

## Upgrade and validation

Stop the dashboard, back up your installation, preserve `.env`, settings,
outputs, `data/` (now also your character/inbox library), profiles and Flow
journals. Overlay only source, reapply custom config, then reinstall
`requirements.txt` in your existing environment. Never erase runtime/private
folders to clear a pause. The new ZIP excludes all these runtime records.

Offline tests exercise real shaped typography, encoded music and destination
outputs, actual dashboard pages, script preservation, content/character/budget
approval hashes, rights declarations, malformed source URL checks and no-provider
planning. Test skips and live-provider limitations are reported with the release.

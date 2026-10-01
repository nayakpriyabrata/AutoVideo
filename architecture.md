# AutoVideoAI v3 — Architecture

## Pipeline

```
Topic → Content Plan → Script → Narration (+word timings) → Story Bible
  → Director (voice-timed shots) → Storyboard frames → Prompt compile
  → Budget gate → Generation (takes) → QC → Retries → Review
  → Timeline → Captions → Sound → FFmpeg render → 1080p MP4
```

## Source layout

```
engine/
  factory.py            # v3 orchestrator (resumable stages, dry-run aware)
  project/              # manager.py (isolated jobs), manifest.py (pydantic), database.py (sqlite)
  planning/             # script.py, director.py, story_bible.py, prompt_compiler.py
  providers/            # base.py, flow_browser.py, comfy_provider.py, stock_provider.py, image_provider.py
  routing/              # credit_router.py, provider_router.py
  audio/                # tts.py (edge-native timing + fallbacks), sound_design.py
  qc/                   # video_qc.py (technical + continuity + retry mapping)
  render/               # timeline.py, captions_ass.py, ffmpeg_renderer.py
  reference_manager.py  # refs + FFmpeg frame extraction
  automation.py         # v2 pipeline (kept) + v3 wrappers
config/
  flow_models.yaml      # models, routing tables, budgets (EDIT, don't hard-code)
  flow_ui.yaml          # Flow selectors (repair UI drift here)
  presets/*.yaml        # style presets
  voices.yaml           # voice registry
tests/                  # pytest, mocked, never spends credits
```

## Key decisions

- **Job isolation**: every production lives in `outputs/JOB-ID/` with fixed subfolders.
  No shared clip folders. Manifest (`production_manifest.json`) is source of truth.
- **Resumable**: each stage persists before the next starts; reruns skip finished work.
- **Profiles over modes**: `FLOW_CINEMATIC|BALANCED|ECONOMY|LOCAL_FREE|FREE_HYBRID|MANUAL_DIRECTOR`.
  Premium profiles raise `NeedsDecision` instead of silently downgrading.
- **Voice-timed shots**: shot windows derive from narration word timings snapped to
  sentence edges (gapless), never equal splits.
- **Reference-first**: storyboard/start/end frames feed image/frames-capable models;
  each accepted shot donates an end frame to the next shot.
- **Budget gate**: projected credits (config estimates + retry reserve) must fit
  `MAX_CREDITS_PER_VIDEO` or the job pauses BEFORE spending anything.
- **QC-gated takes**: `take_01..N.mp4` → scored → `accepted.mp4`. Failures map to
  targeted prompt modifiers for retries (never blind re-sends).
- **FFmpeg primary renderer**: filter_complex (xfade, ASS burn, sidechain ducking,
  loudnorm), HW encoder auto-detect; MoviePy fallback on failure.
- **Dry-run honesty**: `dry_run` jobs simulate generation (no browser, no credits)
  and skip rendering; UI/CLI always label DRY RUN / FLOW CREDITS / LOCAL FREE.

## Data flow per shot

`Shot` (manifest) → `compile_shot` (+bible+preset) → provider `.generate()` →
`take_NN.mp4` → `analyze_take` → `qc/*.json` → accept/retry → `accepted.mp4` →
`best_end_frame` → next shot's `start_frame`.

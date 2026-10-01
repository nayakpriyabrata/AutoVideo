# AutoVideoAI v4.1 — Long-form pacing + generation audit

This release fixes problems found in the first 5-minute STORYBOARD_ECONOMY real run.

## What changed

1. **Long narration is actually split into visual beats.**
   v4.0 could leave a 20–60 second TTS sentence as one shot, producing only ~8 shots for a 5-minute video. v4.1 applies the existing timed-word splitter before shot windowing. With the default 8-second ceiling, a 5-minute narration typically produces roughly 35–50 visual beats depending on pauses and sentence boundaries.

2. **Optional `--shot-max-seconds`.**
   Use `--shot-max-seconds 8` for normal YouTube pacing or 5–6 for faster explainer pacing.

3. **Stock planning reflects reality.**
   Stock slots are only reserved when a local stock library or configured Pexels/Pixabay source is actually available. Otherwise those scenes are planned as image-motion from the start.

4. **Runtime fallbacks are visible.**
   If a Flow scene, stock scene, or another provider falls back to image-motion, the terminal now prints a warning instead of silently continuing.

5. **Planned vs actual provider tracking.**
   Every shot now records `actual_provider`, `actual_model`, `fallback_reason`, and observed credits. The final job writes `generation_summary.json` and `generation_summary.md`.

6. **`v3 audit JOB_ID`.**
   Audits shot density, planned strategies, actual providers, fallbacks, and recorded credits.

7. **FFmpeg subtitle retry.**
   If libass/subtitles fails because of an explicit `fontsdir` under WSL, the renderer retries once without `fontsdir` before falling back to MoviePy.

## Recommended 5-minute test

First do a no-spend planning run:

```bash
python3 cli.py v3 create \
  --topic "How AI agents will change work" \
  --type faceless_youtube \
  --duration 300 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 50 \
  --video-share 0.18 \
  --stock-share 0.20 \
  --max-flow-scenes 6 \
  --shot-max-seconds 8 \
  --frame-source auto \
  --flow-approval once \
  --max-generation-credits 10 \
  --dry-run
```

Inspect `economy_plan.md`. If it looks sensible, create a fresh real job with the same command minus `--dry-run`.

Do not resume a v4.0 job if you want the denser shot plan: its 8-shot storyboard is already persisted. Create a new v4.1 job.

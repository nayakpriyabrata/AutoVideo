# AutoVideoAI v4.0 — Storyboard Economy Engine

This build is optimized for **long YouTube videos and Shorts/Reels on a limited Google Flow credit budget**.
It does not require Gemini/Veo API billing.

## Core idea

Instead of spending credits on every narration scene, AutoVideoAI decides which scenes genuinely need AI motion.

- **Flow video** — only hooks, hero moments, meaningful action, transformations, and important reveals.
- **Image motion** — free opening + closing frames, animated locally with pan/zoom/crossfade.
- **Stock B-roll** — optional local stock library first; Pexels/Pixabay APIs are optional, not required.
- **Continuity** — a scene's closing frame is reused as the next scene's opening frame when possible.
- **Credit guard** — paid Flow scenes use Gemini Omni Flash 360p in this profile and any single Agent confirmation above the configured cap is not approved.
- **Fallback-first** — if Flow UI/download fails, a STORYBOARD_ECONOMY shot falls back to local image-motion rather than blocking the whole movie.

## Recommended 60-second Reel

```bash
python3 cli.py v3 create \
  --topic "5 AI skills that will matter in 2027" \
  --type shorts \
  --duration 60 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 25 \
  --video-share 0.20 \
  --stock-share 0.15 \
  --frame-source auto \
  --flow-approval once \
  --max-generation-credits 10
```

## Recommended 5-minute YouTube video

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
  --frame-source auto \
  --flow-approval once \
  --max-generation-credits 10
```

Run the same command with `--dry-run` first to create `economy_plan.json` and `economy_plan.md` without spending credits.

## Opening/closing frame continuity

For each shot v4 creates:

```text
shot_001_open.jpg  -> motion/transition -> shot_001_close.jpg
                                            |
                                            +--> reused as shot_002_open.jpg
```

For paid Flow motion scenes the same pair is attached to the Flow Agent as first/last-frame guidance when the current UI accepts attachments. For image-only scenes the pair is animated locally, so the scene still has movement without spending Flow credits.

## Stock video without any API

Create/drop clips under:

```text
assets/stock_library/
```

Use descriptive filenames:

```text
city_traffic_night.mp4
office_laptop_team.mp4
mountain_drone_sunrise.mp4
finance_phone_market.mp4
```

The engine matches filenames to scene keywords. Use only media you are licensed to use.

Optional: set `PEXELS_API_KEY` or `PIXABAY_API_KEY` if you want automatic external stock search. These are not Gemini/Flow APIs and are not required.

## Frame source

`--frame-source auto` is recommended:

1. Try the logged-in Flow image path (Nano Banana 2 Lite when available).
2. If Flow's image UI/download changes, automatically use the free image provider.

`--frame-source free` skips Flow for stills completely and is the most robust/no-credit path.

## Files added to each job

In addition to the normal production bundle:

- `economy_plan.json` — machine-readable routing and credit estimate.
- `economy_plan.md` — human-readable scene table.
- `storyboard/shot_XXX_open.jpg`
- `storyboard/shot_XXX_close.jpg`
- `storyboard/character_master.jpg` when the story uses a recurring character.
- `storyboard/location_master.jpg`

## Current Flow caveat

Google changes Flow/Agent markup often. v4 attempts to attach references, approve low-cost generations, detect completed media, and download it. If a paid Flow shot cannot be downloaded automatically, STORYBOARD_ECONOMY falls back to the already-created frame pair so the production can still finish. The diagnostic screenshot/UI dump remains available for future selector repair.

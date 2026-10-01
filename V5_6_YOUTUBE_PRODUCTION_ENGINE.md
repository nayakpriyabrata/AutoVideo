# AutoVideoAI v5.6.0 — YouTube Production Engine

v5.6 changes the long-form faceless workflow from an image slideshow into a mixed-media edit.

## New `youtube_pro` production mode

For a five-minute video the default target is about ten true-motion inserts, distributed through the whole timeline instead of clustered in one section:

- ~3–4 Google Flow AI-motion hero clips (credit/budget permitting)
- the remaining motion slots use royalty-free stock video
- all other beats use the existing image-motion pipeline
- stock/Flow failure falls back to image-motion instead of blocking the whole film

Use `--dynamic-video-scenes`, `--flow-scenes`, and `--stock-scenes` to override the mix.

## Free stock sources first

Stock selection priority:

1. `assets/stock_library` (your own clips)
2. Pexels Video API when `PEXELS_API_KEY` is configured
3. Pixabay Video API when `PIXABAY_API_KEY` is configured
4. isolated browser fallback against public Pexels/Pixabay search pages when no key is available

The browser helper runs in a separate Python process and persistent browser profile so it cannot interfere with Gemini or Flow Playwright sessions. Source metadata is stored next to downloaded stock clips as `*.source.json`.

`--stock-source auto|api|browser|local` controls this behavior.

## Editorial graphics instead of permanent transcript text

`youtube_pro` keeps the complete `.srt`/`.ass` caption files for YouTube accessibility but does not burn the entire transcript into the picture by default.

Instead it adds restrained editorial graphics:

- opening promise/title card
- numbered section/chapter cards
- sparse key-point popups
- quick recap/table card near the end
- like/subscribe/comment end-screen card
- optional channel-name watermark in the lower-right corner
- optional logo on intro/outro cards

Use `--caption-display full` if you still want permanent captions burned into the video.

## Background music

`--background-music auto` uses:

1. a matching file already in `assets/music`, then
2. a no-key Pixabay browser lookup as a best-effort fallback.

Music is mixed softly below narration with side-chain ducking. The normal master is forced to stereo even when narration is mono.

You can also use `--background-music local` and add your preferred licensed music to `assets/music` for maximum repeatability.

## Branding

Use:

```bash
--channel-name "Your Channel Name" \
--channel-logo "/path/to/logo.png"
```

In `youtube_pro`, a supplied channel name automatically enables a subtle watermark and branded end screen.

## Recommended 5-minute command

```bash
python3 cli.py v3 create \
  --topic "5 habits winners build for a successful life" \
  --type faceless_youtube \
  --duration 300 \
  --content-type education \
  --profile STORYBOARD_ECONOMY \
  --production-mode youtube_pro \
  --dynamic-video-scenes 10 \
  --flow-scenes 3 \
  --stock-scenes 7 \
  --stock-source auto \
  --max-credits 30 \
  --max-flow-scenes 3 \
  --shot-max-seconds 7 \
  --frame-source flow \
  --flow-approval once \
  --max-generation-credits 10 \
  --flow-frame-retries 3 \
  --flow-video-retries 0 \
  --flow-video-ready-grace-seconds 60 \
  --flow-video-recovery-wait-seconds 120 \
  --network-wait-seconds 180 \
  --flow-capacity-wait-seconds 300 \
  --flow-capacity-retries 4 \
  --flow-reuse-mode exact \
  --script-provider gemini-web \
  --script-quality publish \
  --tts-provider auto \
  --caption-provider script-timed \
  --caption-display none \
  --background-music auto \
  --music-mood "soft motivational modern ambient instrumental" \
  --channel-name "YOUR CHANNEL NAME" \
  --max-tts-speedup 1.08 \
  --render-quality high
```

If you do not have stock API keys, leave `--stock-source auto`; browser fallback will be attempted. If the browser source is temporarily unavailable, that slot degrades to image-motion rather than stopping the production.

## Reliability notes

- Gemini web, Flow, stock browser and music browser do not share one Playwright lifecycle.
- Stock/music browser work is isolated in a subprocess.
- Full captions are still exported even when `--caption-display none` is used.
- The v5.3.4 black/truncated-render recovery remains active.
- Runtime fallback is reported in `generation_summary.json`.
- Graphics are saved in `render/graphics/` and planned in `graphics_plan.json`.
- Sound selection is recorded in `audio/sound_plan.json`.
- Final publish checks remain in `publish_readiness.json`.

### Browser media debugging

The stock/music browser fallback is headless by default. Set `AUTOVIDEO_MEDIA_BROWSER_VISIBLE=1` before the run if you want to watch its Pexels/Pixabay searches in a visible window.

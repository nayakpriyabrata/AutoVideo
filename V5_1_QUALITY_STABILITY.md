# AutoVideoAI v5.1 — Clean Quality & Stability Build

v5.1 is based on the clean v5.0.3 tree. It deliberately avoids carrying forward
mixed/reversed patch state from older working directories.

## What changed

### Rendering and captions
- FFmpeg remains the master renderer even when the local `subtitles/libass` filter fails.
- If FFmpeg advertises NVENC/QSV/AMF but the hardware encoder cannot actually open, the same render is retried automatically with `libx264`.
- If ASS burn-in fails, v5.1 renders the complete FFmpeg master without ASS and adds
  captions in a narrow Pillow/MoviePy overlay pass (`ffmpeg+caption-overlay`).
- Full MoviePy reconstruction is now reserved for a true FFmpeg master-render failure.
- Word-pop caption events are globally non-overlapping and use a single phrase card,
  eliminating double/stacked caption flashes.
- Timeline transition overlap is compensated so picture duration follows narration.
- Missing/unaccepted shot media can borrow the nearest usable visual instead of
  shortening the final film.

### Storyboard variety
- LLM `visual_intent` now controls concrete environments/actions instead of forcing
  every beat into the same canonical room.
- Previous closing frames are reused only when the next shot genuinely shares the
  same environment and continuity benefits from it.
- Hook/insert/b-roll/outro coverage refreshes composition.
- A shot opening that is byte-identical to the generic location master is rejected
  and regenerated as a shot-specific composition.
- Lightweight perceptual-hash QC detects near-duplicate storyboard frames and writes
  `visual_diversity.json`.
- Image-motion is coverage-aware (hook, close-up, insert, b-roll, outro use different
  pan/zoom behavior).

### Flow accounting/reuse
- Agent references are de-duplicated by file content, so the same JPEG cannot be
  attached twice under different names (for example opening frame + location master).
- A newly generated/recovered Flow video with unknown observed cost is charged using
  the configured model estimate rather than silently reporting zero credits.
- Generation summary provider counts now describe accepted shots only and list
  unaccepted/bridged shots separately.

### TTS and captions
- Gemini TTS accepts both RIFF/WAV and raw 24 kHz PCM responses.
- Gemini Interactions response parsing covers SDK and REST response shapes.
- Groq Orpheus narration is chunked below its per-request text limit and returns
  detailed API errors rather than a generic 400.
- Kokoro/Torch is no longer attempted in `--tts-provider auto` unless
  `AUTOVIDEO_ENABLE_LOCAL_TTS=1`; explicit `--tts-provider kokoro` still works.
- This prevents multi-GB local AI dependencies from being pulled into a laptop that
  is already low on storage.

### Storage protection
- Before production work starts, the target output drive is checked.
- Default hard stop: < 1.5 GB free (`AUTOVIDEO_MIN_FREE_GB`).
- Default warning: < 5 GB free (`AUTOVIDEO_WARN_FREE_GB`).
- This prevents truncated JPEG/MP4 files caused by a nearly-full disk.

## Upgrade recommendation

Use the clean v5.1 archive rather than patching an existing v5.0.x folder. Copy only
your `.env` if needed. The Flow project-media cache remains shared under the user's
AutoVideoAI data directory, so clean source upgrades can still reuse compatible media.

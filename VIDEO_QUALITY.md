# Video-quality upgrade

This v5.8.6 checkout/packaged build contains editable source based on the uploaded
**v5.8.4 Settings Hotfix** release, plus the improvements below. Run from the
folder containing `cli.py` and `app.py`. The original v5.8.4 ZIP is preserved as a
reference and does not contain these changes; the v5.8.5 and newer ZIPs do. See
[V5_8_5_QUALITY_PAUSE_DIAGNOSTICS.md](V5_8_5_QUALITY_PAUSE_DIAGNOSTICS.md) for the
paused-job upgrade procedure.

The v5.8.6 build additionally provides independent voiceover and card switches,
real music-only/silent output, and redesigned readable display cards. See
[V5_8_6_MUSIC_ONLY_TEXT_CARDS.md](V5_8_6_MUSIC_ONLY_TEXT_CARDS.md).

## What improved

### Narration and background audio

The primary FFmpeg renderer now splits narration into an audible branch and a
sidechain detector branch. Previously, adding any music, ambience, or sound
effect reused a single filter output twice, causing FFmpeg to reject the graph.

- Music/ambience/SFX renders work without forcing a full MoviePy rebuild.
- Music is ducked during narration using the existing compressor settings.
- Adding a bed no longer automatically halves narration gain. Configured bed
  levels are also preserved when more than one sound source is present.
- Channel layouts are normalized **before** mixing. Stereo music remains stereo
  when the narration is mono, including on the no-loudnorm compatibility path.
- A bounded internal audio drain guard prevents early loss of background music
  near EOF on the tested FFmpeg 7 build. The mixed result is trimmed back to the
  actual narration duration; this does not lengthen the movie.
- The normal master still targets **−14 LUFS / −1.5 dBTP** through FFmpeg's
  existing single-pass loudness filter. This is a target, not a measurement or
  guarantee; review the finished mix, especially after a compatibility retry.

These audio changes apply to the production master renderer. The optional
highlight clipper retains its separate audio-mixing path.

### Readable, correctly timed captions

All eight templates remain available: `MINIMAL`, `HORMOZI`, `DOCUMENTARY`,
`CINEMATIC`, `KARAOKE`, `TECH`, `KIDS`, and `OPUS`.

- Timestamps round at their actual precision and carry correctly across minute
  and hour boundaries. For example, an ASS time of `59.999s` becomes
  `0:01:00.00`, not the invalid `0:00:60.00`.
- Two-line wrapping measures visible words rather than color/karaoke tags.
  Single long words are kept intact, without an empty second line.
- Phrase grouping accounts for spaces, punctuation, pauses, and a three-second
  reading-duration limit. A single long word is never split or retimed.
- Font size, outline, shadow, and platform safe zones scale with output size;
  the original 1080p styles keep their existing dimensions.
- Word highlighting and SRT cues do not overlap the next phrase. Closely spaced
  cues are not made negative by an artificial gap.
- Karaoke highlights include inter-word pauses instead of shifting later words
  early. Inactive words use the normal template color.
- Production and highlight captions are clamped to the actual narration/clip
  duration, including their short end-of-phrase holds.
- Nonfinite, negative, reversed, missing, or out-of-order word timings fail with
  a clear error **before** writing sidecars. Events too short for ASS's 10ms
  precision are omitted with a timing-review warning rather than stretched or
  written with an invalid interval.

Text order is not sorted, invented, or rewritten to repair bad timing. Estimated
ASR/script timestamps still require a human sync check. Literal subtitle control
characters and font coverage for different scripts remain review considerations.

## Use the updated code

Use the normal dashboard/CLI from the repository root after installing
`requirements.txt`; no new API key or setting is required for these fixes.

For an existing job with accepted media and saved narration, **back up its final
MP4 first**, then render locally:

```bash
python3 cli.py v3 render YOUR_JOB_ID --quality high
```

This command reuses the job's accepted media and does not submit new Flow
visual-generation requests. It replaces the final render; do not delete old
outputs or paid-generation request records. If word timestamps are missing,
the existing configured caption provider may still be invoked.

For a new reel, these existing settings are a useful starting point:

```yaml
topic: "Three practical ways to protect your focus"
production_mode: reels_pro
duration: 45
script_quality: publish
render_quality: high
caption_display: full
background_music: local
```

Place a music file you have appropriate rights to use in `assets/music/`.
`local` avoids browser music lookup; missing local music will not be fabricated.
Save the YAML as `my_video.yaml` and inspect its plan before generating:

```bash
python3 cli.py v3 create-config my_video.yaml --plan-only
```

This creates a job/configuration without starting generation. Follow the normal
credit approval and provider setup workflow when ready to run it. Caption
appearance is selected by `caption_style` in the chosen preset under
`config/presets/`. In `youtube_pro`, `caption_display: auto` intentionally leaves
full captions as sidecars; use `full` when you want burn-in captions.

## Regression checks

A lightweight, isolated test installation is available:

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r requirements-test.txt
python -m pytest -q -rs
```

For full coverage install FFmpeg **and FFprobe**, plus DejaVu Sans fonts. The new
render tests can also use the FFmpeg bundled by `imageio-ffmpeg`; some older
stream-QC tests require system binaries and will explicitly skip without them.
The test-only dependencies do not install the dashboard or local model weights;
use `requirements.txt` for the application.

New checks cover actual H.264/AAC renders with music, ambience, SFX and combined
beds, narration gain, stereo separation, speech ducking, and real libass caption
rendering, in addition to timestamp/layout/validation unit tests. Tests use
synthetic local media, never open signed-in browsers, and never spend generation
credits. GitHub Actions runs the offline suite on Python 3.10 and 3.12.

Technical tests do not replace editorial review, factual verification, media
rights clearance, or checking AI identity/visual continuity before publishing.

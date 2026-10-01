# AutoVideoAI v5.8.6 — music-only reels and readable text cards

## New independent choices

- **Voiceover:** on or off. Off skips TTS, speech transcription, speech retiming
  and spoken-caption generation. It does not generate a voice and then mute it.
- **Text cards:** on or off, even in Pro mode. Off skips intro/chapter/key-point,
  recap/outro and custom structured cards. An explicitly enabled channel watermark
  is a separate branding choice; turn it off too if you want no text whatsoever.
- **Card style:** `auto`, `bold`, `playful`, or `clean`. Auto uses rounded playful
  typography for cartoon stories, bold display headings otherwise.
- **Music:** choose a licensed local file or the existing auto/local/browser
  provider. Music-only mode has no speech-triggered ducking and uses a foreground
  instrumental gain. Ambience and SFX default off without voiceover. Selecting
  silent mode in the dashboard disables all audio.

Speech captions remain separate from decorative text cards when voiceover is on.
They are always disabled when there is no voiceover; unspoken story notes are not
passed off as spoken captions. Old speech files are kept, but not read or burned
in a music-only render. Original dialogue embedded in generated/stock source clips
is not retained by either renderer.

## Dashboard

**STUDIO / CREATE:** select **Audio mode → Music only**, uncheck **Include text
cards**, then choose your music. For cartoon reels, select `reels_pro` and the
`kids_cartoon` theme in Studio. Voice/TTS and speech-caption controls are disabled
when not applicable. The older `cartoon_3d` theme identifier now correctly loads
the cartoon preset rather than falling back to photorealism.

**QUEUE:** select an existing job and expand **Audio & text cards — edit without
regenerating visuals**. Save your options, then click **Render now**. This changes
local presentation settings only; it preserves accepted takes, shot timings,
Flow project bindings and pending request journals. Saving settings does not
submit generation. The local typography preview also makes no provider call.

Do not use Resume merely to restyle a finished video: Resume can generate later
unfinished scenes or prepare missing speech. Turning voiceover back on for a
job that never generated speech requires a narration file first; the render
explains this instead of inventing audio or silently omitting it.

## YAML example — cartoon reel with music, no voice or text

```yaml
topic: A shy rabbit shares a carrot and makes a new friend
production_mode: reels_pro
theme: kids_cartoon
duration: 30
profile: STORYBOARD_ECONOMY
voiceover_enabled: false
text_cards_enabled: false
caption_display: none
background_music: local
background_music_path: assets/music/my-licensed-track.mp3
music_volume: 0.55
sound_effects_enabled: false
ambience_enabled: false
```

Run `python3 cli.py v3 create-config your-reel.yaml`. Relative music paths in YAML
are resolved next to that YAML file. Normal script planning/visual generation
still takes place and the chosen visual providers can spend credits. Disabling
speech only avoids speech-provider work, not visual generation costs.

For a cartoon reel **with** expressive on-screen cards, set
`text_cards_enabled: true` and `text_card_style: playful`.

## CLI — edit a saved video without new visual generation

```bash
python3 cli.py v3 render YOUR_JOB_ID --no-voiceover --no-text-cards \
  --background-music local --background-music-path /path/to/licensed.mp3

# Keep the voice but remove decorative cards AND burned subtitles:
python3 cli.py v3 render YOUR_JOB_ID --no-text-cards --caption-display none

# Restyle the same accepted footage:
python3 cli.py v3 render YOUR_JOB_ID --text-cards --text-card-style playful
```

The same switches are available on `v3 create`. `--no-sound-effects` and
`--no-ambience` are available for explicit control. `--voiceover` re-enables speech;
`--text-cards` re-enables cards. Boolean YAML settings must be real `true`/`false`,
not quoted strings. Music gain must be finite and between 0 and 1.

## What changed in card quality

- Portrait layouts now scale from the **1080px short edge**, not a landscape
  width. Typical full-HD headings start at **88px**, versus approximately 40px
  before; body copy has a readable floor rather than shrinking to tiny text.
- Bundled **Bungee** display lettering and rounded **Fredoka** variable lettering
  work without a separate font installation. The SIL Open Font Licenses are in
  `assets/fonts/`. Clean body text uses a scalable system face with a bundled
  scalable fallback, never Pillow's fixed tiny bitmap font.
- Width/height are measured in pixels, two-line headings are balanced, strokes
  provide contrast over bright footage, and panels fit their content instead
  of blanketing the screen. Full-resolution RGBA overlays preserve the video
  canvas; the master encoder/quality setting is not reduced by enabling cards.
- Small truncated six-row agendas are replaced by one full current idea; recaps
  use timed pages. Automatic cards are scheduled one at a time, with short alpha
  fades. Kids stories do not receive generic like/subscribe/comment outro cards.
- Custom lists/comparisons/charts use larger type, contrast and measured wrapping.
  Overloaded copy raises a clear layout error rather than cropping or hiding
  labels/numbers. Shorten it or split it into timed events.

Cards leave the central action and bottom/right social-UI zones clear in the
standard portrait layout, but cannot certify that every face is unobstructed:
review your actual footage. The bundled display faces target Latin lettering;
review other scripts carefully rather than assuming all glyphs are supported.

## Timing, recovery and review

New non-narrated jobs allocate a gapless visual story clock across approved story
beats and the requested duration. There are no fabricated ASR word timestamps or
placeholder silent narration files. Muting a saved narrated job uses its existing
shot-clock duration rather than stretching it to a different target or replanning
paid media.

A requested music-only edit with no available track stops with an actionable
message. Choose a licensed local track or explicitly choose music off for silence;
the renderer does not quietly export silence instead of requested music.

The FFmpeg and MoviePy compatibility paths both honour voice/cards/caption choices.
Intentionally disabled captions/cards are labelled not applicable in recipe
checks. A deliberately silent film does not fail review for lacking an audio
stream/loudness measurement. Music provenance/rights still need review. Neither
this release nor a successful local render certifies copyright, editorial quality,
virality or the cause of the earlier unidentified live Flow pause.

## Upgrade / download

Back up the current installation and preserve `.env`, settings, outputs, databases,
browser profiles and Flow request journals. Stop the dashboard before overlaying
source; see the v5.8.5 upgrade guide for the saved-job precautions. Do not clear
pending journals or create a replacement job to remove a pause.

The source ZIP includes named bundled fonts and their licenses, but excludes
private settings, media libraries, credentials, profiles, outputs, virtual
environments and older ZIPs. `VERSION` / the dashboard should show **5.8.6**.

Offline verification includes real encoded music-only and silent outputs, actual
Streamlit forms, no-TTS/ASR assertions, saved-journal preservation, fallback
rendering and pixel-measured typography. No live Google generation was used.

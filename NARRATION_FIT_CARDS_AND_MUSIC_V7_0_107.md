# v7.0.107 — Odia fits, cards pop, hooks appear, music ducks

Field report after one three-language job
(`20261022-143856-7-small-daily-habits-tha-9729`, 27 Oct 2026):

> the odia mode get failed for some reason … text cards in the video not good … max meaningful pop-up cards
> feature not visible … hooks missing … the background music does not fade while speaking … recommend
> royalty-free music per video type

Hindi exported, Odia stopped with one line:

```
Odia narration is more than 25% longer than the approved picture. Shorten that language script,
review it, and prepare it again.
```

That line is true and useless: it never said by how much, and the only lever was "slow the picture by up to
25%", so a good Odia script 30% longer than the picture produced no video at all.

---

## 1. A longer narration is now fitted, not refused

`engine/narration_fit.py` makes the decision with numbers instead of a bare gate. Three bounded levers:

| Lever | Default | What happens |
| --- | --- | --- |
| picture | up to **1.25×** | the approved picture is slowed with `setpts`, exactly as before |
| narration | up to **1.12×** | the reviewed narration is sped up with pitch-preserving `atempo` |
| hold (opt-in) | **off** | with `--fit-hold` / `edition_fit_hold_seconds`, the last frame is cloned for the remainder |

Together they absorb a narration up to **1.40×** the picture. Word timings are divided by the same narration
speed, so cards, hooks and burned captions stay on the spoken words. Your Odia case (1.3×) now exports with a
1.25× picture and a 1.04× narration.

Beyond 1.40× the edition still refuses — but the message carries the measurement and every repair:

```
Odia narration is 160.0s but the approved picture is 100.0s (1.60x) - more than 25% longer than the approved
picture, so a video rendered from it would either cut the narration or freeze the picture. Slowing the picture
1.25x and speeding the narration 1.12x absorbs 1.40x, which still leaves 20.0s (about 48 spoken words) over.
Nothing was exported. Fix one of these: shorten that language script by about 48 words and re-approve it; re-run
with `--fit-max-tempo 1.28` to accept a faster narration; or hold the last frame for 20s with `--fit-hold 20`;
or trim the picture.
```

Every edition writes `language_editions/<id>/fit-<language>.json` (the arithmetic) and records the applied fit
in its `.provenance.json` (`narration_fit.picture_scale`, `.tempo`, `.hold_seconds`). The other languages are
untouched: one edition's fit can never change another's.

Change the budget for one job:

```bash
python3 cli.py v3 tune <job_id> --fit-max-tempo 1.15 --fit-hold 10   # persisted in the job's settings.json
python3 cli.py v3 language-outputs <job_id> --fit-max-tempo 1.15 --fit-hold 10   # this run only
```

---

## 2. Cards that look like cards, hooks that actually render

Five separate causes were found; the field job could have hit any of them.

1. **Speech cards were only ever used for "educational" videos.** In `finishing_studio.create_plan` the
   reviewed `speech_cards.json` snapshot was stored only when the edition was educational, so a plain video's
   language editions fell back to thin keypoint strips. Any reviewed card file is now used, whatever the type.
2. **Plain keypoint cards were thin, static lower-third strips.** The "pop-up card" look (panel, badge, open
   and close) only existed for educational content. `render_card_png` now draws keypoint cards too — same
   panel, a `KEY POINT` badge, a soft shadow, a denser panel for readability over bright footage, and
   `anim: pop` with fade in/out, so the renderer animates them.
3. **Editions forced the educational palette.** `_edition_overlays` passed `educational=True` and
   `style='playful'` for every language, changing the kinds and the palette of a non-educational video. It
   now uses that edition's own flag.
4. **Hooks were off by default** and, in editions, only present when the batch was prepared with hooks. New
   jobs now default to `hooks_enabled = True` and `speech_cards_enabled = True` (still one Gemini Web request
   each; untick them in Create to skip). The checkboxes explain this.
5. **Card failures killed the render.** A failed card draft, a stale `speech_cards.json` or a
   `speech_cards.json` that did not exist raised out of the render. All three now fall back to the automatic
   cards, log the reason, and finish the video.

### `production/graphics_audit.json`

Every render writes it:

* what was **requested** (text cards, speech cards, hooks);
* what was **prepared** (cards drafted, series points, hooks drafted);
* what reached the **timeline** (counts by kind);
* **problems** with a code, a cause and a fix — e.g. `text_cards_off`, `no_cards_placed`,
  `speech_cards_missing`, `hooks_not_placed`, `hooks_dropped`;
* **notes** — e.g. *"9 reviewed speech cards were already prepared, but 'Use speech-timed Gemini cards' is
  off, so the automatic keypoint cards were used instead."*;
* `verified_in_video` — see below.

It also appears in the job warnings, in the new **Text cards and hooks · what appeared, and why** panel in the
app, and on the command line:

```bash
python3 cli.py v3 graphics-audit <job_id>            # the stored explanation
python3 cli.py v3 graphics-audit <job_id> --json     # the whole report
python3 cli.py v3 graphics-audit <job_id> --check    # sample the finished video and update the report
```

### "Does the card really appear in the video?"

`--check` (and the button in the panel) grabs the frame in the middle of each card and a control frame a
moment earlier, then compares the pixels **inside that card's own region** (`engine/render/graphic_visibility.py`).
A card that never rendered leaves those pixels identical. At most eight cards are sampled, two half-scale
frames each — a few seconds, no re-encode. The result names each card that could not be found, so "the cards
are missing" becomes a fact with a timecode instead of an impression.

---

## 3. Music that moves with the voice

The bed was technically ducked before, but only by a few dB — the mix sounded like a flat track with speech
over it.

| | before | 7.0.107 |
| --- | --- | --- |
| duck depth under speech | 4:1 at 0.04 threshold ≈ 3–5 dB | **12:1 at 0.02 ≈ 13 dB** |
| attack / release | 120 ms / 400 ms | **15 ms / 550 ms** (returns in every pause) |
| music entry / exit | none — the bed started and stopped dead | **fade in ~1 s, fade out ~2.5 s**, both scaled to the video length |
| sound effects | full planned level | **0.65×**, so they sit under the voice |
| edition loudness | limiter only | **−14 LUFS**, the same target as the English master |

Fades scale with the length: a 4-second clip fades 0.2 s in and does not fade out at all; an 8-minute video
gets the full 2.5 s exit. Every value is a job setting and can be tuned without spending credits:

```bash
python3 cli.py v3 tune <job_id> --show
python3 cli.py v3 tune <job_id> --duck-ratio 16 --duck-release-ms 700 --music-fade-out 4 --sfx-gain 0.5
python3 cli.py v3 render <job_id>        # same accepted takes; no Flow credits
```

---

## 4. Royalty-free music, per video type

See **`docs/MUSIC_LIBRARY.md`**: licence table (YouTube Audio Library, Pixabay, CC BY, CC0), a track list per
video type with the exact credit line, how to import a track into `music_library/`, and a pre-publish
checklist.

```bash
python3 cli.py v3 music-suggest --content-type education
python3 cli.py v3 music-suggest --content-type documentary --theme cinematic
python3 cli.py v3 music-suggest --sources          # where to download, and the terms
python3 cli.py v3 music-check ~/Downloads/track.mp3   # validates the file and prints the manifest entry
```

Catalogue entries are real, checked pages (`engine/audio/music_catalog.py`), starting with the CC0 track this
installation already has. Nothing is downloaded for you; the guide says to re-check each licence page before
publishing, and warns about the Content ID shield on Pixabay tracks.

---

## 5. Install

```bash
# 1. extract AutoVideoAI-v7.0.107...zip beside the existing folder
python3 ../AutoVideoAI-v7.0.107/tools/update_v7106_to_v7107.py .            # dry run
python3 ../AutoVideoAI-v7.0.107/tools/update_v7106_to_v7107.py . --apply    # install
# 2. restart the dashboard
```

Only code and documentation are replaced; outputs, saved jobs, Flow journals, browser profiles and
`music_library/` are never touched. A re-run is safe and does nothing once installed. If the installed version
is older than 7.0.106, the updater refuses and names the earlier update to apply first.

### Re-running the Odia edition you already have

Nothing needs to be re-generated and no Flow credit is spent:

```bash
python3 cli.py v3 language-outputs outputs/<your-job-id> --fit-hold 8
```

`--fit-hold 8` is only needed if that particular Odia script is more than 1.40× the picture; the message tells
you the seconds and the words. If you would rather keep the picture pace identical, shorten the script by the
number of words the message names and re-approve it in Jobs & Recovery → Speech batches.

### If something is still wrong, send these four files

They are small JSON files under `AutoVideoAI-Shared/outputs/<job>/` and they answer the question without a
video upload:

1. `production/graphics_audit.json` — requested vs prepared vs placed, plus the visibility check;
2. `production/speech_cards.json` — the drafted cards (count, text, anchors);
3. `production/hooks.json`, if present — the drafted hooks;
4. `language_editions/<id>/fit-or.json` and the Odia `.provenance.json` — the fit arithmetic that was applied.

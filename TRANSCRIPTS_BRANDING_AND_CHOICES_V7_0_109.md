# AutoVideoAI v7.0.109 — transcripts you can switch off, a brand that stays, and the shots you choose

Five things you asked for, from the two screenshots and the questions around them.

---

## 1. The Odia transcript: switch it off, and fix what it says

**What you saw:** the Odia video burned their own transcript, and the words were right but the spellings
were not.

**Why:** the burned text came from whichever word file the narration produced. A speech recognizer writes its
own guess at a word, and a machine-translated script carries its own spelling, so either could disagree with
the script you approved. Odia speech recognition is the least reliable of the three, which is why it showed up
there first.

**What v7.0.109 does**

* **Odia transcripts are off by default.** Hindi and English keep theirs; Odia renders with its narration,
  cards, hooks, channel badge and logo, and no burned text. Nothing else about the edition changes.
* **Choose per language, after the render.** The three-language panel now has a *Transcript* switch per
  language, and the CLI can set the same thing:

  ```bash
  python3 cli.py v3 language-outputs <job> --transcript-off or      # no Odia transcript
  python3 cli.py v3 language-outputs <job> --transcript-on or       # put it back
  python3 cli.py v3 language-outputs <job> --no-transcript          # none of the editions
  python3 cli.py v3 language-outputs <job> --explain                # what each language currently does
  ```

  Only the languages whose switch changed are re-rendered, from the narration already saved in the job: no new
  voice, no new video, no Flow credits. Every render is a new file, so the version you had stays in its
  `language_editions/<stamp>/exports/` folder — switch back and forth as often as you like.
* **When a transcript is on, its text is the reviewed script.** Caption timing still comes from the measured
  word timings, but every caption word is checked against the script and replaced with the script's spelling;
  unmatched words are interpolated inside the real audio, never invented. The export's provenance records
  `captions_from_reviewed_script` and how many words it corrected.
* **Future jobs store script-accurate words.** Card drafting reads the same word file, so cards stop inheriting
  a recognizer's spelling either.
* **Primary video:** the English master keeps whatever Create chose. To rebuild it locally without captions
  (accepted takes only, no credits): `python3 cli.py v3 render <job> --caption-display none`, and
  `--caption-display auto` to bring it back.

---

## 2. The channel badge from the English video, now in every language

Your first screenshot showed plain white text in the corner; the English video had the panel with the mark and
the play glyph that opens and closes.

* **Language editions draw the same animated badge** as the English master — rounded panel, accent rail, mark,
  and the open/close cycle — with the language's own channel name from its profile.
* **The badge no longer disappears between cycles.** The old plan restarted the mark every 35 seconds but each
  run lasted 30, so there was a five-second hole every time, and with it the only copy of the logo. The mark is
  now contiguous: closed for 0.8 s, open for the rest of each 30 s cycle, covering the whole video.
* **The logo stays for the whole video.** The logo is a separate overlay, bottom-right, with a soft fade-in, in
  both the primary master and every edition — the name may come and go, the logo does not.
* Turning text cards off no longer removes the mark or the logo.

---

## 3. Deleting a job now keeps *every* language video

You asked whether deleting a job keeps a copy of each language video. Until now: **no.** The primary finished
video was moved to `outputs/_render-backups/<job>/`, but the Hindi and Odia editions went with the folder —
the space was freed, and the videos you wanted to publish disappeared with it.

v7.0.109 backs up **all** of them before anything is removed:

```
outputs/_render-backups/<job>/
    <job>-final.mp4
    <job>-branded.mp4
    <job>-hi-edition.mp4
    <job>-or-edition.mp4
    hi-20261027-151159-74e26b32.mp4      (the language_editions/ export)
    or-20261027-173643-f046a5a0.mp4
```

The deletion preview lists them (file, size, destination) before you type the job ID, and if any copy cannot
be verified the deletion is refused and nothing is removed. Restore any of them with
`python3 cli.py v3 backups`.

---

## 4. You choose which shots Gemini generates

The old setting was only a number: *"use Gemini for up to N shots"*, and the first N eligible Flow shots were
silently taken. Now the choice is explicit.

* **In the app:** Storyboard → *Gemini Web video shots · choose which ones*. Every shot is listed with its
  verdict — eligible, already has an accepted take, has a pending Flow request, not a Flow shot — and you pick
  up to four. Saving writes the choice; nothing is submitted or charged.
* **In the CLI:**

  ```bash
  python3 cli.py v3 gemini-shots <job>                     # who is eligible and what is chosen
  python3 cli.py v3 gemini-shots <job> --choose shot_003,shot_007
  python3 cli.py v3 gemini-shots <job> --clear             # back to the first N eligible
  python3 cli.py v3 gemini-shots <job> --json
  ```

* A shot with an accepted take or a Flow request journal is **refused**, with the reason in the message — the
  rule "never resubmit a shot whose request journal exists" still holds. A saved choice that goes stale (its
  take arrived, or a request appeared) is dropped silently at run time rather than re-requested.

---

## 5. Music: start-here links for each video type

Full table, licences and obligations in `docs/MUSIC_LIBRARY.md` (new section 3b). Print it with:

```bash
python3 cli.py v3 music-suggest --playbook
python3 cli.py v3 music-suggest --content-type education --playbook
```

| Type | Start here | Credit? |
|---|---|---|
| Education / explainer | [Mixkit · Inspirational](https://mixkit.co/free-stock-music/tag/inspirational/) · [YouTube Audio Library](https://studio.youtube.com/channel/UC/video_manager/music) · [Buckley · Amberlight](https://www.scottbuckley.com.au/library/amberlight/) | Mixkit no · YT filter · Buckley yes |
| Motivation | [Scott Buckley library](https://www.scottbuckley.com.au/library/) · [Pixabay · inspiring](https://pixabay.com/music/search/inspiring/) | Buckley yes · Pixabay no |
| Documentary | [Buckley · Discovery](https://www.scottbuckley.com.au/library/discovery/) · [Mixkit · Cinematic](https://mixkit.co/free-stock-music/tag/cinematic/) | Buckley yes · Mixkit no |
| Technology / AI | [Mixkit · Technology](https://mixkit.co/free-stock-music/tag/technology/) · [Uppbeat · Electronic](https://uppbeat.io/music/genre/electronic) | Mixkit no · Uppbeat credit code |
| Kids | [Pixabay · kids](https://pixabay.com/music/search/kids/) · [YouTube Audio Library](https://studio.youtube.com/channel/UC/video_manager/music) | No |
| Travel | [Mixkit · Travel](https://mixkit.co/free-stock-music/tag/travel/) · [Pixabay · travel](https://pixabay.com/music/search/travel/) | No |
| Business / finance | [Mixkit · Corporate](https://mixkit.co/free-stock-music/tag/corporate/) · [Bensound · Corporate](https://www.bensound.com/royalty-free-music/tag/corporate) | Mixkit no · Bensound 3-line credit + code |

The short version: **Mixkit** is the least friction (no account, no credit, no cap, not Content ID registered),
**YouTube Audio Library** is the only library YouTube itself guarantees, **Pixabay** needs no credit but some
tracks carry a Content ID shield, and **Scott Buckley** sounds the most expensive but requires the exact credit
line. **Uppbeat** and **Bensound** free tiers give you a per-video code — one video each, every time.

---

## What changed in the code

| File | Change |
|---|---|
| `engine/language_editions.py` | `transcript_settings` / `transcript_for` / `set_transcript` / `transcript_plan`; the render record stores what each edition burned, so a changed switch re-renders only that language; Odia defaults to no transcript |
| `engine/finishing_studio.py` | captions come from the reviewed script; caption correction recorded in provenance; the edition draws the animated channel badge from contiguous segments and keeps the logo for the whole video; plan records `branding_badge` |
| `engine/captions.py` | `script_accurate_words()` — reviewed script for text, measured timings for cues |
| `engine/speech_cards.py` | saved narration words are aligned to the reviewed script when a batch is prepared |
| `engine/render/graphics.py` | `watermark_segments()` (no gaps), persistent `logo` overlay kind, logo kept when cards are off |
| `engine/providers/gemini_video.py` | `gemini_shot_plan()` / `choose_shots()`, eligibility with reasons, stale choices dropped |
| `engine/job_delete.py` | every language video and the branded master are backed up before a job is deleted |
| `engine/graphics_audit.py` | the persistent logo is not counted as a text card |
| `cli.py` | `--transcript / --no-transcript / --transcript-off / --transcript-on`, new `v3 gemini-shots`, `v3 music-suggest --playbook` |
| `app.py` | per-language transcript switches in the three-language panel; Gemini shot picker in Storyboard |

## Tests

`tests/test_v7109_transcript_branding_gemini.py` — **21 tests**, including two real FFmpeg renders:

* a Hindi edition renders with its transcript, renders again without one, then again with it: three separate
  files, the earlier ones still on disk, provenance matching each;
* the badge spans its window with no gaps and the logo is visibly present at 6.5 s, inside what used to be the
  five-second hole;
* caption words are corrected to the reviewed script while measured word times are kept;
* a transcript switch saved alone touches no media and renders nothing;
* Gemini choices are saved, refused with reasons, dropped when stale, and never submit anything;
* deleting a job keeps all four kinds of video.

Card, hook, branding, fit, edition and backup suites re-run clean (**105 + 24 + 54 passing** across the
targeted files).

> Sandbox note: the edition render tests need FFmpeg with libass, plus `uharfbuzz` and `freetype-py` for the
> Devanagari/Odia shaping. Without them the render step fails on the missing module — an environment problem,
> not a card problem.

## Install

1. Extract `AutoVideoAI-v7.0.109-Transcripts-Branding-And-Choices.zip` beside your installation.
2. Stop the dashboard.
3. From your installation folder:

```bash
python3 ../AutoVideoAI-v7.0.109/tools/update_v7108_to_v7109.py .            # dry run
python3 ../AutoVideoAI-v7.0.109/tools/update_v7108_to_v7109.py . --apply    # install
```

Only code, docs and tests are replaced. Outputs, saved jobs, Flow journals, browser profiles and
`music_library/` are untouched; previous code files are kept under `code-update-backups/`.

## Do this next, for your job

```bash
python3 cli.py v3 language-outputs outputs/20261022-143856-7-small-daily-habits-tha-9729 --explain
python3 cli.py v3 language-outputs outputs/20261022-143856-7-small-daily-habits-tha-9729 --fit-hold 8
```

Odia will render without its transcript (its default now), with the animated badge and the logo for the whole
video. If you want the Odia transcript back later, render again with `--transcript-on or` — that version is
built from the reviewed script, and the version you already had stays on disk.

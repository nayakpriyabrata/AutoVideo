# AutoVideoAI v7.0.110 — Fix the transcript text, and pick Gemini's shots in the app

Two things you asked for after v7.0.109. Neither of them records anything or spends Flow credits.

* **You can see the transcript, fix a spelling, and burn the fixed text** — for one language at a time, without
  re-recording the voice.
* **The Gemini shot picker is in the app**, not only on the command line.

---

## 1. The transcript, in your own words

The v7.0.109 screenshot showed Odia captions where the *words* were right and the *spellings* were not. v7.0.109
answered that by taking the caption text from the reviewed script and by switching Odia transcripts off by
default. That is a good default, and it is still the default. It is not the same as letting you fix the word
that is wrong.

v7.0.110 adds the third route.

### What you see

In the job panel (**Queue**, **Create**, or **Storyboard**), open
**Languages and editions → Fix the transcript text (optional · the narration is never re-recorded)**.

1. Pick the language. Only languages whose narration has already been measured are offered, because those are
   the only ones with word timings to show.
2. The editor lists the transcript **as captions**, in the same 6-word lines the video shows, with the start
   time of each line. Edit the text in place.
3. **Save corrected text** stores the correction for that language only.
4. **Render language editions** (or “Render all languages”) then burns the corrected text. **Only that language is
   re-rendered**; Hindi and English keep their existing files, and the earlier export of the corrected language
   stays on disk as well.

The same thing on the command line, for a long transcript or a scripted fix:

```bash
python3 cli.py v3 transcript outputs/<job> --show                 # read it
python3 cli.py v3 transcript outputs/<job> --export or.txt        # a plain text file to edit anywhere
python3 cli.py v3 transcript outputs/<job> --apply or.txt         # save the corrected text
python3 cli.py v3 transcript outputs/<job> --set-word 12=ସ୍ୱାସ୍ଥ୍ୟ   # one word, by index
python3 cli.py v3 transcript outputs/<job> --clear                # drop the correction
python3 cli.py v3 transcript outputs/<job> --script               # same thing, named for the reviewed script
python3 cli.py v3 transcript outputs/<job> --render               # render that language with the correction
```

`--language` defaults to the extra language when the job has exactly one; pass `--language hi` or `or`
otherwise. `outputs/<id>` paths and trailing slashes are accepted, as everywhere else.

### What a correction does and does not change

| | |
|---|---|
| The narration file | **unchanged** — byte for byte, never re-recorded, no text-to-speech |
| The measured word times | **kept exactly**, as long as the word count stays the same |
| The word count changes (a word split or merged) | accepted, but the timings are **re-estimated** and the editor says so before you render |
| Text cards and hooks | unchanged — they keep the timings they were drafted from, so a spelling fix cannot move a card |
| Flow credits | **none** — no video is requested |
| Other languages | untouched; their exports are not re-rendered |
| The version you already had | kept on disk next to the new one |

A correction lives in `production/transcripts/<language>.json` (`"schema": "transcript-edit-v1"`), and the
renderer copies it into the plan's `assets/` before burning, so a later edit cannot change a render that is
already running. Its checksum is part of the “is this export current?” test, which is why exactly one spelling
fix re-renders exactly one language.

### The three routes, side by side

| Route | What the captions say | What it costs | When to use it |
|---|---|---|---|
| **Leave it off** (default for Odia) | nothing burned | nothing | the fastest, safest answer to today's bad spelling |
| **Use the reviewed script** | the script's words, at the measured times | nothing | the script is already right and only the recogniser was wrong |
| **Fix the spellings** | exactly what you typed | nothing | you want the transcript, and you want it right |

Nothing here is mandatory. If you never open the editor, the job behaves exactly as it did in 7.0.109.

### When a correction is refused

Every message names the word and the file, and says nothing was changed:

* “Word 4 (ଧ୍ୟାନ) ends before it starts (1.85s → 1.40s). Fix its timing and save again; nothing was changed.”
* “Word 3 (…) starts before the word before it ends. Keep the words in order and save again; nothing was
  changed.”
* “An empty transcript cannot be saved; nothing was changed. Use `--clear` to remove a correction and go back to
  the measured words.”

---

## 2. Gemini's shots are chosen in the app

v7.0.109 added the choice, but only `cli.py v3 gemini-shots` could change it, and Create still only asked for a
number — which silently took the first eligible shots. Now:

* **Create** still asks for the cap (“Use Gemini Web for up to this many AI video shots”), and now says where the
  shots are chosen once the storyboard exists.
* The job panel (**Queue** and **Create**), and **Storyboard**, show
  **Gemini Web video shots · shot_003 · 2 eligible**: a multiselect of exactly the shots Gemini may take (maximum
  four), a table of **every** shot with its verdict and its reason, and **Save Gemini choice** / **Clear the
  choice**.
* Reasons are stated, never implied: *eligible* · *not a Flow shot* · *already has an accepted take* · *a Flow
  request journal exists (never resubmitted)*.

Saving a choice submits **nothing** — an empty journal, no request, no credit. A shot with an accepted take or an
existing Flow request is never offered, so it cannot be generated twice. Opening the panel is free.

```bash
python3 cli.py v3 gemini-shots outputs/<job> --show                 # the plan and every verdict
python3 cli.py v3 gemini-shots outputs/<job> --choose shot_003,shot_007
```

---

## Updating

Stop the dashboard, extract this zip **beside** your installation, then:

```bash
python3 ../AutoVideoAI-v7.0.110/tools/update_v7109_to_v7110.py /path/to/AutoVideoAI-v7.0.109         # dry run
python3 ../AutoVideoAI-v7.0.110/tools/update_v7109_to_v7110.py /path/to/AutoVideoAI-v7.0.109 --apply
```

The updater replaces code, docs and tests only. Your `outputs/`, saved jobs, Flow journals, browser profiles and
`music_library/` are never touched, and a file you edited yourself is preserved instead of overwritten (the run
stops and names it). It refuses an installation older than 7.0.109 and tells you which earlier update to apply
first. Code backups go to `code-update-backups/v7.0.109-to-v7.0.110-<stamp>/`, and a second run says “already up
to date”.

---

## Verification

New tests: `tests/test_v7110_transcript_edit.py` (17) and `tests/test_v7110_gemini_picker_ui.py` (8).

* the editor shows exactly the words that would be burned, with their times;
* fixing a spelling keeps every measured time and writes **only** `production/transcripts/<language>.json`;
* a changed word count is accepted and reported as `estimated`;
* empty, reversed and out-of-order corrections are refused with the word index named, and nothing is written;
* the correction is what FFmpeg burns — the plan's `assets/captions-<code>.json` snapshot holds the corrected
  word, the provenance records `captions_from_correction: true`, and the previous export stays on disk;
* a second render with nothing changed produces no new file; a new correction re-renders that language;
* the picker is one shared function, reachable from the Queue panel, the Create pipeline view and Storyboard, and
  saving a choice is described as submitting nothing.

The full suite is unchanged against a pristine 7.0.109 tree: **44 failed / 1 762 passed / 5 skipped** on this
build and the same 44 pre-existing, environment-caused failures on 7.0.109 (identical failure lists).

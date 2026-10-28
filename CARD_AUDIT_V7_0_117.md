# AutoVideoAI v7.0.117 — ask before you spend the render

Your Odia render finished, and the transcript fix is confirmed in the field:

```
"captions": false, "caption_source": "measured",
"captions_detected": { "looks_like_text": false,
  "detail": "caption band: 6.13% bright / 0.82% edges … — no burned transcript detected." }
Odia: captions: no · picture check: no text
```

But that file was made by **7.0.115**, not 7.0.116. The proof is in its own record: the card audit that 7.0.116 writes
(`cards_on_screen_at_once`) is not there, and neither is the warning it would have added. So this Odia video still has
the old overlapping cards, and nothing in the app told you — a missing record looked exactly like "checked, fine".

That is what this release fixes, without asking you to spend another two hours to find out.

## `--card-audit` — the answer in seconds, before any render

```
python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --card-audit
```

It reads only. No encoding, no voice, no Flow credit, nothing written into the job. For every selected language it
lists both card sources, every pair that would share the screen with the overlap in seconds, and exactly what a render
will do:

```
Odia (or)
  job cards: 1 · edition cards: 1 · drawn by a render: 1
  Odia: the same card is scheduled twice for the same moment (once by the job card copy, once by the
  edition card file, 2.1s apart). A render draws it once.
  - not drawn twice: "ଅଭ୍ୟାସ ୧: କହିବା" is already drawn once (2.1s of overlap)
  current file: …/or-20261028-175252-4d686981.mp4 (rendered before 7.0.116 - its card overlap is not recorded)

A render of the languages above draws one card at a time and skips the overlaps. It reuses the saved narration
and the approved picture - no new voice, no Flow credits:
    python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --fit-hold 8
```

If a language has nothing to fix, it says so plainly — *"3 cards, no two share the screen. A render draws all of
them."* — and no render command is suggested. `--json` gives the same data machine-readable.

## The listing stops being silent

`--files` now states the card state of each current file instead of omitting it:

```
  cards: one at a time · 1 overlapping or duplicate card(s) were not drawn      ← rendered by 7.0.116+
  cards: one at a time (recorded)                                              ← 7.0.116+, nothing dropped
  cards: not recorded - this file was rendered before 7.0.116, so whether two cards share the screen is
  unknown. `--card-audit` says whether this job needs a new render.             ← your current Odia file
```

and the one-line summary ends with `cards: one at a time` or `cards: not recorded`, so the difference is visible at a
glance.

---

## What this means for your Odia video

Nothing here changes a file. The sequence that costs you least:

```
python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --card-audit
```

* **it reports overlaps** (as in the example above) → render that language once more; the new file draws one card at a
  time and the older file is kept;
* **it reports no overlaps** → this job is already fine, keep the file you have and skip the render entirely.

Either way you will know before the machine spends an hour on it.

---

## Updating

Stop the dashboard, extract this zip **beside** your installation, then:

```bash
python3 ../AutoVideoAI-v7.0.117/tools/update_v7116_to_v7117.py /path/to/AutoVideoAI-v7.0.116         # dry run
python3 ../AutoVideoAI-v7.0.117/tools/update_v7116_to_v7117.py /path/to/AutoVideoAI-v7.0.116 --apply
```

Code, docs and tests only. `outputs/`, saved jobs, Flow journals, browser profiles and `music_library/` are never
touched; a file you edited yourself is preserved and the run stops and names it. It refuses anything older than
7.0.116. Code backups go to `code-update-backups/v7.0.116-to-v7.0.117-<stamp>/`.

---

## Verification

New tests: `tests/test_v7117_card_audit.py` (**7**), real FFmpeg renders where they matter.

* the audit finds the two-card collision before any render — one job card, one edition card, one pair, the overlap in
  seconds, what a render draws and what it skips;
* **the audit is read-only**: every file in the job, with its size, is identical before and after it runs;
* a language with only one card source has nothing to fix and says so; a language with no cards says that; a missing
  drafted card file is a note, not an error;
* the audit reports whether the current file was rendered with the rule, and after a 7.0.116+ render it does;
* the listing says `cards: not recorded - this file was rendered before 7.0.116` for a pre-7.0.116 record and
  `cards: one at a time` when the file carries it, in both the summary line and the full listing.

The updater also gained a guard this release needed: if a different file already sits where a *new* file of this
update goes (`engine/card_audit.py`), it stops and names it instead of overwriting it — the same promise it already
made for a file you had edited.

Full suite in this environment: **55 failed / 1 824 passed / 4 skipped** (+4 collection errors), against a pristine
7.0.116 tree failing the **identical** 55 tests and 4 errors (this sandbox's FFmpeg lacks `subtitles`/`drawtext`, so
the caption and clip-editing suites cannot run here). No regressions; 7 new tests.

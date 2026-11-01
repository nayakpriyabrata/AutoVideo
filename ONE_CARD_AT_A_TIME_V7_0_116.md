# AutoVideoAI v7.0.116 — one card on screen at a time

Your screenshot showed it exactly: one Odia frame carrying **two** pop-up cards, the bold KEY POINT panel in front and
a second panel of the same shape behind it, a fraction of a second out of step, holding the rest of the sentence.

The transcript fix is holding — that is a separate, older bug and this frame confirms it is gone. This one was in the
cards.

## Why two cards were drawn

Both panels were real, and both were drawn by the *same* render, from two different lists:

* **the job's copied cards** — `bundle['cards']`, written by the original English card pass and stored on each
  language's narration. `render()` draws each of these as a full-frame image in its own loop;
* **the edition's own cards** — `production/speech_cards.json`, drafted for this language from its own reviewed
  narration (`speech_cards.render()`), drawn in a second loop.

Both are anchored to the same spoken sentence, so as soon as their windows differ by a few tenths of a second they
land on the same pixels. Nothing compared the two lists: hooks were checked against cards, copied cards were not.

Reproduced on 7.0.115 with an Odia narration before touching anything (the two panels below are one frame, 1.2 s in;
the second panel is the copied job card, and it carries the whole sentence):

```
copied job card:  0.4 → 2.40s   ଅଭ୍ୟାସ ୧: କହିବା
edition card:     0.4 → 2.55s   ଅଭ୍ୟାସ ୧: କହିବା
```

## What 7.0.116 does

New module `engine/render/card_slots.py` decides what may be drawn, before anything is encoded:

1. **One card at a time.** Two cards may not share the screen, from either list. Cards keep a 0.15 s beat between them,
   which is longer than the 0.22 s fades they open and close with, so one card never fades through another.
2. **The edition's own card wins** when they collide — it was drafted for this narration, in this language, with this
   card style — and a *duplicate* of the same text is drawn once rather than twice.
3. **Hooks are untouched.** They are small pills in their own band; the rule only governs cards.
4. **Nothing is deleted.** Your saved cards, the copied ones and the drafted ones, stay exactly as they are; the
   render simply does not draw the second one.

The render records what it did: `graphics-<lang>.json` and the export's provenance now carry
`cards_on_screen_at_once` (1) and, when something gave way, `cards_overlap_removed` with the text, the window, the
card that kept the screen and the overlap in seconds. The job warns in plain words and the file listing shows:

```
  cards: one at a time · 1 overlapping or duplicate card(s) were not drawn
```

Nothing is re-recorded, no Flow credit is spent, and no new video request is opened. Your saved cards are not
rewritten, so if you ever want the other card to win, that is a one-line rule change, not a re-draft.

---

## What to do

Update, then render the Odia edition once more:

```
python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --fit-hold 8
```

Only languages that are not current are rendered, from their saved narration and the approved picture. The earlier
files are kept. The new Odia file should show one card at a time; if any card was dropped as a duplicate, the job
panel says which one, and the listing repeats it.

---

## Updating

Stop the dashboard, extract this zip **beside** your installation, then:

```bash
python3 ../AutoVideoAI-v7.0.116/tools/update_v7115_to_v7116.py /path/to/AutoVideoAI-v7.0.115         # dry run
python3 ../AutoVideoAI-v7.0.116/tools/update_v7115_to_v7116.py /path/to/AutoVideoAI-v7.0.115 --apply
```

Code, docs and tests only. `outputs/`, saved jobs, Flow journals, browser profiles and `music_library/` are never
touched; a file you edited yourself is preserved and the run stops and names it. It refuses anything older than
7.0.115. Code backups go to `code-update-backups/v7.0.115-to-v7.0.116-<stamp>/`.

---

## Verification

New tests: `tests/test_v7116_one_card_at_a_time.py` (**11**), with real FFmpeg renders.

* the rule on its own: a second card is dropped while the first is showing; a 0.15 s beat is enforced; the edition's
  own card beats the copied one; the same text twice is drawn once and explained that way; `conflicts()` reports what
  shared the screen; hooks and cards are told apart; a points series and a single card cannot coexist;
* a real edition render draws exactly one card and records `cards_on_screen_at_once: 1` plus the dropped card's text
  and overlap in `graphics-or.json` **and** in the export's provenance;
* **the picture check**: the same edition rendered with and without the copied job cards produces frames that differ
  by a mean of under 2/255 per channel at 1.2 s — the extra panel is gone, not dimmed;
* the job record, the panel warning and the listing all say which card gave way, so the change is not silent;
* an edition with no drafted card file still draws its copied cards — the rule never removes the only cards a
  language has.

Full suite in this environment: **55 failed / 1 817 passed / 4 skipped** (plus 4 collection errors), against a
pristine 7.0.115 tree failing the **identical** 55 tests and 4 errors (this sandbox's FFmpeg lacks
`subtitles`/`drawtext`, so the caption and clip-editing suites cannot run here). No regressions; 11 new tests.

The before/after frames from the reproduction are `before-116.png` (two panels) and `after-116.png` (one panel).

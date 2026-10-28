# AutoVideoAI v7.0.112 — the card off the face, the same card in every language, and proof in the picture

Two reports. One about where a text card sits and how it looks, one about an Odia transcript that would not go
away. Neither fix renders anything by itself or spends a credit.

---

## 1. The card: below the face, above the captions, the same in all three languages

**What you saw:** the English card sat over the presenter's face. The Hindi and Odia cards sat lower, in a plain
navy panel with white text — and the English one looked better.

**Why:** they were drawn by two different code paths.

| | English master | Hindi / Odia editions |
|---|---|---|
| Position | 12 % of the height — a **top** card, over the face | 72 % — a bottom strip |
| Panel | playful palette, accent rail, rounded panel | hand-rolled navy rectangle |
| Text | the job's card style, stroke, fit | one font size, white, thin stroke |

### One band for every card

`engine/render/card_band.py` is now the only place a card's position is decided:

* it starts at **40 %** of the height in a 16:9 frame, **44 %** in 9:16 — below the head and shoulders of a
  portrait shot, which is where your face is;
* it ends where the caption style's own numbers say the top caption line begins, less a 2 % gap — so a card can
  never sit on the transcript;
* the card is **centred** in that band, which is the "middle, not on the person's face" you asked for;
* with no transcript burned, the band ends above the channel logo instead.

Same numbers in `graphics.py` (English master, keypoint/chapter/intro/outro cards), `educational_cards.py` (the
speech-timed pop-up cards) and `finishing_studio._card_image` (the editions).

### One card style for every language

The editions drew a hard-coded `bold` style while the English master used the job's actual style. Now:

* `create_plan()` records the **job's** style (from the saved language state, else the production's own
  `publish_readiness.json`, where `text_card_style` is the resolved style the primary render drew) and gives it to
  every edition;
* `_card_image` hands the card to the shared `render_overlay_png` with that style — the same panel, accent rail,
  typography and stroke as English;
* an edition with an explicitly saved `card_style` keeps it, and an educational edition stays `playful`.

Where the card lands, measured on a 1920×1080 frame:

```
old English keypoint card    y 571 → 856   (53 % → 79 %)   over the face
old edition strip            y ~700 → 780  (65 % → 72 %)   different look
now, every language          y 432 → 730   (40 % → 68 %)   below the face, above the captions
```

---

## 2. The transcript: now the picture is checked, not just the record

v7.0.111 named the current file and stopped a stale plan from re-burning captions. What it could not do was look
at the video. So v7.0.112 adds the witness that cannot agree with a plan by accident.

* **Every render samples the finished picture** — five moments — and records what it sees in
  `production/language_editions_render.json` under `captions_detected`: how much of the caption band is
  glyph-bright, how much sharp local contrast it carries, and a sentence with the numbers.
* The test is **two measurements**, not one: bright alone counts a bright sky or a colour bar; bright *and* edged
  is thin text with a dark outline. On the field videos: **1.5 % bright / 6.4 % edges** with the transcript,
  **16.6 % bright / 1.5 % edges** for a colour-bar picture — called correctly, and the earlier one-number rule
  called the colour bars text.
* `python3 cli.py v3 language-outputs <job> --files --check-captions` prints it for the current file:

  ```
  Odia (or)
    watch: …/render/<job>-or-edition.mp4
    export: …/language_editions/20261028-…/exports/or-20261028-….mp4
    burned captions: no (provenance) · 2026-10-28 02:28 · sha 741e80864a4f
    picture check: caption band: 0.00% bright / 0.96% edges at 0.9s, … — no burned transcript detected.
    earlier file (NOT current): … · burned captions: yes
  ```

  It warns, with the numbers, when the *current* file shows text while the job asks for none. It never warns in
  the other direction: a caption is not on screen every second, so finding nothing proves nothing.
* **The panel now plays the uniquely named export**, not the stable `render/<job>-or-edition.mp4` copy. A browser
  or a player can keep yesterday's file under that stable name and show it as today's; the export name changes
  with every render. The copy is still there — labelled "same file, stable name, for playing outside the app".

If a render is reported as current and the picture check says it shows no burned transcript, that file really has
none: play that exact path.

---

## Updating

Stop the dashboard, extract this zip **beside** your installation, then:

```bash
python3 ../AutoVideoAI-v7.0.112/tools/update_v7111_to_v7112.py /path/to/AutoVideoAI-v7.0.111         # dry run
python3 ../AutoVideoAI-v7.0.112/tools/update_v7111_to_v7112.py /path/to/AutoVideoAI-v7.0.111 --apply
```

Code, docs and tests only. `outputs/`, saved jobs, Flow journals, browser profiles and `music_library/` are never
touched; a file you edited yourself is preserved and the run stops and names it. It refuses an installation older
than 7.0.111 and says which earlier update to apply first. Code backups go to
`code-update-backups/v7.0.111-to-v7.0.112-<stamp>/`; a second run says "already up to date".

Already at 7.0.109? Apply 7.0.110, then 7.0.111, then this one.

---

## Verification

New tests: `tests/test_v7112_card_band_and_picture_check.py` (**21**).

* a card never starts in the face zone and never reaches the burned captions, at four frame sizes;
* the band is centred, not a strip at the top, and a short frame still gets a usable one;
* **the English card and an edition card are pixel-identical** (same bounding box) in two aspect ratios and two
  styles — the "make Odia look like English" request, measured;
* the edition takes the job's style, and an unknown saved style is ignored rather than propagated;
* the picture check sees a burned caption and does not see a plain frame; a missing file is reported, not guessed;
* a real render records `captions_detected` in the edition record and in the panel listing, and a job that asked
  for no transcript is warned about only when text is visible.

One existing test changed with its reason stated in place: `test_lower_cards_leave_head_area_and_caption_margin`
asserted cards start at or below 50 % of the height. A two-line card is taller than the room between 50 % and the
caption line at 70 %, so that rule pushed the panel onto the captions — or, at the old 12 %, onto the face. It now
asserts what the request actually needs: below the head, above the captions.

Full suite: **28 failed / 1 812 passed / 4 skipped**, against a pristine 7.0.111 tree failing the same set minus
the ten card-position tests this change fixes. No new failures.

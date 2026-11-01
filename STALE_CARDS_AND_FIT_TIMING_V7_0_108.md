# AutoVideoAI v7.0.108 — the Odia edition that died after its own retiming

## What you hit

Your three-language job `20261022-143856-7-small-daily-habits-tha-9729` produced the English export and the
Hindi edition, then the Odia edition stopped with:

```
Narration or timings changed after card drafting. Press Resume to refresh speech cards.
```

The narration was fine. Nothing about the script had changed. The message was the app arguing with itself.

## What was actually wrong

1. **Cards were resolved from a file the app had just rewritten.** When a reviewed narration is longer than
   the picture, 7.0.107 retimes it: the picture is slowed (up to 1.25x), the narration is sped up with pitch
   preserved (up to 1.12x), and the word timings are rescaled into `words-fitted.json`. The card renderer was
   handed that rescaled copy **after** the fit, and it fingerprints the narration plus the word timings. Its own
   retimed copy could never match the draft, so it raised "narration or timings changed" — with the review
   script untouched.
2. **It failed late and unhelpfully.** The card step ran after the picture retiming and after minutes of
   encoding, and the one-line message named neither the file, the numbers, nor a way out.

## What 7.0.108 does

**Cards and hooks are resolved before the picture is touched.** They are anchored to the reviewed narration and
its own word timings — the exact inputs their draft fingerprint was made from — then the placed overlays are
retimed by the narration speed. A fitted narration can no longer invalidate its own cards, and a genuinely
stale card file now fails in seconds instead of after an encode.

* `engine/finishing_studio.py` — new `_retime_overlays()` scales card/hook start and end times by `1 / tempo`.
  The `speech_cards` / hooks / educational block moved **above** the picture retiming, and it is fed the
  reviewed words plus the narration's original duration.
  `graphics-<lang>.json` now records `narration_tempo` next to the card kinds, so a later audit can see the
  cards were retimed, and by how much.

**When a card file really is stale, the message is now a repair recipe.** Example from the same job (counts
illustrative), naming the file and the part that changed (narration audio / word timings / reviewed script / video type), the saved draft's word and character
counts against this edition's, and two paste-ready commands:

```
Speech cards in outputs/20261022-143856-.../speech-editions/or/.../production/speech_cards.json were drafted
from a different narration: the reviewed script changed since the draft. Saved draft: 431 words, 2612 script
characters; this edition: 512 words, 3005 script characters. Nothing was rendered with stale timings.
Repair in one step - no new TTS, no new video, no Flow credits:
`python3 cli.py v3 refresh-cards 20261022-143856-7-small-daily-habits-tha-9729 --language or`
(one Gemini Web request per language), then run
python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --fit-hold 8.
```

**New command: `v3 refresh-cards`.** It re-drafts cards (and hooks, when the job uses them) from the narrations
that are already saved in the job: one Gemini Web request per language, no text-to-speech, no video request, no
Flow credit. It rewrites each language bundle, keeps the source-language cards in the job root, and prints the
render command to run next.

```bash
python3 cli.py v3 refresh-cards <job>                       # every prepared language
python3 cli.py v3 refresh-cards <job> --language or          # just the Odia edition
python3 cli.py v3 refresh-cards <job> --language or --cleanup keep   # leave the chat open to read
```

**Failure text is no longer cut off.** Edition failures were truncated to 300 characters in the panel and 800
in the record, which cut these instructions in half. They are kept whole now (900 in the panel, 1500 in
`production/language_editions_render.json`), and the record on disk always has the full wording.

## Proof, not promises

`tests/test_v768_language_editions_render.py` renders real Hindi and Odia editions with FFmpeg, including the
exact failure shape from your job: a 4.2 s Hindi narration on a 3.0 s picture.

* the stretched picture (1.25x) and the sped narration (1.12x) meet at 3.75 s, and the export is 3.75 s;
* the Hindi edition still carries the Hindi voice (660 Hz) and Odia the Odia voice (880 Hz);
* the picture is slowed only inside the fit budget, and the other languages are untouched;
* a genuine 4.9 s overrun is still refused — with `4.9s`, `3.0s`, `1.65x`, the words to cut and the flags.

`tests/test_v7108_stale_cards_and_fit.py` covers the retiming arithmetic, the pre-encode ordering, the stale
message, and that a stale file never reaches the encoder. The card/hook/fit suites total **129 passing tests**,
with the edition render suite at **11 passing**.

> The edition tests need `uharfbuzz` and `freetype-py` (Hindi/Odia shaping) plus FFmpeg. In a bare sandbox
> without them the render step fails on the missing module, which is an environment problem, not a card
> problem. `pip install uharfbuzz freetype-py` before judging those tests.

## Install

1. Extract `AutoVideoAI-v7.0.108-Stale-Cards-And-Fit-Timing.zip` **beside** your installation.
2. Stop the dashboard.
3. From your installation folder:

```bash
python3 ../AutoVideoAI-v7.0.108/tools/update_v7107_to_v7108.py .            # dry run
python3 ../AutoVideoAI-v7.0.108/tools/update_v7107_to_v7108.py . --apply    # install
```

Only code and documentation are replaced. Outputs, saved jobs, Flow journals, browser profiles and
`music_library/` are untouched, and the previous code files are backed up under `code-update-backups/`.

## Do this next, for your job

```bash
python3 cli.py v3 language-outputs outputs/20261022-143856-7-small-daily-habits-tha-9729 --fit-hold 8
```

The Odia edition should now finish with the English and Hindi ones. If a card file turns out to be genuinely
stale, the new message will name it and give you the `refresh-cards` command above — no re-recording, no
re-rendering from scratch, no Flow credits.

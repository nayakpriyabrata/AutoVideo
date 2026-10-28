# AutoVideoAI v7.0.113 — the transcript that came back, and the line that caused it

Your 7.0.112 picture check settled it, and it settled it against me: the current Odia export **does** carry burned
captions, although the job asks for none.

```
Odia (or)
  burned captions: yes (provenance, from the reviewed script)
  picture check: 10.14% bright / 7.69% edges … — consistent with a burned transcript.
```

So my earlier "the render was right, you were watching the old file" was wrong. The file you watched was the right
file, and it was wrong. This release fixes the cause, repairs the job, and says what happened.

---

## The cause: one line in the narration-fit step

When a narration is longer than the picture, the render fits it — the picture is slowed, the voice is sped up with
pitch preserved, and (with `--fit-hold`) the last frame may be held. Fitting also re-times the word file, because
cards and captions are anchored to the narration.

The render decides whether to burn a transcript at the top:

```python
words_path = _verified(edition['words']) if edition.get('words') and plan.get('captions') else None
```

`None` means "no transcript for this language". Then, fifteen lines lower, the fit step did this:

```python
words_for_render.write_text(json.dumps(scaled, …))
words_path = words_for_render        # ← captions switched back on, whatever the plan said
```

So a language whose transcript was switched **off** got its captions back as soon as its narration had to be fitted.
That is why Odia (whose narration is the longest) had them and the job's record still said `captions: false` — the
record was right about the *request* and the file was right about what the *renderer* did. It is why the old
"re-render with the transcript off" instruction changed nothing: every re-render hit the same line. And it has been
there since 7.0.107, when fitting landed, so any fitted language was affected.

Reproduced on the 7.0.112 tree before changing anything, with a 7.8 s Odia narration on a 6 s picture:

```
status: exported | plan captions: False
provenance captions_burned: True | from_reviewed_script: True
picture check: 15.13% bright / 4.20% edges — consistent with a burned transcript
```

## The fix

1. **The fit step only decides about timing.** `words_path` is handed to the caption stage only if captions were
   asked for in the first place:

   ```python
   if words_path is not None:          # the plan asked for captions
       words_path = words_for_render
   ```

   The same reproduction after the change: `captions_burned: False`, picture check **1.34 % edges** — not text.
   The control still works: a fitted edition that *does* ask for its transcript gets it.

2. **A plain render repairs your job.** A language whose current export shows a transcript while the job asks for
   none is now treated as out of date and rendered again — that language only, from its saved narration, no new
   voice, no Flow credit. The earlier file stays where it is and is marked `superseded.json`.

3. **No repair loop.** If a freshly rendered file still disagrees (a pathological source, say), it is kept, marked
   `captions_disputed`, and explained — it will not be rendered again automatically.

4. **The message names the cause** instead of asking you to re-check the switch you had already checked.

## What to do with your job

```
python3 cli.py v3 language-outputs outputs/20261022-143856-7-small-daily-habits-tha-9729 --files --check-captions
```

On 7.0.113 that lists the problem **and** prints the exact render command beneath it:

```
    python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --fit-hold 8
```

Run it once. Odia is rendered again without captions (Hindi and English are untouched, because they already agree
with what the job asks), the new `or-<stamp>.mp4` is the current one, and the previous one is kept as the earlier
version with a `superseded.json` beside it. No new voice, no Flow credit.

Afterwards the listing should read `burned captions: no` and `no burned transcript detected` for Odia.

---

## Updating

Stop the dashboard, extract this zip **beside** your installation, then:

```bash
python3 ../AutoVideoAI-v7.0.113/tools/update_v7112_to_v7113.py /path/to/AutoVideoAI-v7.0.112         # dry run
python3 ../AutoVideoAI-v7.0.113/tools/update_v7112_to_v7113.py /path/to/AutoVideoAI-v7.0.112 --apply
```

Code, docs and tests only. `outputs/`, saved jobs, Flow journals, browser profiles and `music_library/` are never
touched; a file you edited yourself is preserved and the run stops and names it. It refuses an installation older
than 7.0.112. Code backups go to `code-update-backups/v7.0.112-to-v7.0.113-<stamp>/`.

Small housekeeping: the 7.0.112 updater's own description still opened with "v7.0.111"; the update behaved
correctly, and the wording is corrected here.

---

## Verification

New tests: `tests/test_v7113_fit_captions_repair.py` (**7**), all with real FFmpeg renders.

* a fitted edition with its transcript off burns no captions — provenance, record and picture all agree — while the
  fitting itself still happened (`narration_fitted_picture: true`);
* a fitted edition that asks for its transcript still gets it, and a narration that needs no fit honours the choice
  in both directions;
* a job already in the field state (export with captions, job wanting none, record claiming current) is repaired by
  **one plain render**, keeping the old file and marking it superseded;
* a file that disagrees even after re-rendering is kept, marked `captions_disputed`, and not rendered again;
* the listing names the cause ("a narration longer than the picture … re-enabled captions") and the cost of the
  repair ("no new voice and no Flow credits").

Full suite: **28 failed / 1 819 passed / 4 skipped**, against a pristine 7.0.112 tree failing the *identical* 28
tests (environment-caused: browser, optional codecs). No regressions; 7 new tests.

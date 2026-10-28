# AutoVideoAI v7.0.115 — the export check that deleted what it was checking

You ran the Odia repair and the render finished. Then:

```
[ 73%] Rendering Odia edition Odia
[100%] Language editions finished
"status": "failed",
"error": "Export QC failed: duration or audio"
```

Fifty-nine minutes, and that was the entire explanation. Everything else came from one line inside the renderer:

```python
if abs(final_duration - full_duration) > 0.8 or not any(s.get('codec_type') == 'audio' …):
    raise ValueError('Export QC failed: duration or audio')
```

It raised inside the `try` whose `finally` deletes the temporary folder — so **the finished video was deleted with
it**. No numbers, no file, no cause, nothing to play, nothing to inspect. The Odia file from before is still on disk
(that is why you could still watch one), but the new render left no trace at all.

## What v7.0.115 changes

**1. The check measures the two tracks separately, and says the numbers.**

"The picture stops at 0:54.0" and "the audio stops at 0:54.0" are different defects with different repairs; the old
check could not tell them apart, or tell you either. It now reports the expected length, the file's own length, its
picture length and its audio length in seconds.

**2. A failed check keeps the video it made.**

The finished file is copied beside the plan as `result-<lang>.qc-failed.mp4`, and `qc-<lang>.json` keeps the numbers.
The job says so in words:

```
Odia edition failed: Export QC failed: the picture stops at 0:54.0 but the timeline runs to 1:01.4. …
  The render did produce a file: …/language_editions/20261028-124105-d29cddeb/result-or.qc-failed.mp4
  (expected 61.4s, picture 54.0s, audio 61.4s). It is kept and playable but not marked current, because it
  failed the duration check.
```

and the listing repeats the path with `Play it before spending another render on it`.

**3. The picture is extended to the timeline before the expensive pass.**

If the concatenated picture is even slightly shorter than the container says — an intro/outro whose audio runs past
its video, a fitted picture that lost a few frames — the last frame is now cloned to cover the gap, for free, before
the hour-long encode. That is a plausible cause of exactly this failure, and it no longer lands after the encode.

**4. An mp4 whose header disagrees with its own tracks is no longer a failure.**

If both tracks run to the timeline and only the container's duration field is off, the export is accepted with a
note in its provenance: *the tracks are what plays*. Re-rendering for an hour would produce the same file.

**5. When a language has no current export, the videos it still has are named.**

This is the third report in a row where the app said `Odia: no current video yet` while finished Odia videos sat in
the folder — the record had lost its pointer, the files had not moved. The summary now reads:

```
Odia: no current video · newest one on disk: or-20261027-214110-f0e33d42.mp4 · captions: yes
```

and the listing explains that it is not current, why, and that it is still there.

---

## What to do with your Odia video

Update to 7.0.115, then render once more:

```
python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --fit-hold 8
```

Outcomes, all of them informative now:

* **it exports** — you have the Odia video without a transcript, the earlier files are kept;
* **it fails the check again** — the finished file is kept at
  `language_editions/<stamp>/result-or.qc-failed.mp4`, `.qc-failed`. Play it. If the picture and the narration both
  end where they should, the file is good in every way that matters and the numbers in the message tell me what to
  change next; if the picture really does stop early, the message says by how much and where.

Nothing in this release re-records a voice, spends a Flow credit, or deletes any video.

---

## Updating

Stop the dashboard, extract this zip **beside** your installation, then:

```bash
python3 ../AutoVideoAI-v7.0.115/tools/update_v7114_to_v7115.py /path/to/AutoVideoAI-v7.0.114         # dry run
python3 ../AutoVideoAI-v7.0.115/tools/update_v7114_to_v7115.py /path/to/AutoVideoAI-v7.0.114 --apply
```

Code, docs and tests only. `outputs/`, saved jobs, Flow journals, browser profiles and `music_library/` are never
touched; a file you edited yourself is preserved and the run stops and names it. It refuses anything older than
7.0.114. Code backups go to `code-update-backups/v7.0.114-to-v7.0.115-<stamp>/`.

---

## Verification

New tests: `tests/test_v7115_qc_keeps_the_file.py` (**12**), real FFmpeg renders where they matter.

* a good export passes with no problems and no notes; a missing audio track, a picture that stops early and a short
  audio track are each named with both numbers in seconds;
* a container whose header disagrees with its own tracks produces a note, not a failure;
* an mp4 that omits per-stream durations falls back to the container instead of inventing a defect;
* a fitted export that comes up short names the fit (`picture x1.25`, `narration x1.12`, `last frame held 14.0s`) and
  says the picture had already been extended;
* a successful render writes `qc-<lang>.json` and its provenance now carries `export_qc` with the measurements;
* a failed check keeps `result-or.qc-failed.mp4`, writes the numbers to `qc-or.json`, raises a message that names the
  defect, the numbers, the kept file and the cost of retrying — and the temporary folder no longer holds the only
  copy;
* the panel diagnosis says *the render did produce a file* and gives its path; the listing says the same and adds
  "play it before spending another render on it";
* a language whose record lost its pointer names the newest finished video on disk, with date and caption state, in
  both the summary and the listing;
* after a failed check, the same command exports normally — the failure is not sticky.

Full suite in this environment: **55 failed / 1 806 passed / 4 skipped**, against a pristine 7.0.114 tree failing the
**identical** 55 tests (this sandbox's FFmpeg build has no `subtitles`/`drawtext` filters, so the caption and
clip-editing suites cannot run here). No regressions; 12 new tests.

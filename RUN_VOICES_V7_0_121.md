# v7.0.121 · One obvious way to run prepared voices, and TTS runs a finished job no longer needs

Two questions from the same page:

> *"still need to know how to resume this so that it will create a job and corresponding video"*
> *"why is it still showing the tts for the completed jobs?"*

## 1 · The answer is now the first thing on Queue & Resume

v7.0.120 added **Use these voices** inside each finished batch, but the batches themselves were inside a
collapsed list, so the way to a video was three levels down. Queue & Resume now opens with:

```
Run your prepared voices
  Batch to run            [ 2026-10-31 10:21 · English, Hindi, Odia · voices 3/3 · not part of any job yet · newest ]
  How may this narration be used?   [ I wrote this narration or own it ]
  [ ] Start it as soon as it is created (Flow spends credits as it generates)
  [ Create the job from these voices ]
```

One selectbox picks the batch (newest first, identified by its time, topic and languages), one statement of
your rights, one button:

* the job is created **from that batch's own narration**, word for word, so its script *is* your voice;
* all three voices are copied into the job;
* the page switches to the new job with `SCRIPT ✓ · VOICE ✓`, the narration you can play, and
  **Nothing has been generated yet - press "Resume / continue job" below to make the video.**

If you would rather do it in one step, tick **Start it as soon as it is created** - that is the only thing that
spends Flow credits, and the label says so. The same thing exists on the command line:

```
python3 cli.py v3 use-voices --list
python3 cli.py v3 use-voices <batch> --create-job --rights own_content
python3 cli.py v3 resume <job>
```

`v3 use-voices` also accepts `--attach-to <job_id>` for a saved job that already approved the same script, and
`--seconds N` when the measured narration length is not the length you want (for example when the approved
voices are shorter than the target video).

## 2 · Why a finished job still showed a "tts" line

It was real, and it was not your current work. Those entries are **Create step 4 batches that stopped during
TTS** (2 of 3 languages) and live *inside* a job folder. The job went on to narrate another way - its voices
were attached from a Create step 4 batch, or it recorded them itself - and reached generating/rendered. The
abandoned run was still listed exactly like unfinished work, so it kept asking to be resumed although nothing
about it was needed.

Now each such batch is judged against the job it belongs to (`engine/speech_batches.job_stage`):

* if the job has already narrated, planned scenes or moved past narration, the batch is **not** counted as
  "to finish" and is listed under
  **`Stopped TTS runs a job no longer needs · N · kept, nothing deleted`** with the reason spelled out:
  *"This job is already past narration (status "generating", 2 scene(s) planned). Its narration is already
  saved (English · Hindi · Odia). This stopped TTS run is not needed to resume the job; it is kept here,
  nothing was deleted. Use "Resume / continue job" on the job itself."*
* if the job has *not* narrated yet, the batch stays in the normal list, because finishing it really is the
  next step.
* nothing is deleted, moved or rewritten. It is still openable ("Inspect this stopped batch") and its voices
  can still be resumed deliberately.

The same distinction is in `python3 cli.py v3 use-voices --list`, which prints
`· stopped run a job no longer needs` for those rows.

## Verified

* 9 new tests (`tests/test_v7121_run_prepared_voices.py`): the stale judgement for a job past narration, a job
  that has not narrated yet, and a finished batch; stale rows leaving the to-do list while staying in the
  inventory; newest-first ordering; the page creating and opening the job from the top panel (real Streamlit
  run, `SCRIPT ✓ · VOICE ✓`, the "nothing generated yet" line); the CLI list / refusal without a rights
  statement / create with one.
* Full suite on the unzipped release, compared with a pristine v7.0.120 checkout: identical failure set, no new breakage. v7.0.120: 46 failed, 1776 passed, 94 skipped, 11 errors. v7.0.121: 46 failed, 1785 passed, 94 skipped, 11 errors. Same 57 FAILED/ERROR node ids on both sides (`diff` of the sorted lists is empty) - the 9 extra passes are this release's new tests. The 46+11 are the long-standing FFmpeg/`drawtext` and browser-shim tests that cannot run in a headless sandbox.

## Install

Stop the dashboard, extract `AutoVideoAI-v7.0.121-Run-Voices.zip` beside your installation, then from inside it:

```
python3 ../AutoVideoAI-v7.0.121-Run-Voices/tools/update_v7120_to_v7121.py . --apply
python3 cli.py v3 self-check
```

The updater replaces only the code files it lists, keeps a backup in `code-update-backups/`, refuses to
overwrite a file you edited, and never touches `outputs/`, saved jobs, speech batches, Flow journals, browser
profiles or `music_library/`. No voice is recorded and no Flow credit is spent by this release.

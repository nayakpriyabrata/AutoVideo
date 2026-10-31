# v7.0.119 · Queue & Resume shows your narration and your completed steps

Your report, after installing 7.0.118:

> when I tried to recover it with queue and resume, i don't see the audio and completed steps, instead it is
> showing the last successful job details

The page you pasted was the Queue, and every part of that was real. Three separate things produced it.

## 1. The list you saw was speech batches, and nothing said so

```
Speech batches · Create step 4 · 2 to finish
Create step 4 · English, Hindi, Odia · ready · voices 3/3
Create step 4 · English, Hindi, Odia · ready · voices 3/3
Job 20261022-143856-7-small-daily-habits-tha-9729 · English, Hindi, Odia · tts · voices 2/3
```

Those are **Create step 4 narration batches, not jobs.** Several of them were fully expanded because no
job was selected in the sidebar, and each one carried exactly the same five words of description - no time,
no topic - so an old session from 22 October and yesterday's session looked identical. A batch is not a
resumable job: until it is attached to a created job, there is nothing to Resume, and its voices live only in
the batch folder.

v7.0.119:

* Every batch now identifies itself: **when** it was made, **which topic** it is for, its languages, its state
  and - new - **where its voices ended up**:
  `Create step 4 · 2026-10-28 09:15 · "The Growth Mindset of small daily habits" · English, Hindi, Odia ·
  ready · voices 3/3 · not part of any job yet`
  (or `voices in job 20261031-120000-…` when a job already holds them, or
  `saved in <job> · voices not copied into the job yet` for a batch that lives inside a job).
* With no job selected the panel says so in its title
  (`Speech batches · Create step 4 · no job selected · 4 batches · 3 ready and not in a job`) and explains,
  in plain words, that these are narration batches and not jobs. Each batch is now a collapsed line with its
  identity instead of a wall of identical expanded rows; the newest one is open.
* The creation time is written once (`created_at` in `batch.json`) and preserved across a resume, so
  re-running TTS can never make an old batch look new. Old batches without it use the file's own timestamp.

## 2. A ready batch never played its audio

For a finished batch the panel showed one sentence - *"In Create step 4, tick "reuse this exact batch""* - and
nothing else. The voices existed and were saved, but nothing could play them. Now a ready batch shows **one
player per language** ("English · 61.5 s", "Hindi · …", "Odia · …") and the narration text of each language in
an expander. Listening generates nothing and re-records nothing.

## 3. Queue now shows the completed steps and the narration of the job it opens

* The step row that Create already had (SCRIPT · VOICE · STORYBOARD · FLOW · QC · RENDER) is now shown in
  **Queue & Resume** too, above the job monitor.
* **VOICE used to mean "a file exists at `narration/voice.mp3`".** A job whose narration came from a prepared
  batch keeps its voices in `speech-editions/<language>/voice.mp3` and `production/prepared_speech.json`, so the
  step showed a dash although the narration was there and playable - the "I don't see the audio" part.
  `engine/narration_assets.py` now finds every voice a job holds, wherever it is, and the step row says
  **✓** with a line naming them: *"Narration saved in this job: English · Hindi · Odia"*.
* A new **Narration** section in Queue plays each saved voice with its language and length. When a job has no
  narration at all it says exactly why: a job whose voices were prepared in Create step 4 only gets them when
  that batch is attached ("reuse this exact batch"); until then they live in the batch, not in the job.
* If Queue is opened with **no Active job**, it now offers an **Open a saved job** picker with each job's
  status and last update, so Queue & Resume can be used without hunting in the sidebar.

## About your own job

The v7.0.118 traceback happened on the *last click* of Create, so that job was never created - there was
nothing to resume, which is why Queue could only show older material. After updating:

1. Create the production again (it now works), and tick **"reuse this exact batch"** for the voices you already
   prepared - the fresh batch is the one labelled **newest** and *not part of any job yet*; its audio is
   playable in Queue before you create anything.
2. Then open the job in Queue: the step row, the narration and Resume are all in one place.

## Verified

* 12 new tests in `tests/test_v7119_queue_narration_and_steps.py`, including the real Streamlit page driven by
  `AppTest` over a miniature installation (Create step 4 batches + one job with an old stopped batch, no job
  selected): every batch line is unique, the ready batches' voices are playable, and the panel states these are
  not jobs.
* Attachment detection is read from the job's own snapshots (`production/prepared_speech.json`,
  `production/language_editions.json`) - no file is hashed, nothing is generated, moved or deleted.
* Full suite on the unzipped release: **35 failed / 1876 passed / 4 skipped** against a pristine v7.0.118
  baseline of **36 / 1863 / 4** - no new failure, and the one difference is a pre-existing timing test that
  passed in this run. All 35 are the sandbox FFmpeg build (no `drawtext`/`subtitles` filter).

## Install

Stop the dashboard, extract `AutoVideoAI-v7.0.119-Queue-Narration-And-Steps.zip` beside your installation,
then from inside it:

```
python3 ../AutoVideoAI-v7.0.119-Queue-Narration-And-Steps/tools/update_v7118_to_v7119.py . --apply
python3 cli.py v3 self-check
```

The updater replaces only the code files it lists, keeps a backup in `code-update-backups/`, refuses to
overwrite a file you edited, and never touches `outputs/`, saved jobs, Flow journals, browser profiles or
`music_library/`. No voice is re-recorded and no Flow credit is spent by this release.

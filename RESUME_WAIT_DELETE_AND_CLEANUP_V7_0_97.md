# AutoVideoAI 7.0.97 · a 60-second image wait, a deletable completed job, Clip Studio cleanup, and speech batches that belong to the job you selected

Four reports from the same session, fixed together.

## 1 · The image wait is 60 seconds, not 360

A saved Flow project either already holds the finished image or it does not; six minutes in the tab
told us nothing that one minute does not. Every image recovery wait is now **60 s** by default:

- `engine/flow_image_transaction.recover()` — the wait after reopening a saved request;
- `engine/isolated_frame_regeneration` — the replacement-frame wait;
- `engine/providers/flow_browser` — the older single-image path.

It is a real job setting, `flow_image_wait_seconds`, so a slow account can raise it:

```
python3 cli.py v3 resume <job> --flow-image-wait-seconds 120     # this job, saved for later resumes
```

`Factory.set_flow_image_wait_seconds()` writes it to the job's `settings.json` and logs
`flow_image_wait_updated`; the default lives in `engine/studio_config.DEFAULTS`, and the journal records
`image_wait_seconds` so a log shows exactly how long each attempt waited. The wait is clamped to
5–3600 s, and a *completed* wait with no output still ends the same way it did in 7.0.96: no second wait,
one fresh free image request.

## 2 · A completed job can be deleted again

`Delete completed job · permanent` refused the job
`20261018-132625-speak-with-confidence--5-0686` with *"No validated final video; profile retained"*.

The guard looked at exactly one path, `render/<job>-final.mp4`. A production rendered with **video
cutaways** writes `render/<job>-final-broll.mp4` (see `factory`), so a finished 2.4 GB job looked like a
job with no video. `engine/job_cleanup.find_final_video()` now checks, in order:

1. the manifest's `final_path`;
2. `render/<job>-final.mp4`;
3. `render/<job>-final-broll.mp4`;
4. `render/*-final*.mp4`, `*-final*.mp4`, `final*.mp4`.

Each candidate is validated (a real container with a finite duration, never a still image in disguise)
and the **largest valid one wins**. The preview shows which file was accepted and its size, plus the
reason every rejected candidate was rejected (`missing`, `too small`, `not a decodable video`, `symlink`).

If a completed job genuinely has no finished video, that is no longer a dead end: tick
*"Delete this completed job even though no finished video was found"*, type the exact job ID, and the
folder is removed with `override: "no_final_video"` recorded in the report. Two things still refuse
deletion outright, with or without that tick: a job that is **not finished**, and a job with an
**unresolved Flow request** (the folder is what lets that request be recovered).

## 3 · Clip Studio content has a cleanup panel

*A Clip Studio run leaves the downloaded source video, speech chunks, caption/batch scratch files
and staged logos (`_clip_work/`), the per-batch selection reports (`clip-history/`), the latest
selection and B-roll reviews, the clip render job state (`.clip-render-jobs/`) and the rendered clips
themselves.*

**Settings → Clip Studio content · disk cleanup** lists every Clip Studio output folder (the one under
`outputs/` and the folder currently typed in Clip Studio), with total size, clip count and whether a
render is running. Each category is a separate tick:

| Category | What it removes |
|---|---|
| `work` | `_clip_work/` — downloaded source, speech chunks, caption and batch scratch files |
| `render_state` | `.clip-render-jobs/` — finished or resumable render state |
| `history` | `clip-history/` — per-batch selection reports |
| `reviews` | `highlights.json`, `highlights.partial.json`, `broll-review-*.json` |
| `clips` | `*.mp4` in the folder — **the product**, and it needs its own tick |

The safe categories are pre-ticked, the rendered clips are not. A folder with a **running clip render**
is refused, symlinked entries and anything outside the selected folder are skipped, and the preview
(`eligible_bytes`) is rechecked before anything is removed (dry run → apply, like the worker cleanup).

## 4 · Speech batches belong to the selected job

The Queue panel listed every Create step 4 batch of the installation, so the batch saved with the
**Active job** was buried among sessions from earlier days — six *"Create step 4 · ready"* cards around
the one that mattered.

Now the Active job decides:

- the header names the job: **Speech batches · `<job id>` · N to finish**, and the panel shows only the
  batch saved inside that job (`partition_for_job`, `list_speech_batches(include_finished=[job])` so a
  *finished* job batch is still shown instead of "no batch yet");
- every other Create step 4 batch is in a collapsed folder,
  **"Other Create step 4 batches · not attached to this job · N to finish"**, still usable for finishing
  TTS and reusing in Create step 4;
- with no Active job selected the panel behaves as before — that is where pre-create batches live.

## Tests

`tests/test_v797_cleanup_and_waits.py` (19 tests, fakes only — no browser, no Flow request, no credits):

- the 60 s default, a job's saved value, invalid values, the 5–3600 s clamp, and the timeout actually
  handed to `wait_for_agent_generation`;
- a `-final-broll.mp4` job is eligible and its file is the one reported; a manifest `final_path` is
  accepted; a completed job without a video says exactly which files were checked; the explicit
  override deletes it; an unfinished job and a pending Flow request are never overridable;
- Clip Studio inventory per category, discovery under `outputs/`, dry run → apply, the rendered clips
  needing their own opt-in, a running render refused, a foreign folder refused;
- a finished job batch listed only when asked for, and batches partitioned by the Active job.

## Install

1. Stop the dashboard.
2. Extract `AutoVideoAI-v7.0.97-Resume-Wait-Delete-Cleanup.zip` beside your installation folder.
3. Run the updater from inside the installation folder:

   ```
   python3 ../AutoVideoAI-v7.0.97/tools/update_v796_to_v797.py .            # dry run: shows the plan
   python3 ../AutoVideoAI-v7.0.97/tools/update_v796_to_v797.py . --apply    # installs the code
   ```

   It accepts an installed 7.0.96 (or an already-updated 7.0.97), backs replaced files up under
   `code-update-backups/v7.0.96-to-v7.0.97-<timestamp>`, and leaves outputs, saved jobs, settings,
   browser profiles, Clip Studio folders, music, characters and channel profiles untouched.

## Not verified live

No Flow project was opened, no clip was rendered and no job was deleted while building this release.
The wait value, the final-video selection, the cleanup categories and the batch partitioning are covered
by fakes and small fixtures; the first real Resume, deletion and cleanup run are the confirmation.

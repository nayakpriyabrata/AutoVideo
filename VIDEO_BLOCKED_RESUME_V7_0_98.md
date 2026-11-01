# AutoVideoAI 7.0.98 · the Resume advice now matches the request it is stuck on (and what to check before you press Resume)

Your job reached a different blocker than the one the panel described:

```
Safe Resume blocked: 1 unresolved Flow request journal(s) …
Saved request(s): flow/shots/shot_014/take_01.mp4
… Image requests cost no Flow credits, so ONE fresh image request may be submitted …
python3 cli.py v3 archive-request <job> flow/shots/shot_014/take_01.mp4
```

`flow/shots/shot_014/take_01.mp4` is a **video** take, not an image. Two things were wrong:

1. **The command could never work.** For a video journal, `archive-request` without
   `--confirm-new-credit-spend` prints *"Dry run. Add --confirm-new-credit-spend to archive. Nothing was
   changed."* — so following the panel changed nothing and the next Resume repeated the same wait.
2. **The money was wrong.** A new Flow **video** does spend credits (unlike an image). The panel promised a
   free replacement that does not exist for video.

The panel also still named `shot_003` and an archive command for `storyboard/shot_023_open.jpg`, a request
that had already been resolved — so it described three different requests at once.

## What 7.0.98 changes

**The journal decides what the message says.** `check_job()` records each journal's kind, and
`FlowResumeBlocked` / the Queue panel / `tools/flow_resume_preflight.py` now split requests:

| Request | What the panel says | Command it offers |
|---|---|---|
| image (`storyboard/*.jpg`, `isolated_image_v1`) | free: one new image request, no credit approval | `archive-request <job> <image>` (no flag) |
| video (`flow/shots/<shot>/take_*.mp4`) | paid: recover the exact saved video first, nothing is resubmitted automatically | `recover-flow-video <job> --shot-id <shot> --wait-seconds 180`, then the reviewed editor URL, then (paid only) `archive-request … --confirm-new-credit-spend` |

- Video journals are recognised by `kind`, by scope, or — for old journals — by their path
  (`flow/shots/<shot>/take_*.mp4`), so a 7.0.8x journal is classified correctly too.
- The Queue panel now lets the **unresolved journal decide which shot it names** (shot_014, not the stale
  pause snapshot's shot_003) and drops commands that point at a request that is no longer unresolved.
- Actions are labelled honestly: *"Recover the exact saved video (0 new credits)"* for the free path and
  *"Allow ONE new paid video request"* for the archive.
- `archive-request` on a video journal now explains itself in the dry run (it spends credits, and what to
  try first) instead of borrowing the free-image wording; with the flag it says **PAID**.

## Before you press Resume — five checks, two minutes

You are on 7.0.97; install 7.0.98 first, then:

1. **Read the exact blocker** (read-only, no browser):

   ```
   python3 tools/flow_resume_preflight.py outputs/20261022-143856-7-small-daily-habits-tha-9729
   ```

   It prints the request, its saved project, the last recovery result, and the commands below.

2. **Open the project saved in the request** — for your log that is
   `https://flow.google.com/project/37d8cf57-12b4-4a85-9934-5580e90d3781` (the journal owns it; the one
   the panel linked, `bb258e72-…`, and the one opened at 15:11, `08d0cf93-…`, are different projects).
   Two scans reported *"6 gallery assets, 0 fresh candidates, 0 readable prompts"* — look yourself for a
   finished video of shot_014.

3. **If the video is there**, download exactly it (0 credits, QC still runs):

   ```
   python3 cli.py v3 recover-flow-video <job> --shot-id shot_014 \
       --asset-url https://flow.google.com/project/37d8cf57-…/edit/<asset-id> --asset-reviewed
   ```

   The URL must belong to that same saved project. This is the only adoption path the app allows on
   purpose: a video from another project could belong to a different shot.

4. **If the video is only in another project** (`08d0cf93-…`, `bb258e72-…`), it cannot be adopted
   automatically. Your choice is then a **paid** replacement for that one shot:

   ```
   python3 cli.py v3 archive-request <job> flow/shots/shot_014/take_01.mp4 --confirm-new-credit-spend
   python3 cli.py v3 resume <job>
   ```

   which archives the old request (kept on record) and submits one new video request.

5. **Check nothing else is already waiting**: the log shows `Waiting for production slot … Other tabs may
   monitor this job` at 15:14 — two Studio tabs were competing, and a Resume pressed in the tab that does
   not hold the slot only queues. Close the extra tabs, and never Resume while
   `logs/[job]` shows a running production.

Note what is already good: the image request for `shot_023_open.jpg` that blocked you yesterday is
**resolved** — the 7.0.96 fix worked, and the job advanced from shot_003 to shot_014 (44%). Hindi and Odia
stay at `needs_picture` until this job produces its finished video; the picture-only master can only be
built *from* that video, so it is the last step, not the first.

## Tests

`tests/test_v798_video_blocked_message.py` (8 tests, fakes only):

- a video journal never gets the free-image wording, always names `recover-flow-video --shot-id shot_014`
  and the paid archive with `--confirm-new-credit-spend`;
- an image journal keeps the free wording and a flag-free command;
- a mixed job explains the two requests separately;
- `archive-request` on a video journal is a dry run that says it costs credits and points at the free
  recovery first, and says **PAID** when it is applied;
- the Queue panel names shot_014 from the journal, drops the stale `shot_023` command, and labels the two
  actions honestly;
- the preflight tool prints `(video)` / `(image)`, the free recovery, `Paid only`, and both closing notes.

`tests/test_v792_stalled_recovery.py` still passes unchanged: a legacy image journal without `kind` is
still treated as an image request (the path decides).

## Install

1. Stop the dashboard (all tabs).
2. Extract `AutoVideoAI-v7.0.98-Video-Resume-Message.zip` beside your installation folder.
3. Run the updater from inside the installation folder:

   ```
   python3 ../AutoVideoAI-v7.0.98/tools/update_v797_to_v798.py .            # dry run: shows the plan
   python3 ../AutoVideoAI-v7.0.98/tools/update_v797_to_v798.py . --apply    # installs the code
   ```

   It accepts an installed 7.0.97 (or an already-updated 7.0.98), backs replaced files up under
   `code-update-backups/v7.0.97-to-v7.0.98-<timestamp>`, and leaves outputs, saved jobs, settings, browser
   profiles, Clip Studio folders and every Flow journal untouched.

## Not verified live

No Flow project was opened and no video was requested while building this release. The message, the
classification and the commands are covered by fakes; whether the shot_014 video still exists in project
`37d8cf57-…` can only be settled by opening it.

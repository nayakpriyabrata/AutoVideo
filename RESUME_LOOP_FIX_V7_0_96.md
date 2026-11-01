# AutoVideoAI 7.0.96 · a blocked Resume now moves forward instead of repeating the same wait

Job `20261022-143856-7-small-daily-habits-tha-9729` could not be resumed. Every attempt ended at
"Recovery needs attention — Saved request unresolved; no new generation started", with shot
`storyboard/shot_023_open.jpg` still missing and Hindi/Odia stuck at `needs_picture`.

## What was actually happening

The saved request for `shot_023_open.jpg` named Flow project `ca1709fe-…`. By the time Resume ran,
Flow was showing a different project — the request had been submitted in a project the job never
recorded (`2d019101-…`), and the single-valued project binding had been overwritten by later work.

The recovery path then did this, on every Resume:

1. `tx.recover()` reopened the journal's project with `ensure_project(...)`;
2. Flow did not land on that project, so `capture()` refused with
   `Image project changed; no download attempted` — correct in itself: reading whichever project Flow
   shows could adopt **another shot's image**;
3. that refusal is a generic error, so it was retried three times and ended as
   `Image recovery checkpoint retained: Image project changed …`, which deliberately does **not** allow
   a fresh request (a browser or download problem must never cause a resubmission);
4. `reconcile_job` recorded the journal as `pending`, `check_job` still saw it, `require_safe_job`
   raised, and the dashboard printed "Saved request unresolved; no new generation started" — identical
   to the previous attempt, with no new information and no way out.

In the runs where the project *did* open, the six-minute wait found only the two uploaded references.
That verdict did allow a fresh request, but the automatic budget (three submissions per shot) counts
**every** archived journal, including the ones the published advice told you to create by hand. The
documented command therefore increased the very counter that was blocking it: archive once more and the
cap was hit again, this time with nothing left to archive.

The advice itself was also wrong about money. `config/flow_models.yaml` sets `credits_per_image: 0` and
`flow_image_transaction.py` states "Image requests are free in Flow", so
`--confirm-new-credit-spend` asked you to approve a spend that never happens.

## What 7.0.96 changes

- **A project that cannot be reopened is a verdict, not a retry.** After `ensure_project`,
  `require_saved_project()` compares the live URL with the journal's URL. If Flow is showing a different
  project, recovery stops at once: no wait, no download, no adoption of another project's gallery, no
  second or third attempt. The journal records `recovery_state: saved_project_not_reachable` together
  with `saved_project_url` and `observed_project_url`.
- **One fresh, free image request is then submitted automatically**, in a new project, exactly as for
  the "only references were found" case. Waiting again in a dead project can never produce the image.
- **A generic browser or download failure still never resubmits**; it is recorded as
  `recovery_checkpoint_retained` and now says so instead of looping silently. A fresh request that
  fails before its new project is bound (browser closed, project creation refused) is recorded as
  `fresh_request_not_started`, so the next blocked Resume explains that too.
- **The automatic budget can no longer block itself.** Only archives this app created
  (`*.flow-request.auto-archived-*.json`) count toward the three automatic submissions per shot. An
  archive you run yourself (`cli.py v3 archive-request`, `*.flow-request.archived-*.json`) is one
  authorised submission of its own and always allows exactly one more free image request.
- **No credit confirmation for image requests.** `cli.py v3 archive-request` and
  `tools/archive_uncertain_flow_image.py` archive an isolated image journal without
  `--confirm-new-credit-spend`. The flag is still accepted for old scripts, and is still required for
  any journal that is not a free image request.
- **The reason is visible, in one line.** The blocked-Resume message, the Queue panel and
  `tools/flow_resume_preflight.py` now print the last recovery verdict for each journal, the saved
  project, and the single command that moves the job forward. The preflight tool stays read-only: it
  opens no browser and submits nothing.

## What to do with the current job

1. Stop the dashboard (one production slot at a time).
2. Install 7.0.96 (below).
3. Read the diagnosis — no browser, no requests:

   ```
   python3 tools/flow_resume_preflight.py outputs/20261022-143856-7-small-daily-habits-tha-9729
   ```

4. Resume once:

   ```
   python3 cli.py v3 resume 20261022-143856-7-small-daily-habits-tha-9729
   ```

   If the saved project cannot be reopened, recovery now says so and submits **one** free image request
   for `shot_023_open.jpg` in a new project. If the automatic budget is already used up, the message
   names the exact archive command; run it, then Resume once. Nothing else is archived or resubmitted.

5. When the frame is accepted, finish the three languages:

   ```
   python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --explain
   python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --recover-picture
   ```

   `needs_picture` is not a second bug: this job never reached the FFmpeg staging render, so
   `production/visual_master.json` does not exist and Hindi/Odia have nothing to mix onto. The
   picture-only master built from the finished video (the panel checkbox, or `--recover-picture` above)
   is the v7.0.95 answer, and it can only run after the missing frame is resolved.

## Install

1. Stop the dashboard.
2. Extract `AutoVideoAI-v7.0.96-Resume-Loop-Fix.zip` beside your installation folder.
3. Run the updater from inside the installation folder:

   ```
   python3 ../AutoVideoAI-v7.0.96/tools/update_v795_to_v796.py .            # dry run: shows the plan
   python3 ../AutoVideoAI-v7.0.96/tools/update_v795_to_v796.py . --apply    # installs the code
   ```

   It accepts an installed 7.0.95 (or an already-updated 7.0.96), backs replaced files up under
   `code-update-backups/v7.0.95-to-v7.0.96-<timestamp>`, and leaves outputs, saved jobs, settings,
   browser profiles, music, characters and channel profiles untouched. An installation older than
   7.0.95 must be updated one zip at a time first.

## Tests

`tests/test_v796_resume_loop.py` reproduces the field state with fakes only — no browser, no Flow
request, no credits — and asserts:

- a saved project that cannot be reopened escalates once: zero waits, zero downloads;
- a real image sitting in the project Flow happens to show is never downloaded or adopted;
- the "only references" wait still records its own verdict;
- a fresh request that cannot start is recorded as `fresh_request_not_started`, end to end through
  `reconcile_job`, and the blocked message names it;
- `generate()` replaces a lost request once and then finishes;
- the automatic budget stops with the exact flag-free archive command, and that command then allows
  exactly one more submission (the old deadlock);
- an explicit archive of an image journal needs no credit confirmation, while a non-image journal
  still does;
- the blocked-Resume message, the preflight tool and the dashboard diagnosis name the verdict and the
  next command.

Contract changes to two older tests are intentional: `tests/test_v791_reference_labels.py` now expects
an image journal to be archived without the flag (and adds a non-image journal that still needs it), and
`tests/test_v792_stalled_recovery.py` expects the archive command without `--confirm-new-credit-spend`.

## Not verified live

No Flow project was opened and no image was requested while building this release. The escalation,
the budget accounting and the messages are covered by fake-bridge tests; the real project binding,
the 360-second wait and the fresh submission still depend on your Flow session, and the first real
Resume is the confirmation.

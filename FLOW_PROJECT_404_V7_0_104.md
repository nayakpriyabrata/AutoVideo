# v7.0.104 — a current pause notice, and a dead project URL that says so

Two reports from **job `20261022-143856-7-small-daily-habits-tha-9729`** on 2026-10-27, both visible in the same
Queue panel.

## 1. The pause notice described a shot that was already finished

The panel said:

```
Job needs recovery at shot_018 · 17/45 accepted shots are saved.
Flow video request is saved at …/flow/shots/shot_014/take_01.mp4.flow-request.json.
Generation is blocked to avoid spending again.
Cause: FlowRequestPending: Existing request still has no single identifiable asset …
```

**shot_014 was accepted hours earlier.** The pause snapshot had been saved while shot_014 was still open, and
nothing ever rewrote it, so the panel mixed the current stopping point (shot_018) with an obsolete cause.

v7.0.104 rewrites the notice before it is shown. If the saved reason quotes a journal that is no longer
unresolved, or the production has moved past the saved shot, the notice becomes:

```
Superseded notice: this job was paused at shot_014, but that request is no longer unresolved
(it was downloaded or archived). No unresolved Flow request remains, so nothing blocks a Resume.
17/45 shots are accepted; Resume continues at shot_018.
```

When requests *are* still open, they are listed with their journal paths and shot ids. The old text is not
deleted: the Job panel keeps it in a collapsible "Earlier pause notice (superseded — kept for the record)".
Nothing is inferred — a notice is only replaced when the evidence (the unresolved journals, the next unfinished
shot) contradicts it.

## 2. `flow.google.com/404?reason=project` — "Project not found"

A stored project URL had been deleted, belonged to another Google account, or held a stale id. The run surfaced
it as the generic *"Configured Flow project URL opened but composer was not found"*, which says nothing about the
repair.

v7.0.104 detects the 404 page itself (URL contains `/404` or `reason=project`, or the body says "Project not
found") and raises `FlowProjectMissing`. Two details matter:

- it retries three times, 1.5 s apart, because a project created seconds ago can answer 404 while Flow
  provisions it — a 404 is not proof of a dead URL until it persists;
- it is raised **after** the composer timeout too, so a slow page cannot disguise the real cause.

The job then pauses with the event `flow_project_missing` and this message (job-scoped, with the real id and file):

```
Flow answered 'Project not found' for the stored video project (https://flow.google.com/project/<id>), so it was
deleted, belongs to another Google account, or the stored id is stale. Nothing was submitted or charged. That URL
is stored in flow_video_project.json; see both bindings with `python3 cli.py v3 flow-projects <job>`.
Repair options: `… --clear-video --confirm` (the next video submission opens its own project) or
`… --set-video https://flow.google.com/project/<real-project-id> --confirm`. The stills project is untouched. Any
clip that was only in the deleted project is gone; a shot whose clip no longer exists needs a replacement request
(it spends credits) - nothing does that automatically.
```

No image-motion fallback is taken on this path: falling back would hide a binding problem behind different
content.

Where it is shown:

- the Job panel shows the message as an error, above both bindings;
- `python3 cli.py v3 status <job>` prints it as `LAST PROJECT ERROR:` and lists `flow_project_missing` as the stop
  reason;
- the message never suggests rebinding the stills project when the dead URL is the video project (that was the
  v7.0.99 bug), and never claims a clip exists.

## Repair for the field job

```
python3 cli.py v3 flow-projects 20261022-143856-7-small-daily-habits-tha-9729 --clear-video --confirm
python3 cli.py v3 resume 20261022-143856-7-small-daily-habits-tha-9729
```

The stills binding stays on project `37d8cf57-12b4-4a85-9934-5580e90d3781`, which is live and holds the
storyboard images. Free disk space first (`2.7 GB` was reported free): Settings → Disk cleanup.

## Files

- `engine/pause_freshness.py` (new) — `refresh()`; pure, no I/O.
- `engine/factory.py` — `recovery_state` applies it and sets `pause_notice_stale`, `pause_notice_superseded`,
  `paused_shot`, `unresolved_journals`; `flow_project_missing_record()`, `_record_flow_project_missing()`,
  `flow_project_missing_message()`; the video recovery and the generation loop convert `FlowProjectMissing` into a
  paused job with that message.
- `engine/providers/flow_browser.py` — `FlowProjectMissing`, `project_missing()`, and the persisted-URL wiring.
- `engine/job_activity.py` — `flow_project_missing` is a stop reason.
- `app.py`, `cli.py` — show the superseded notice and the last project error.
- `tests/test_v7104_stale_pause_and_404.py` (new) — 15 tests, no browser, no credits.

## Upgrade

```
python3 ../AutoVideoAI-v7.0.104/tools/update_v7103_to_v7104.py .            # dry run
python3 ../AutoVideoAI-v7.0.104/tools/update_v7103_to_v7104.py . --apply    # install
```

Stop the dashboard first. Outputs, jobs, journals, browser profiles and Clip Studio folders are untouched; code
backups go to `code-update-backups/v7.0.103-to-v7.0.104-<timestamp>`.

## Honest limits

- Nothing in this release was exercised against live Flow: no project was opened and no credits were spent. The
  404 detection and the pause freshness are covered by tests against fakes.
- A clip that existed only inside the deleted project cannot be recovered from it. Re-creating it spends credits
  and is never done automatically.
- `needs_picture` for the Hindi and Odia versions of this job is unrelated: they need `production/visual_master.json`,
  which only a completed FFmpeg staging render writes.

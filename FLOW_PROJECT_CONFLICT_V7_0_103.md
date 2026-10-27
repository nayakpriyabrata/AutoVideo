# AutoVideoAI 7.0.103 · the run stopped (and why), and the two Flow projects that collided

## Your question first: it is **not** running

`status=planned` means *the plan is saved*, not *work is in progress*. The red line is an error that stopped the
production: the browser closed, and nothing has progressed since 04:46:16.

```
[04:45:56] [28.00%] ⏭️ [44/45] shot_044 closing frame skipped
[04:46:12] [Flow][diag] browser launched
[04:46:16] [Flow] Opening persisted project URL: …/project/37f3495d-…
Video Flow project must differ from storyboard image project
```

Nothing was rendered, so the English edition is missing and Hindi/Odia stay `needs_picture` — that is expected
until a finished video exists; it is not a second failure.

One flag from your log worth acting on: **`Low disk space: 1.9 GB free`**. The final render needs room.

## What "Video Flow project must differ from storyboard image project" means

Storyboard stills and motion videos must live in **two different** Flow projects. A new video is identified by
its prompt *and* by being fresh in that project's gallery; if both roles share one project, a fresh video cannot
be told apart from the stills, so generation is refused (no credits spent).

**This one is my fault.** 7.0.99's recovery wrote the project it downloaded from — the *video* project — into the
job's **stills** binding (`settings.json → flow_project_url` and the database row). The video binding was
already on that project, so the next run saw both roles on one URL and refused to start. 7.0.103 no longer does
that; recovery binds the video role only.

## Repair your job (one command, no credits)

Your two bindings currently read:

```
Stills: 37d8cf57-…   from settings.json flow_project_url
Video:  37d8cf57-…   from flow_video_project.json
```

Check it yourself (read-only, no browser):

```
python3 cli.py v3 flow-projects 20261022-143856-7-small-daily-habits-tha-9729
```

Then choose one:

- **Let the video production open its own project** (recommended — least assumptions, and the stills project
  keeps the frames already generated there):

  ```
  python3 cli.py v3 flow-projects 20261022-143856-7-small-daily-habits-tha-9729 --clear-video --confirm
  ```

  The binding file is kept as `flow_video_project.json.cleared`; saved request journals keep their own project
  URLs, so nothing already submitted is redirected.

- **Or rebind the stills to their real storyboard project** (14dbfdef… from your 21:15 run, or a new one):

  ```
  python3 cli.py v3 flow-projects 20261022-143856-7-small-daily-habits-tha-9729 \
      --set-stills https://flow.google.com/project/<storyboard-project-id> --confirm
  ```

Then continue the job: **Resume** in the Queue (or `python3 cli.py v3 resume <job-id>`). The 28 % already done
(storyboard plan, most closing frames) is reused; it restarts at the video shots.

Before resuming, free some disk: Settings → *Disk cleanup* (worker + Clip Studio panels), or delete an old job
you no longer need. A 45-shot long-form render can want several GB.

## What 7.0.103 adds

| Piece | Behaviour |
|---|---|
| `flow_project_bindings()` / `flow_project_conflict_message()` | name both roles, **which file each value comes from**, whether they collide, and the exact repair commands |
| the guard | instead of a one-line error it pauses the job (so `planned` can never masquerade as "running"), logs `flow_project_conflict` with the shot, and raises the full explanation — nothing is generated or charged |
| `recover_flow_video` | binds the **video** role only (`_remember_flow_video_project_url`); it can no longer overwrite the stills binding |
| `cli.py v3 flow-projects <job>` | read-only report; `--set-stills URL`, `--set-video URL`, `--clear-stills`, `--clear-video`, all requiring `--confirm`, one action per command. Refuses a second video binding without clearing first, and flags stored copies that disagree |
| `cli.py v3 status <job>` | one honest answer: **RUNNING** (a live process holds the job lock, plus last stage/percent) or **NOT RUNNING** (with the last stage, the event that stopped it and its reason), then both project bindings and a CONFLICT line |
| Job panel | new *"Flow projects — storyboard images vs video clips"* expander shows both bindings, the explanation and the copy-ready repair commands |

## Tests

`tests/test_v7103_project_conflict.py` — 17 tests: bindings resolved across settings/database/file with their
sources; a collision detected across sources; the message naming both sources and commands; the old one-line
error gone and the job paused instead; the recovery no longer touching the stills writer; the CLI read-only by
default, dry-run without `--confirm`, `--clear-video` freeing the role with a `.cleared` backup, `--set-stills`
rebinding both copies, `--set-video` refusing a second binding, two actions refused, invalid URL refused,
`--clear-stills` removing both copies, the OK line, disagreeing copies reported; and the running/stopped probe
(free lock vs held lock, stop reason, the `planned` explanation).

## Install

1. Stop the dashboard (all tabs).
2. Extract `AutoVideoAI-v7.0.103-Flow-Project-Conflict.zip` beside your installation.
3. From inside the installation folder:

   ```
   python3 ../AutoVideoAI-v7.0.103/tools/update_v7102_to_v7103.py .            # dry run
   python3 ../AutoVideoAI-v7.0.103/tools/update_v7102_to_v7103.py . --apply    # installs the code
   ```

   Accepts an installed 7.0.102 (or an already-updated 7.0.103). Replaced files are backed up under
   `code-update-backups/v7.0.102-to-v7.0.103-<timestamp>`; outputs, jobs, Flow journals, browser profiles and
   Clip Studio folders are never touched.

You can repair the binding without installing anything (edit `settings.json` / move
`flow_video_project.json`), but `flow-projects` does it safely and prints what it changed.

## Not verified live

No Flow project was opened and no credit was spent here. The classification and repairs are covered by tests;
which project your stills should live in is your call — I can see the URLs in your logs, not your gallery.

# AutoVideoAI 7.0.100 · the commands take a job id, and a wrong one says what to type

Your three attempts failed for one reason that had nothing to do with Flow:

```
python3 cli.py v3 recover-flow-video outputs/20261022-143856-7-small-daily-habits-tha-9729

FileNotFoundError: .../AutoVideoAI-v7/outputs/outputs/20261022-143856-7-small-daily-habits-tha-9729/production_manifest.json
```

The app already prefixes `outputs/`, so the pasted folder became `outputs/outputs/…`. The trailing-slash
retry failed identically, and the traceback never said what to type instead.

**The correct command is just the job id:**

```
python3 cli.py v3 recover-flow-video 20261022-143856-7-small-daily-habits-tha-9729 \
    --shot-id shot_014 --wait-seconds 180
```

(run it from `/mnt/c/Users/eiyanpr/Downloads/Auto/AutoVideoAI-v7`).

## Where your job actually stands now

Your new screenshot shows Flow answered the approval with

> Your video generation has been scheduled and is waiting in the queue due to high demand. Feel free to check
> back shortly to check its progress.

So the 5 credits were spent and the generation **is accepted — it is queued, not finished**. Nothing is
downloadable yet, which is exactly what the recovery scan reported. Also note the Flow UI shows the approval as
*chosen* (the faded row) with a separate **Approve** button at the bottom right: that button submits the choice.
Your queue message means it did submit.

**Do not resume yet.** Resume reopens the project, finds no video, waits, and pauses again — harmless, but it
burns the browser round-trip and changes nothing.

The order is:

1. **Wait** for the queue (5–30 minutes is normal at "high demand"; the clip appears in the project's media
   grid, and a `360p` tile appears in the chat). Waiting costs nothing.
2. **Download it** (0 credits, QC still runs):

   ```
   python3 cli.py v3 recover-flow-video 20261022-143856-7-small-daily-habits-tha-9729 \
       --shot-id shot_014 --wait-seconds 180
   ```

   If it still says no verified match, open the new thumbnail, copy its
   `https://flow.google.com/project/37d8cf57-…/edit/<id>` URL and add `--asset-url <url> --asset-reviewed`.
   The same download is available in the Queue panel under
   *"Recover a visually reviewed video if its old fingerprint no longer matches"*.
3. **Resume** — from the UI is fine now, because the shot is downloaded and the manifest knows it. Resume will
   continue from shot_014 to the remaining shots.

Resuming **before** the clip exists is what would put you back in the loop you were in.

## What 7.0.100 changes

| Piece | Behaviour |
|---|---|
| `engine/job_ref.py` (new) | `normalize_job_id()` accepts `2026…`, `outputs/2026…`, `outputs/2026…/`, `./outputs/2026…`, `outputs/outputs/2026…` (the mistake itself), `C:\…\outputs\2026…` and any absolute path to the job folder |
| Wrong id | `job_lookup_error()` says commands take the **bare** id, explains why `outputs/<id>` becomes `outputs/outputs/<id>`, and lists the jobs that do exist (or suggests `--outputs-root` when none are found) |
| CLI | every command with a job id normalizes it first — and never blocks an offline command on a reference it cannot resolve |
| `recover-flow-video` | a missing production now raises that message instead of `FileNotFoundError` from inside the loader; the "no downloadable video" message names the queued/high-demand case and says waiting costs no credits |

## Tests

`tests/test_v7100_job_reference.py` — 18 tests: every accepted reference shape (bare, trailing slash, `outputs/`,
`outputs/outputs/`, `./outputs/`, Windows path, absolute path, quoted path), the typo path and its message, an
empty outputs folder, an empty reference; the CLI handing the Factory the bare id for `recover-flow-video` and
`approve-request`; the CLI never blocking an unresolved reference (offline commands keep working); the Factory
reporting an unknown job as a message rather than a traceback; and the queued-generation wording.

`tests/test_cli_content_commands.py` (the offline CLI suite that caught my first, too-strict version) passes
unchanged.

## Install

1. Stop the dashboard (all tabs).
2. Extract `AutoVideoAI-v7.0.100-Job-Reference.zip` beside your installation.
3. From inside the installation folder:

   ```
   python3 ../AutoVideoAI-v7.0.100/tools/update_v799_to_v7100.py .            # dry run
   python3 ../AutoVideoAI-v7.0.100/tools/update_v799_to_v7100.py . --apply    # installs the code
   ```

   Accepts an installed 7.0.99 (or an already-updated 7.0.100), backs replaced files up under
   `code-update-backups/v7.0.99-to-v7.0.100-<timestamp>`, and never touches outputs, jobs, Flow journals,
   browser profiles or Clip Studio folders.

You do not need 7.0.100 to make progress: the bare-id command above works on the version you have.

## Not verified live

No Flow project was opened and no credit was spent here. The reference handling, the messages and the queued
wording are covered by tests; whether the queued clip has appeared can only be settled by looking at the
project.

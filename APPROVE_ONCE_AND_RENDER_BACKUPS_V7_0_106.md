# v7.0.106 — one approval per Flow video, and the rendered video is never lost

Two requests from the same session.

## 1. "Approve each video request once — not the first one only, and never 'Always approve'"

Every Flow video request is a separate credit card, and the app was only reliably clicking the first one. The
rest waited for a human, so a job with eight Flow videos needed seven manual clicks (and, after a pause, a
manual `approve-request` before Resume could do anything).

The rule is now enforced **per saved request**, from files rather than from session memory:

| Situation | What happens |
|---|---|
| a saved video request, card visible, cost readable, within the per-take cap | **one** Approve click, recorded, then the (free) download |
| the same request again — a re-rendered card, a new browser, a resumed job | **never clicked**; the video it already paid for is waited for |
| card cost above `max_generation_credits` (default 10) | nothing clicked, the reason is written |
| cost not readable, or no clickable card | nothing clicked, the reason is written |
| `flow_approval = manual` | nothing is ever clicked for you |
| the only visible control is "Always approve" | never used |

Where it clicks:

- **while generating** — the existing wait now also writes its one click into the request journal
  (`approval_clicks`, `approval_cost`, `approval_label`) and into `<job>/flow_approvals.jsonl`;
- **on Resume** — `reconcile_job` approves the saved request's own card once before the download-only wait
  (this is the path that used to stall: "no approval click is recorded … every scan finds nothing");
- **on an automatic retry** — the retry loop now reconciles the saved request (approve once + download) instead
  of restarting the whole run into the same blocked journal;
- **`cli.py v3 recover-flow-video … --auto-approve`** — same rule, on demand.

`python3 cli.py v3 status <job>` and the Job panel now show `flow_approvals:` (each click, its cost and
`1/1`), which saved requests are still waiting for a card, and whether automatic approval is on for the job.
Turn it off for one job with `"flow_auto_approve_video_requests": false` in `settings.json`, or with
`"flow_approval": "manual"` for no automatic click at all.

## 2. "Where does the rendered file go when a job is cleaned up?"

**Nowhere — it was deleted.** The completed-job deletion moved the folder into `outputs/.deletion-quarantine/`
and then removed it; the Clip Studio cleanup unlinked its clips. Neither kept the video.

v7.0.106 moves rendered videos out before anything is deleted:

```
<outputs>/_render-backups/<job id>/<file>.mp4        finished job videos (permanent deletion)
<clips folder>/_render-backups/clips/<stamp>/*.mp4   Clip Studio clips (Clip Studio cleanup)
```

- the move is a rename inside one filesystem (instant, no extra space); across filesystems the bytes are
  copied, hashed and verified before the original is removed;
- if the backup cannot be verified, **the deletion is refused** and nothing is removed;
- an identical backup already present is recognised (no duplicate copies);
- the location is configurable: `AUTOVIDEO_RENDER_BACKUP_DIR` (absolute; another disk is fine) or the
  `render_backup_dir` setting;
- `python3 cli.py v3 backups` lists what is kept; `python3 cli.py v3 backups --restore <job>` copies a job's
  videos back to `outputs/<job>/render/` (the production itself is not recreated);
- the Job panel shows the exact folder before deleting and the kept path afterwards; the Clip Studio cleanup
  has "Keep the rendered clips" ticked by default (`keep_clips=False` still deletes them outright).

## Files

- `engine/flow_approval_once.py` (new) — `plan()`, `record_click()`, `clicks_for()`, `auto_allowed()`,
  `approve_saved_video_request()`.
- `engine/render_backup.py` (new) — `backup_root()`, `plan()`, `backup_files()`, `restore()`, `inventory()`.
- `engine/providers/flow_browser.py` — the strict one-click budget before any click; each click recorded.
- `engine/flow_resume_recovery.py`, `engine/automatic_recovery.py` — approve the saved card once, then download.
- `engine/factory.py` — `recover_flow_video(auto_approve=True)`, approval state for the panel.
- `engine/job_delete.py`, `engine/clip_cleanup.py`, `app.py`, `cli.py` — keep videos, `v3 backups`, UI.
- `tests/test_v7106_approval_and_backups.py` — 33 tests, no browser, no credits.

## Honest limits

- Nothing here was exercised against live Flow; the card probes, clicks and duplicate guards are covered by
  fakes. No credits were spent.
- A request that Flow never approved (e.g. the account is out of credits) still cannot produce a video; the
  refusal is reported instead of retried.
- The backup keeps the **rendered file**, not the production: journals, takes and the manifest stay in the job
  folder, which is deleted. Restore copies the video back and says so.

## Upgrade

```
python3 ../AutoVideoAI-v7.0.106/tools/update_v7105_to_v7106.py .            # dry run
python3 ../AutoVideoAI-v7.0.106/tools/update_v7105_to_v7106.py . --apply    # install
```

Stop the dashboard first. Outputs, saved jobs, Flow journals, browser profiles and Clip Studio folders are
never copied, moved or deleted by the updater; code backups go to
`code-update-backups/v7.0.105-to-v7.0.106-<timestamp>`.

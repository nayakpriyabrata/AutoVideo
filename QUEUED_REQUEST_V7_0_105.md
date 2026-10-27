# v7.0.105 — a paid Flow request is waited for, not abandoned

Real log, job `20261022-143856-7-small-daily-habits-tha-9729`, 2026-10-27. Two Flow videos were produced
(`shot_018`, `shot_020`); the app kept only the first, then spent ten minutes rescanning the same gallery and
paused with "no single identifiable asset".

```
11:18:58  exact UI blob saved: shots/shot_018/take_01.mp4            ← recovered, good
11:19:12  shot_020 take 1/1 via flow/omni_draft
11:21:03  Could not attach Agent reference media: … no verified composer attachment appeared within 45s
11:21:14  Automatic Flow recovery shot_020: retry 1/20               ← whole run restarts at 1%
11:22:50  Reused existing project media: AV_a4e5d83d2775_shot_020_open.jpg   ← the upload had landed
11:22:53  Credit confirmation: clicked 'Approve' (6 credits)
11:22:54  … still scheduled in the high-demand queue … remaining=899s
11:23:27  Approval stopped: Additional approval card exceeds the saved request approval-card limit
11:23:27  Approval refused … No card was clicked; the wait ends now  ← walks away after 29 seconds
11:23:28  FlowRequestPending … (last observed interval 29s)
11:24:37  Download-only recovery … 6 gallery assets, 0 fresh candidates
…         retries 3, 4, 5 → 11:33:52 PAUSED flow_recovery_exhausted
```

Three separate defects, all fixed here.

## 1. The second approval card ended a wait for a request that was already paid for

Flow re-renders the approval turn after a request is queued (and the Agent asks again while the clip is still
generating). The approval guard saw a card that was not in the saved request's reservations and treated it as a
hard stop, ending the wait after 29 s while the request it had just approved still had ~870 s of queue left.

- `engine/flow_approval.py` now raises a typed `ApprovalCardLimitReached` (still a `ValueError`, with `.cards`
  and `.limit`) instead of a bare error, and `wait_decision()` states what the wait does next:
  `continue`, `keep_waiting` or `stop`.
- When at least one card for this request is already approved, the additional card is **never clicked** and the
  wait **continues** for the video that was paid for. Approval probing stops for that request so the same card is
  not re-read every two seconds.
- A card that would exceed the credit cap, a manual-approval request, and a card with no approval yet still stop
  the wait as before: nothing is clicked and nothing is submitted.

Console: `This request was already approved; the additional card is left unclicked. Continuing to wait for the
video that was already paid for (no new credits).`

## 2. A queued request is no longer counted as "no progress"

`automatic_recovery` stopped after four no-progress retries (five scans, ~10 minutes), while Flow's high-demand
queue had advertised 899 s. A submitted request that is still queueing is not stagnation:

- `still_queued()` recognises the queue verdict from the saved request;
- such retries are exempt from the four-attempt no-progress budget inside a 1 500 s wall-clock budget (the total
  attempt bound of 20 and the browser/upload bound are unchanged);
- queued retries back off at 30/60/90 s instead of hammering every 10 s;
- `automatic_recovery.json` records `"queued": true` per attempt.

## 3. An upload that lands late is attached instead of failing the shot

`shot_020`'s first attempt failed the composer check after 45 s, yet the very next attempt found both files in
the project with "Reused existing project media" — the upload had succeeded and only the chip verification was
slow.

- the composer check now waits **90 s** (`REFERENCE_ATTACH_TIMEOUT_MS`);
- if it still fails, the same alias is attached from the project's uploaded media once, and the shot continues —
  no failed shot, no extra submission cycle;
- if the file really is absent, the existing honest error remains ("The photo exists locally; Flow
  upload/attachment needs recovery. **No generation submitted.**").

## 4. The console guidance now shows the current pause, not the stale snapshot

`python3 cli.py v3 status` printed the saved snapshot verbatim: `shot_014 … FlowRequestPending` and
`completed=13/45` while the manifest had 17 accepted shots and the production had stopped at shot_018. It now
prints `Factory.recovery_state()` through `pause_guidance_lines()` — the current stopping point, the superseded
notice marked as superseded (the old text kept), `completed=N/M (manifest)` and the unresolved journals that
Resume will keep waiting on.

## What this does not do

- It never clicks a card that is not part of the request already approved, and it never submits a generation to
  "retry" a download.
- It cannot fetch a clip that Flow never produced: if the queue ends without a video, the pause names the saved
  request and the download-only recovery command.
- Nothing here was run against live Flow; the tests use fakes and spend no credits.

## Files

- `engine/flow_approval.py` — `ApprovalCardLimitReached`, `wait_decision()`.
- `engine/providers/flow_browser.py` — the wait keeps waiting after a refused extra card; 90 s attachment check
  with the project-media fallback.
- `engine/automatic_recovery.py` — `still_queued()`, queue grace, longer queued backoff, `queued` in history.
- `cli.py` — `pause_guidance_lines()`, used by `v3 status`.
- `tests/test_v7105_queued_approval.py` — 21 tests, no browser, no credits.

## Upgrade

```
python3 ../AutoVideoAI-v7.0.105/tools/update_v7104_to_v7105.py .            # dry run
python3 ../AutoVideoAI-v7.0.105/tools/update_v7104_to_v7105.py . --apply    # install
```

Stop the dashboard first. Outputs, jobs, journals, browser profiles and Clip Studio folders are untouched; code
backups go to `code-update-backups/v7.0.104-to-v7.0.105-<timestamp>`.

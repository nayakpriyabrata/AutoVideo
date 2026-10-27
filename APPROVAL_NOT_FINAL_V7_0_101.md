# AutoVideoAI 7.0.101 · "no approval click recorded" is not "no video exists"

You are right, and the app was wrong to state it. Two things I said last round were based on reading the chat
text as the project state:

- *"the card was never approved, so no video exists"* — you approved it **in the Flow UI yourself**, and that
  click is not visible to the app (only the CLI path writes an approval line to the take ledger).
- *"wait for the queue"* — that chat turn is written when Flow accepts the request and **stays in the chat
  afterwards**. In your project it is a leftover while the clip was already finished a minute later.

What actually happened in your terminal is simpler than either: **your recovery command never reached a
browser.** The traceback was at `load_manifest`, before any `[Flow] …` line, because the job reference was
`outputs/…` and the app prefixes `outputs/` itself (fixed in 7.0.100). The video was there the whole time.

## Do this now (bare job id — the app adds outputs/ itself)

```
cd /mnt/c/Users/eiyanpr/Downloads/Auto/AutoVideoAI-v7
python3 cli.py v3 recover-flow-video 20261022-143856-7-small-daily-habits-tha-9729 \
    --shot-id shot_014 --wait-seconds 180
```

Because that clip was created *after* the request was submitted, it counts as a fresh asset, so automatic
matching should now find it (the earlier `0 fresh candidates` scan ran before it existed). Expect a `[Flow]`
browser launch, then the download, then QC.

If it reports `no verified match`, the exact video is in the project you screenshotted — click the clip so the
address bar shows `…/project/37d8cf57-12b4-4a85-9934-5580e90d3781/edit/<asset-id>` and run:

```
python3 cli.py v3 recover-flow-video 20261022-143856-7-small-daily-habits-tha-9729 \
    --shot-id shot_014 --asset-url https://flow.google.com/project/37d8cf57-12b4-4a85-9934-5580e90d3781/edit/<asset-id> \
    --asset-reviewed
```

(The same box exists in the Queue panel, *"Recover a visually reviewed video if its old fingerprint no longer
matches"*.) Then Resume — UI is fine, the shot is saved and the manifest knows it.

## What 7.0.101 changes (wording that must not mislead)

| Where | Before | Now |
|---|---|---|
| Blocked-Resume message | "that card was never approved and no video exists yet" | "no video exists **until** that card is approved … if you have already approved it in the saved project (the clip, or a queued note, is there), skip this: download the video first, it is free" |
| Queue panel warning | "Flow is probably still waiting … until that card is approved no video exists" | "no approval click is **recorded** … if you approved it in the Flow UI yourself, this note is stale — the clip may already be in the project, and downloading it costs nothing … run the free download first" |
| Panel next action | "…so no video exists yet and another wait cannot find one" | "Either Flow is still waiting on the card … or you approved it directly in the Flow UI, where the click is not recorded here … Run the free download first" |
| `recover-flow-video` with nothing found | "If the saved project says the generation is queued because of high demand, there is nothing to download yet: wait" | "A chat turn that says the generation is queued … is a **snapshot from when it was submitted** and can stay in the chat after the clip is finished … check the project's media grid … download exactly it with `--asset-url … --asset-reviewed`" |
| Preflight tool | "Flow is probably still waiting on its Approve/Reject card" | same, plus "If you approved it in the browser yourself the click is not recorded here — download the video first (free); only approve if the project has no video" |
| Approval evidence | "…so Flow is probably still waiting" | "…or the card was approved directly in the browser (that click is not recorded here)" |

The order of advice is now: **download (0 credits) → approve (credits) only if the project really has no video →
replacement (paid) last.** That is the order it should always have had.

## Tests

`tests/test_v7101_approval_not_final.py` — 8 tests:

- the evidence still flags a missing click but says a browser approval is invisible to it;
- the blocked message says "no video exists **until** that card is approved", tells a user who already approved
  to download first, and still lists both commands (approve before recovery in the text, as an option);
- the preflight keeps `no approval click is recorded` and adds the unrecorded-click explanation and
  `download the video first (free)`;
- the queued chat note is described as a snapshot, points at the media grid, and names `--asset-url`;
- the no-video error says nothing was submitted, names the media grid, and offers `--asset-reviewed`;
- the panel note carries the "stale" explanation and "run the free download first";
- the panel's next action says "Either Flow is still waiting … or you approved it directly in the Flow UI"
  and still hands over the recovery command.

`tests/test_v799_approval_pending.py` was updated for the corrected sentence (the behaviour it pins — a missing
click is reported — is unchanged).

## Install

1. Stop the dashboard (all tabs).
2. Extract `AutoVideoAI-v7.0.101-Approval-Not-Final.zip` beside your installation.
3. From inside the installation folder:

   ```
   python3 ../AutoVideoAI-v7.0.101/tools/update_v7100_to_v7101.py .            # dry run
   python3 ../AutoVideoAI-v7.0.101/tools/update_v7100_to_v7101.py . --apply    # installs the code
   ```

   Accepts an installed 7.0.100 (or an already-updated 7.0.101), backs replaced files up under
   `code-update-backups/v7.0.100-to-v7.0.101-<timestamp>`, and never touches outputs, jobs, Flow journals,
   browser profiles or Clip Studio folders.

The recovery command above works on the version you already have; install this so the panel stops insisting a
video is missing while you are looking at it.

## Not verified live

No Flow project was opened and no credit was spent here. I cannot see your project, so I cannot promise the
automatic match will succeed — only that a fresh clip is what it looks for, and that `--asset-url` downloads
the exact video you point at.

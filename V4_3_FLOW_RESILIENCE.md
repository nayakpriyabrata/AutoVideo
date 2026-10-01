# v4.3 — Flow UI Resilience, Auto-Done, Auto-Approve & Network Recovery

This build targets the Sep-2026 Google Flow Agent UI observed in real runs.

## Fixes

### 1. Image editor no longer requires manual **Done**
Flow opens generated stills under `/project/.../edit/<asset>`. v4.2 could leave the browser in that editor, so the next Agent prompt was sent into the wrong UI. v4.3 downloads the image and automatically clicks **Done** (with Back/history fallback), then verifies the project composer before continuing.

### 2. Current Flow download menu is supported
The toolbar download icon now opens a quality menu. v4.3 deliberately selects **1K / Original size** for storyboard/reference frames, downloads it, saves it to the job folder, and returns to the project. This avoids paid/slow upscale steps while building the storyboard.

### 3. Credit approval works with non-semantic Flow rows
Flow may render **Approve / Always approve / Reject** as clickable rows rather than normal HTML buttons. v4.3 tries semantic buttons first and exact visible-text controls second. `--flow-approval once` clicks only **Approve**. It never selects **Always approve** unless explicitly requested.

The per-generation credit guard remains active. A visible confirmation that cannot be approved is now treated as BLOCKED instead of silently continuing to the next step.

### 4. Temporary Internet loss pauses instead of wasting the job
New defaults:

- `--flow-frame-retries 3`
- `--network-wait-seconds 300`

When a browser/Flow network error is detected, AutoVideoAI pauses, waits for connectivity, reloads/recover the Flow session, returns from an editor if needed, and retries the SAME frame without counting the outage as a normal generation retry.

If strict `--frame-source flow` still cannot recover, the job returns `status=paused` with a resume command instead of losing completed frames.

### 5. Resume remains incremental
Every successfully downloaded opening/closing frame is cached. Resume skips files that already exist, so a long 49-scene production does not restart image generation from scene 1.

## Recommended real-run command

```bash
python3 cli.py v3 create \
  --topic "How AI agents will change work" \
  --type faceless_youtube \
  --duration 300 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 50 \
  --video-share 0.18 \
  --stock-share 0.20 \
  --max-flow-scenes 6 \
  --shot-max-seconds 8 \
  --frame-source flow \
  --flow-approval once \
  --max-generation-credits 10 \
  --flow-frame-retries 3 \
  --network-wait-seconds 300
```

Expected new terminal messages include:

```text
[Flow] Returning from image editor to project...
[Flow] Credit confirmation: clicked 'Approve' (7 credits)
[Flow] Network interruption detected; waiting up to 300s for recovery...
[Flow] Network restored; browser session recovered.
```

For a paused job:

```bash
python3 cli.py v3 resume <JOB_ID>
```

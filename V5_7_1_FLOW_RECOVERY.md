# AutoVideoAI v5.7.1 — Flow recovery and pause UX

This maintenance release protects work already produced in Google Flow.

## Fixed

- Detection and download now use the same image/video asset signature.
- Video download menus can select 1080p, 720p, 360p, MP4, or original variants.
- A delayed first-project `Approve`/`Approve once` prompt is detected during the wait.
- `flow_approval: once` still refuses persistent `Always approve` unless requested.
- The first Flow project URL is persisted before sequential or parallel images continue.
- All parallel image workers open the same canonical project URL.
- “You've reached your usage limit” stops immediately instead of entering capacity retries.
- Capacity waits show wall-clock timestamp, elapsed time, and next retry time.
- TTS model-terms errors are circuit-broken after the first failure in a run.

## Recover an existing video without generating again

```bash
python3 cli.py v3 status <JOB-ID>
python3 cli.py v3 recover-flow-video <JOB-ID> --shot-id <SHOT-ID> --wait-seconds 120
python3 cli.py v3 resume <JOB-ID>
```

The recovery command only scans/downloads existing media from the job's saved Flow
project. It never submits a generation prompt and records `new_credits: 0`. A
v5.7.1 pause stores the pre-generation media baseline, so only a proven-new tile is
eligible. For older pauses without a baseline, automatic recovery refuses to guess;
use manual association or `--allow-latest` only after visually confirming the tile.

Studio shows the same recovery action on every actionable paused job and keeps the
manual MP4 association path as a fallback.

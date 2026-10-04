# AutoVideoAI v6.0.16 — Flow video tile recovery

## What changed

- A fresh, explicitly typed Flow video tile no longer has to wait for the *entire Agent conversation* to become idle. Flow leaves old `pending`/`generating` status text in conversation history; that page-wide text could block an already-visible video tile until the 900-second generation timeout. AutoVideo now waits for the exact new tile to remain stable briefly, then attempts its exact-signature download and validates the resulting video.
- If the tile is visible but the file is not yet playable/downloadable, recovery remains bounded and download-only. The saved request stays available for explicit Resume; AutoVideo does not submit a replacement video generation or weaken asset identity checks.
- Flow failure progress and job logs now retain the provider's concise recovery cause instead of showing only a generic unresolved-request message. Missing-image replacement diagnostics show a safe filename/detail without printing a user-specific full path.
- v6.0.15's Storyboard Economy features are included: **Parallel Flow image workers** (choose 1–3; start with 2 to reduce serial still-generation time) and **Flow video input** (`Storyboard frames` or `Prompt only`). Parallelism applies only to independent stills; video generations remain sequential, and continuity-linked opening/closing frames stay paired.

## Diagnosis of the reported run

The supplied run was launched from **v6.0.14**, which predates the visible worker selector. Its repeated still-generation/recovery work therefore did not use the v6.0.15 parallel-worker option. The log then shows a video tile around `+04:37:50`, approval for 4 credits, and unresolved failure around `+04:52:50`—almost exactly the configured 900-second generation timeout.

The old wait used page-wide `pending`/`generating` text as a reason not to accept the detected tile. If stale status text remained elsewhere in Flow's conversation, AutoVideo could wait out the full timeout even though a fresh typed tile existed. The log does **not** prove the tile was playable or that a download completed, so this is a code-path diagnosis, not confirmation of what Google's live UI did. v6.0.16 proceeds to exact-asset download/validation sooner; if that still fails, it reports the recovery cause and keeps the paid request protected from duplicate generation.

## Safely continuing the existing job

Do not click **Generate** in Flow or start a second paid request for the affected shot. Preserve the whole job directory and its hidden request/recovery sidecars before upgrading. Install v6.0.16, carry over the job folder, `data/jobs.db` if you need job history, local configuration, and the existing signed-in Flow browser profile. Keep the v6.0.14 installation until the existing job and output are verified.

Before resuming, inspect the backed-up job locally and confirm the failed shot still has its video request sidecar (typically `take_01.mp4.flow-request.json`) with `kind: video` and a pending/unresolved status. If that sidecar is missing or its identity is unclear, do **not** Resume yet—the app could have no durable record to guard against a new submission. Once the matching request sidecar is present, use the explicit **Resume** action in v6.0.16: it checks the saved Flow project and exact asset download-only first; if Flow still has no exact completed video, the request remains unresolved rather than silently submitting another clip. Do not copy in a different MP4 or still as a substitute.

For new Storyboard Economy runs, set **Parallel Flow image workers** to 2 initially. If Google Flow throttles or the browser session is unstable, return to 1. Choose **Prompt only** when you want the paid Flow clip generated from its prompt without attaching storyboard stills; the stills remain available for image-motion scenes and fallback. Choose **Storyboard frames** for frame-guided continuity.

## Validation

The focused Flow-recovery, worker/continuity, and failure-diagnostic tests pass. The full offline suite has 568 passed and 5 skipped; 8 unrelated clip/B-roll tests require the system `ffprobe`/`ffmpeg` commands, which are unavailable in this environment. No live Flow account/browser test was performed, so real-time queue/download behavior remains dependent on Google's UI and account.

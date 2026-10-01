# v4.9 — Stable Flow session + cross-version project reuse

## Why this release exists

Two separate behaviors were being confused:

1. Flow can close/replace the active media-editor page after a generated asset is opened/downloaded.
2. Extracting a new AutoVideoAI release creates a new local `data/` and `outputs/` tree, so the old exact frame cache is no longer visible even when the same Google Flow project URL is reused.

## Browser/session changes

- Keeps a stable guard project tab alive before risky media-editor/download actions.
- Recovers a closed page inside the existing browser context first.
- Does **not** restart the whole browser merely because one Flow page target closed.
- CDP-attached Chrome contexts are never closed by `FlowBrowser.close()`.
- A full browser relaunch is now a last resort only when the browser context itself is dead.
- If a Flow request appears to have generated a video but detection/download fails, AutoVideoAI scans the newest project assets and validates them as real video before spending another generation or falling back.

## Reuse changes

- Canonical Flow-project frame cache moved to `~/.local/share/autovideoai/flow_project_cache/` (or `AUTOVIDEO_FLOW_CACHE_DIR`).
- Old per-release `data/flow_project_cache/...` folders are automatically imported.
- New `--flow-reuse-mode`:
  - `exact`: exact prompt fingerprint only.
  - `topic` (default): exact first, then same Flow project + same topic + same shot role from current/sibling AutoVideoAI release folders.
  - `project`: also permits same shot role reuse across topics in the same project; use only for intentionally shared visual projects.
- Previously accepted Flow videos can be reused from older local jobs when the project/topic/shot matches.

## Important distinction

`v3 resume JOB_ID` always continues one existing AutoVideoAI job.
`v3 create --flow-project-url ...` creates a new AutoVideoAI job inside an existing Google Flow project. v4.9 now reuses same-topic media much more aggressively, but a new job can still have a different script/shot plan.

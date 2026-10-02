# v6.0.1 — Automatic Flow image download recovery

## Changed
- Retry saved image downloads up to three times automatically, recovering the same project/browser before each retry. Each attempt is logged.
- If a visible/enabled Download control fails specifically because its Angular animation is unstable, retry that download control with the stability check bypassed. Generation controls never use this fallback.
- One automatic replacement image per output is permitted only after recovery fails, the original request is at least six minutes old, its identity/project/prompt match, and two project scans 30 seconds apart show the saved baseline but not the target. Empty, incomplete or generating galleries do not qualify.
- Replacement can use image credits. The original request is retained in `.flow-request.before-regeneration.json`; this durable reservation prevents repeated regeneration across Resume/restarts. Never delete these journals to force retries.
- Video generation protections remain unchanged. Exhausted recovery, login/quota problems and ambiguous assets can still pause; retries are not infinite.

## Upgrade an existing WSL job
1. Stop the dashboard with Ctrl+C and back up your current folder.
2. Extract the v6.0.1 ZIP to a new folder.
3. Copy your `outputs/`, `data/`, local `.env`, `config/user_settings.yaml` (if present), and browser profile folders from the old installation to the new one. Keep those files private. Alternatively copy updated source files into your backed-up existing installation without replacing runtime folders.
4. Install requirements in your environment, then run `./dashboard.sh`.
5. Select your existing job and click Resume once. Do not create a new job. Subsequent image-download retries happen automatically.

## Limits and testing
Offline regression suite: 464 passed, 5 skipped. No live authenticated Flow/WSL session was available here: this is a recovery fix for testing, not a guarantee that every current Flow download UI works. If it still pauses, share the redacted support report and recent retry logs.

Advanced integrations may set compiled `flow_image_auto_recover: false` to retain download-only manual recovery or `flow_image_auto_regenerate: false` to disable automatic replacement. These are provider-level controls, not dashboard settings.

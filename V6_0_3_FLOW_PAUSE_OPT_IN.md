# v6.0.3 — Flow recovery pauses are opt-in

## What changed

- Unresolved Flow image requests no longer pause jobs by default. In `frame_source=auto`, AutoVideoAI keeps the exact-signature download retries and bounded missing-image recovery, then uses the configured free image fallback if Flow still cannot identify the asset. The unresolved Flow request is archived for audit; a different Flow tile is never substituted.
- A signature-less request is only bound to a gallery asset when polling finds exactly one distinct, typed image newer than the saved baseline. A one-time image replacement is still limited to requests older than six minutes and two successful full-baseline scans proving that no new media appeared. It may use image credits and remains subject to Flow's approval safeguards.
- Strict Flow image requests and unresolved video downloads report failure rather than entering PAUSED status unless the user opts in. Pending video requests retain their journal and are not resubmitted automatically.
- Pause behavior is selectable per new job, as the global Settings default, or for an existing job in Queue → Flow recovery behavior. CLI users can pass `--pause-on-unresolved-flow-request` or `--no-pause-on-unresolved-flow-request` to `v3 create` or `v3 resume`.

## Validation

- Offline regression suite: **476 passed, 5 skipped**.
- CLI help, source compilation, archive CRC, and release-manifest checks pass.
- No authenticated Google Flow session was available for a live browser/account test.

## Upgrade note

Keep existing `outputs/`, `data/`, `.env`, `config/user_settings.yaml`, and browser profiles private and preserve them when upgrading. Do not discard a pending `.flow-request.json` or create a duplicate job to work around it. For an existing job, choose its recovery behavior in Queue before resuming. With pause off, automatic free fallback applies only to `frame_source=auto`; strict Flow jobs fail without pausing and can be explicitly resumed.

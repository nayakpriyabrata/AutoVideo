# AutoVideoAI v6.0.6 — Flow resume safety and diagnostics

## Fixes

- In CDP-attached Chrome, normal Flow work now reuses an already-open Flow tab, reuses one blank tab if necessary, and opens at most one persistent dedicated Flow tab instead of opening/closing a fresh tab on each reconnect. Unrelated tabs are left untouched; isolated parallel-worker tabs retain their previous lifecycle.
- Reconnection preserves the current `flow.google.com` project route instead of navigating to Flow home first.
- If the exact saved project tab is alive but its composer is still loading, recovery no longer opens another tab on every Resume poll. Existing matching guard tabs are reused.
- Flow recovery errors now distinguish **video** and **image** requests. Video failures include the provider's concise failure detail when available and explicitly say not to associate a different MP4 or click Generate again. The failed request remains download-only until it is safely recovered.
- A long-form render stopped by Coverage QC now shows the saved issues and unaccepted shot statuses in the dashboard. This is a read-only review panel; it does not approve a shot, alter a take, or submit another generation.

## Existing v6.0.5 mini-reel request

The reported message `Submitted Flow request has no validated local asset` means the browser provider did not produce a locally validated/downloaded clip. It does not prove whether Flow failed to generate or whether a completed Flow asset is merely not matched/downloaded. The saved recovery diagnostic is needed to distinguish those cases.

For reel ID `20261002-123755-a7be7df2`:

1. Keep the original v6.0.5 installation's `outputs/mini_reels/20261002-123755-a7be7df2/` directory intact.
2. In that same installation, open **MINI REELS → Recover a saved Flow request → Recover exact saved Flow video**. This retries the saved request's download path only; it does not submit a new prompt.
3. If recovery still cannot identify the exact video, stop retrying. Open the saved `flow_project_url` from the reel metadata in Google Flow and confirm whether the generated clip is present. Do not substitute another MP4 or start a new request until the pending request is resolved.

A new install pointed at a different output folder will not automatically see the old journal. Preserve the existing output path when upgrading or perform recovery from the original installation.

## Separate long-form Coverage QC stop

`Coverage QC: shot_003: shot is not accepted` is a separate safety stop. The renderer correctly refuses to use a rejected/unaccepted shot even if a file exists. The dashboard now lists the report issues and current non-accepted shot statuses; inspect `outputs/<JOB-ID>/render/coverage_qc.json` and review that shot in STORYBOARD or DIRECTOR REVIEW before rendering the same job again. This release does not auto-accept the shot or generate replacement media.

## Verification and limits

- Added deterministic tests for CDP tab reuse, preserving the existing project route, not spawning duplicate tabs while the saved project is still loading, and video/image-specific failure diagnostics.
- Full offline test-suite results are recorded in the release notes.
- The user's Windows/WSL Chrome session, current Flow project, pending video, and the specific `shot_003` Coverage QC report are not available in this sandbox, so the live account failure itself has not been reproduced. Keep the saved Flow request and QC report for diagnosis; never share `.env`, browser profiles, cookies, or raw signed media URLs.

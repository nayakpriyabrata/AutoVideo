# AutoVideoAI v5.3.3 — Live Flow Recovery

This release fixes the recovery loop that could print "waiting up to 179s" while no usable Flow browser/project page was active.

## Changes

- A recovery wait now requires a live browser context and the canonical `/project/<uuid>` page.
- If the Flow page/context is gone, AutoVideoAI reopens/rebuilds it immediately before continuing the wait.
- Headed recovery brings the Flow project page to the foreground so the operator can see that recovery is active.
- Recovery polls only the project media grid and waits for an explicit video tile. It no longer opens untyped poster/image cards during polling.
- The terminal prints a recovery heartbeat every ~15 seconds with browser/project state, fresh media count, video-tile count, and remaining time.
- A failed project reopen aborts after three attempts instead of silently sleeping for the entire timeout.
- A submitted Flow request gets one recovery window. Nested provider/factory 179-second recovery loops were removed.
- Before a factory retry can submit another generation, the provider performs a short final scan for the previous request's completed video.

These changes are intended to prevent hour-long stalls and duplicate Flow generations when the original video already exists in the project.

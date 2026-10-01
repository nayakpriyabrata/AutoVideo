# v4.8.2 — Stale Agent failure isolation + non-critical frame resilience

## Fixes

1. **Old Flow Agent failure cards no longer poison later image requests.** Before each Agent submission AutoVideoAI snapshots the existing failure-text counts. `detect_failure()` only treats a newly-added failure occurrence as belonging to the current request, and a newer progress marker wins over an older failure card.
2. **A non-video STORYBOARD_ECONOMY scene no longer pauses the whole job when only its closing still exhausts all Flow retries.** The already-generated Flow opening frame is reused as the emergency closing frame. The selected paid Flow-video scene remains strict and still requires a usable/distinct frame pair.
3. v4.8.1 download/page-close recovery remains unchanged.

This specifically addresses resumes that successfully generate many frames and then pause late in the storyboard with `Flow Agent image generation did not reach a detectable completed asset`.

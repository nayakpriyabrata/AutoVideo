# AutoVideoAI v6.0.17 — Flow gallery tile recovery

## What changed

Flow can display a provisional “scheduled / waiting in a high-demand queue” message in the Agent chat and then add a completed video to the project gallery without posting a second completion message. Earlier recovery code mixed broad ancestor/chat text with gallery-tile classification, so that queue sentence could make a separate gallery video look pending.

v6.0.17 scopes queue-status detection to the nearby media card and uses tile-local labels for classification. A separate generated gallery tile with explicit video evidence can therefore be recovered even while the chat still contains the old queue sentence. Download still requires a fresh, typed asset that matches the saved request's baseline and signature rules; if identity is ambiguous or the asset does not validate, recovery fails safely without submitting another paid generation.

## Continuing the existing job

The v6.0.16 log confirms that the saved job/request was copied successfully and that the exact Flow project opened. The screenshot's queue sentence alone is not proof that the gallery lacks a completed clip. Preserve the updated v6.0.16 job folder—including the video request journal and recovery sidecar—then copy that whole job folder to v6.0.17 if installing into a new directory. Do not recopy the older v6.0.14 job over it, because that would replace newer recovery diagnostics.

Resume the same job in v6.0.17. It checks the existing request and attempts download-only recovery; it does not click Generate. Do not manually associate another MP4, and do not submit a replacement request. If the gallery has more than one plausible fresh video or none can be tied to the saved request, the app will keep the request unresolved rather than choose by tile order.

## Validation

Offline regressions cover a separate/stale chat queue message alongside a completed gallery tile, a genuinely queued thumbnail, exact request recovery, and duplicate-generation protection. Live Google Flow/DOM behavior was not available for testing in this environment.

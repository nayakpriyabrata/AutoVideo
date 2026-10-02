# v6.0.9 — Flow video type and recovery repair

## Reported failure

A long Storyboard Economy job reached a pending Flow Agent video request at `shot_017`. The project exposed fresh image media but no explicit video tile; an earlier readiness fallback could then attach the still's signature to the video request. Strict MP4 validation prevented the still from being accepted, but that wrong signature could make later Resume look only for the still. The job also recorded repeated `Download.save_as` target-closed errors for storyboard images.

## Fix

- Flow Agent video preparation now selects **Video** in the visible generation-type picker before sending the prompt. If the picker is visible but the Video option cannot be selected, the prompt is not submitted. The image Agent path likewise selects **Image** when that picker is available.
- A fresh image/poster is no longer promoted to a completed video when the readiness grace expires. Video completion requires an explicitly typed video tile, a short stability period, and the existing strict container/duration validation.
- Video-tile recognition includes Flow's Material `play_arrow`/`smart_display` controls, resolution badges, and video labels, in addition to actual video elements and media URLs.
- Download-only Resume now disqualifies a journal signature whose encoded kind is `image` for a pending `video` request. It preserves the rejected signature for audit and scans only for one unique, post-baseline video. If no such video is visible, the request remains pending; no new credit-bearing video is submitted and no image is downloaded as a substitute.
- If an image download's `save_as` fails after the media-viewer target closes, recovery now tries the exact UI-triggered download's temporary file and then its signed download URL. The URL is not logged, bytes are bounded and image-validated, and video downloads do not use this image-only fallback.

`flow_video_ready_grace_seconds` is now a diagnostic threshold for continued image-only/untyped media, not permission to treat a still as a video. The standard generation timeout and the existing bounded recovery/retry settings remain in force.

## Verification

- Flow regression tests cover explicit Agent mode selection, still-only timeout behavior, waiting for a later typed video, Material-icon classification, image-signature repair on Resume, no-download/no-regeneration when only a still exists, and image recovery after a target-closed `save_as`.
- Full suite: **519 passed, 5 skipped, 12 existing deprecation warnings**.
- No live Flow credit-bearing generation was submitted during verification.

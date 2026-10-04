# AutoVideoAI v6.0.18 — precise Flow gallery video matching

## What the diagnostic showed

The supplied v6.0.17 recovery snapshot was from the current Flow page and contained 119 visible media elements. The classifier reported 17 as videos, so its “exactly one fresh video” check correctly refused to guess. The first gallery tile was 429×241 with both a play control and a 360p badge. Fifteen neighboring 16:9 stills had neither marker, but broad ancestor text containing the word “video” promoted them. A 192×108 sidebar preview had a play icon but no resolution badge and was also promoted.

## Fix

- The bare word “video” and a play icon by themselves no longer turn an image into a video.
- A poster image is treated as a video when tile evidence is corroborated (such as a play control plus a resolution badge), or when there is a literal video node/recognized video URL/explicit video label.
- Queue text remains scoped to the media card. A stale Agent chat message cannot demote a separate gallery clip; a thumbnail inside its own queued card remains pending.
- The recovery process still compares against the saved pre-request baseline and requires one fresh, typed matching asset. It does not select the first tile by position, substitute another file, or submit a duplicate paid generation.

## Resume the existing request

Keep the request journal and recovery sidecar from the v6.0.17 job. If installing v6.0.18 in a new directory, copy the entire updated job directory from v6.0.17's `outputs/`—not the older v6.0.14 copy. Then use Resume once in v6.0.18. The saved video request is checked download-only; do not click Generate or manually associate another MP4.

## Validation

Offline regressions model the 119-element diagnosis: generic gallery labels and a play-only sidebar thumbnail remain non-video, while the main play-plus-resolution tile is the single typed video. Existing queue-thumbnail and exact-baseline recovery tests remain in place. Live Google Flow behavior was not available for testing in this environment.

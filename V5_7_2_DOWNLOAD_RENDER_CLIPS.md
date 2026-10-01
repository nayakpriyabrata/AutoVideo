# AutoVideoAI v5.7.2 — stable Flow downloads, visible footage, and local clips

## Flow download

The detected project-grid video tile is now downloaded from its own three-dot
menu. AutoVideoAI selects Download and the highest visible MP4 resolution while
the canonical project page remains alive. The unstable full-screen media viewer
is retained only as a compatibility fallback.

For a previously paused shot, use `recover-flow-video` first. This mode never
submits a new generation request.

## Render integrity and graphics

- A 20% near-black/missing-picture threshold now triggers safe-concat recovery.
- A still-broken recovery render is refused instead of published.
- Intro, chapter, key-point, recap and outro graphics use transparent panels.
- The outro no longer places a full-frame black layer over the footage.
- Long-form automatic routing targets 60% stock, 20% Flow and 20% image motion.

## Highlight clipper

`python3 cli.py v3 clip INPUT` accepts a local video or a permitted URL. It uses
speech timing and an explainable importance score, removes overlapping picks,
face-reframes to 9:16 and renders bold active-word captions locally.

## Validation

The complete automated suite passes, and a real 1080x1920 captioned smoke clip
was rendered from the supplied long-video example with video and audio streams.

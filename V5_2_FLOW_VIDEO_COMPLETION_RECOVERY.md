# v5.2 - Flow video completion, recovery, exact scene targets

## Flow video readiness

v5.1 could see a fresh poster image a few seconds before the real Flow video was playable and immediately download it as `take_01.mp4`. Since JPEG is technically exposed by ffprobe as a video stream (`jpeg_pipe`), that could pass the old validation and later break the renderer.

v5.2:

- classifies Flow media cards using play controls, resolution badges such as 360p/720p/1080p, video labels and descendant video elements;
- waits for an explicit video card to remain stable before download;
- waits 20 seconds by default before even probing a fresh untyped tile;
- requires a real time-based container with finite positive duration;
- rejects JPEG/PNG/image-pipe media even if the filename ends in `.mp4`.

## Session closure after generation

If Flow replaces/closes the browser page after a request is sent, AutoVideoAI no longer immediately spends another generation attempt. It reopens the same persisted project and waits up to 180 seconds by default for media created by the existing request. Only after that recovery window expires may `--flow-video-retries` submit another generation request.

CLI controls:

- `--flow-video-ready-grace-seconds 20`
- `--flow-video-recovery-wait-seconds 180`

## Exact Flow scene count

`--max-flow-scenes` remains a hard cap, not a requested count. v5.2 adds:

- `--flow-scenes N` - explicit requested number of Flow video scenes.

Budget safety still wins. If three Flow scenes cost more than the per-video budget, the planner reports `[budget-limited]` and uses fewer scenes.

## Renderer safety

Timeline probing now rejects still-image files masquerading as `.mp4`, rejects non-finite/nonsensical durations, and FFmpeg command construction validates every seek/duration/freeze value before rendering.

## Cartoon story preset

v5.2 adds `config/presets/cartoon_story.yaml`. Use it with `--content-type kids_story` to keep a consistent protagonist, cartoon visual style, setting and mood across shots while using the existing AutoVideoAI/Flow generation pipeline.

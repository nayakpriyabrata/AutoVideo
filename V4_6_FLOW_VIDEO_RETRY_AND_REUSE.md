# v4.6 — Flow Video Retry, Safe Project Media Reuse, and Editor Recovery

This release addresses the Sep-23 Flow behavior seen after successful storyboard-image generation.

## Fixes

1. **Do not click `Done` as the primary editor-exit path.** After downloading a Flow image, AutoVideoAI now navigates directly back to the persisted `/project/<uuid>` URL. If Flow closed/recreated the editor target, AutoVideoAI first adopts another live Flow tab before rebuilding the browser session.
2. **Credit-confirmation stale-history fix.** Old `N credits` text elsewhere in an Agent conversation no longer blocks a new generation. A credit confirmation is considered current only when a live approval action or an explicit current confirmation prompt is present. Agent messages such as `I'm going to generate a 4-second video interpolation...` are treated as generation progress, not a failed approval.
3. **Retry Flow video once before image-motion fallback.** STORYBOARD_ECONOMY defaults to one additional paid-video attempt (`--flow-video-retries 1`) before local image-motion fallback.
4. **Exact Flow-project frame cache.** Frames are keyed by exact Flow project URL + prompt + aspect + frame role. Previous jobs bound to the same Flow project are indexed automatically, including v4.5 jobs, and only exact prompt matches are reused.
5. **Content-hashed project-media uploads.** Reference images are uploaded with a stable content fingerprint such as `AV_<sha>_shot_001_open.jpg`. Future runs first look for that exact asset in the same Flow project's media library and reuse it when available. Generic filenames are never blindly reused.
6. **MoviePy fallback remains 1080p.** If FFmpeg/libass fails, the MoviePy renderer now produces 1920x1080 landscape or 1080x1920 portrait instead of silently dropping to 720p.

## New CLI option

```bash
--flow-video-retries 1
```

`1` means one retry after the first Flow video attempt, then image-motion fallback if no usable Flow video is produced.

Project media reuse is enabled by default when a Flow project URL is used. To disable it:

```bash
--no-flow-reuse-project-media
```

## Recommended command

```bash
python3 cli.py v3 create \
  --topic "How AI agents will change work" \
  --type faceless_youtube \
  --duration 45 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 10 \
  --video-share 0.20 \
  --stock-share 0 \
  --max-flow-scenes 1 \
  --shot-max-seconds 8 \
  --frame-source flow \
  --flow-approval once \
  --max-generation-credits 10 \
  --flow-frame-retries 3 \
  --flow-video-retries 1 \
  --network-wait-seconds 300 \
  --flow-capacity-wait-seconds 900 \
  --flow-capacity-retries 8 \
  --flow-project-url "https://flow.google.com/project/8d993ec2-65c4-4395-81da-7aac95f82871"
```

Expected reuse/retry messages include:

```text
[Flow] Returning from image editor to project...
♻️ shot_001 opening frame: reused exact frame from Flow-project cache.
[Flow] Reused existing project media: AV_<hash>_shot_001_open.jpg
🔁 shot_001: Flow returned no usable video; retrying once (1/1) before image-motion fallback...
```

# v4.5 — Flow Project URL + Media Import/Selection Fix

This release fixes three issues observed in the Sep-2026 Google Flow Agent UI.

## 1. Flow projects are identified by URL, not the visible date/time title

Current Flow creates projects with date/time labels (for example `Sept 23 - 17:50`) and does not reliably expose a rename field. AutoVideoAI now treats its `AutoVideo-<job-id>` string as a logical name only and persists the canonical URL:

`https://flow.google.com/project/<uuid>`

The URL is stored in `jobs.flow_project`. Resume and browser-session recovery reopen that exact URL instead of searching for a project title and accidentally creating a new project.

To deliberately reuse an existing Flow project for a new production:

```bash
python3 cli.py v3 create \
  --topic "How AI agents will change work" \
  --type faceless_youtube \
  --duration 45 \
  --profile STORYBOARD_ECONOMY \
  --flow-project-url "https://flow.google.com/project/8d993ec2-65c4-4395-81da-7aac95f82871"
```

To bind an existing AutoVideoAI job:

```bash
python3 cli.py v3 flow-project JOB_ID \
  "https://flow.google.com/project/8d993ec2-65c4-4395-81da-7aac95f82871"
python3 cli.py v3 resume JOB_ID
```

## 2. Agent media picker now completes `Add to prompt`

Flow may upload a local image into the project library but leave the project media modal open. v4.4 returned immediately after the file upload, so the next click on the Agent composer timed out behind the modal. v4.5 uploads references one at a time and completes the `Add to prompt` step before typing the video request.

The generation media baseline is captured **after** start/end reference thumbnails are attached. This prevents reference images from being mistaken for newly generated video media.

## 3. Newly generated asset is fingerprinted

v4.4 mostly relied on the number and screen position of visible image/video elements. Flow keeps historical assets in the DOM and can update tiles in place, so the downloader could select an older image repeatedly even though the Agent generated several distinct images.

v4.5 snapshots media fingerprints before each request, waits for a new fingerprint, remembers it, and downloads that exact new asset. If no new media can be distinguished, the run fails/retries instead of silently downloading an old tile.

## Clipchamp

Clipchamp is intentionally not used as the unattended renderer in v4.5. AutoVideoAI keeps FFmpeg as the primary renderer and MoviePy as fallback. Clipchamp remains suitable for optional manual finishing after the automated MP4 is produced.

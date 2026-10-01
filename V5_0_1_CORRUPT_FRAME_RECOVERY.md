# v5.0.1 — Corrupt frame recovery

This hotfix prevents a partially written/corrupt storyboard image from crashing the local image-motion renderer.

Observed failure:

`PIL.UnidentifiedImageError: cannot identify image file .../storyboard/shot_006_close.jpg`

## Changes

- Validate every Flow/shared-cache frame with Pillow before accepting or caching it.
- Remove invalid shared cache entries and invalid per-job storyboard frames so resume can regenerate them.
- Validate older project frames before reusing them.
- If Flow returns a file path that exists but is not a decodable image, remove it and count the attempt as failed/retryable.
- Image-motion rendering ignores a corrupt optional closing frame and uses the valid opening frame instead of crashing the entire job.
- If the opening frame is corrupt but the closing frame is valid, image-motion can use the closing frame as its single source.

This is especially important after low-disk-space or interrupted-browser/download incidents, which can leave a `.jpg` filename behind without valid JPEG bytes.

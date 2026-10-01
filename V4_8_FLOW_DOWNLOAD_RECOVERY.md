# v4.8 — Flow video download recovery

This release hardens the Flow video path when the Flow editor/browser closes right after a generated video appears.

## Fixes

- Salvage completed Playwright downloads via `download.path()` when `save_as()` fails because the page/context closed.
- Retry post-generation download recovery against the bound Flow project URL using the same preferred asset signature and pre-generation baseline.
- Accept already-saved valid video files before escalating to fallback.

## Why

Observed failure in v4.7:

- Flow generated a fresh asset.
- AutoVideoAI opened the asset for download.
- The page/browser target closed during `Download.save_as(...)`.
- The pipeline fell back to image-motion even though the video generation itself had probably succeeded.

v4.8 keeps the same bounded Flow retry policy, but tries much harder to preserve the generated Flow video before surrendering to image-motion.

## v4.8.1 hotfix

The first v4.8 patch placed `_salvage_playwright_download()` on `FlowBrowserProvider` while `download_latest_asset()` calls it on the `FlowBrowser` instance. That produced:

```text
'FlowBrowser' object has no attribute '_salvage_playwright_download'
```

v4.8.1 moves the helper to the correct `FlowBrowser` class.

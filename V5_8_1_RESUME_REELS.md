# v5.8.1 — Resume and reels hotfix

The September 29 session exposed a real Studio regression: retrying a paused job rendered a second Resume widget with the same key. The same screen incorrectly instructed a user waiting for a JPG opening frame to generate/download an MP4. Both UI defects are corrected.

## Changes

- Default clips return to filled 1080×1920 face cropping. `fit` remains an explicit option. Existing YAML files with `framing: fit` must be changed; existing videos are not rewritten.
- Resume is queued across a Streamlit rerun rather than invoking a nested production run from the pause panel. Repeated pause panels for one job are suppressed per script run.
- The manual prompt-generation/newest-download workflow has been removed from FLOW SESSION. Advanced CLI association remains available, but is not the normal recovery path.
- Recorded Flow media match by URL and kind instead of tile dimensions and accessibility text. Known URL signing parameters may change only when an independent content ID is present. Different assets, ambiguous URLs and media types remain distinct.
- Failed download matching records the expected signature and visible assets in `<asset-path>.recovery.json`. The error retains the actual mismatch reason instead of merely `Cause: FlowUIChanged`.
- CLI expected pauses print a concise message and next actions, with exit status 2, rather than an exception traceback.

The log does not include the stored signature, so it cannot prove whether the failed match was caused by layout, URL changes, unloaded media, or a missing tile. This hotfix addresses known unstable fingerprint fields; it does not claim a live Flow download was reproduced or verified. Unidentifiable requests still pause rather than spend credits again. Preserve `.flow-request.json`, completed files and the saved project URL.

## Install over VERSION 5.8.0

Stop Studio and running jobs. Back up the installation first. From the installation folder:

```bash
cat VERSION
patch --dry-run -p1 < AutoVideoAI-v5.8.0-to-v5.8.1.patch
# Apply only if the dry run succeeds.
patch -p1 < AutoVideoAI-v5.8.0-to-v5.8.1.patch
python3 -m compileall -q cli.py app.py engine
python3 cli.py v3 resume 20260929-125429-7-habits-to-build-your-m-8a59
```

For another installed version, use the full ZIP and migration instructions in README. Do not force this patch over a different baseline.

For reels, append `--framing face-crop` to the existing clip command or select **face-crop** in CLIP STUDIO. Use a new output folder. Static cropping is not active-speaker tracking; review speaker changes. Padding inside a portrait canvas explains the landscape-looking result from v5.8.0's fit default.

## Evidence and verification

- **280 regression tests passed** on Linux/Python 3.12; includes new resize/identity, duplicate-panel, queued-resume and crop-default regressions.
- CLI/dashboard/engine compile checks passed.
- Streamlit AppTest passed on Flow Session and Clip Studio; restored framing default verified.
- Full ZIP extraction and patch application compared by exact file hashes.
- No paid generation, live Google browser session or user credentials were used in release testing.
- User log confirms Gemini temporary-chat cleanup succeeded at 20:52:23 and four valid clips were retained from ten requested. Neither is the failure shown here.

If resume still fails, inspect the new recovery diagnostic and the saved Flow project. Share the diagnostic with sensitive URL signing values redacted plus the project-grid screenshot. Repeated Resume alone cannot identify a missing or changed asset without additional evidence.

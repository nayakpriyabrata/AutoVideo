# AutoVideo

## Latest release: AutoVideoAI v7.0.0 — Content Studio

**Download the actual standalone ZIP:** [AutoVideoAI-v7.0.0-Content-Studio.zip](AutoVideoAI-v7.0.0-Content-Studio.zip)

**SHA-256:** [checksum file](AutoVideoAI-v7.0.0-Content-Studio.zip.sha256)

**Version:** `7.0.0` · **Archive size:** 1.66 MB

Version 7 is a separate release; extract it into a new folder. It includes the complete editable application source, English/Hindi/Odia support, category-specific Mini Reels guardrails, Factozone (`factozone.com`) and TechniVella RSS idea discovery, and destination-specific video exports with a copy/paste metadata packet and review fingerprint. Inside the ZIP, read `V7_0_0_CONTENT_STUDIO.md` for setup and workflow instructions and `V7_RESEARCH_AND_PRODUCT_PLAN_2026_10_04.md` for platform rules, free/paid tool options and the staged roadmap.

**Publishing remains manual.** The release does not log in to Instagram, Facebook or YouTube, upload a file, or remotely schedule a post. The Facebook Reels export recipe uses the documented 3–90 second Page Reels API range; it is not a universal statement about every Facebook upload surface.

### Validation status

- v7 focused discovery/content/delivery/package tests: **61 passed, 7 media-dependent cases deselected**.
- Full offline suite: **588 passed, 5 skipped, 8 failed**. The eight existing clip/B-roll render tests need system `ffmpeg`/`ffprobe`, which are unavailable in the build sandbox. Install both before using render/export workflows, then rerun those media tests.
- The generated archive passed ZIP CRC and manifest checks; all 317 packaged source-file hashes matched the embedded `RELEASE_MANIFEST.json`. The committed v6.0.19 ZIP remains unchanged.

## Previous release

- [AutoVideoAI v6.0.19 — Flow Video Download Recovery](AutoVideoAI-v6.0.19-Flow-Video-Download-Recovery.zip) — preserved unchanged.
- [AutoVideoAI v5.8.4 — Settings Hotfix](AutoVideoAI-v5.8.4-Settings-Hotfix.zip).

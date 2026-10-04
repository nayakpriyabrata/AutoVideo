# AutoVideo

## Latest release: AutoVideoAI v7.0.1 — Flow Video Recovery

**Download the actual standalone ZIP:** [AutoVideoAI-v7.0.1-Flow-Video-Recovery.zip](AutoVideoAI-v7.0.1-Flow-Video-Recovery.zip)

**SHA-256:** [checksum file](AutoVideoAI-v7.0.1-Flow-Video-Recovery.zip.sha256)

**Version:** `7.0.1` · **Archive size:** 1.66 MB

This is a full source ZIP hotfix for resuming an already-generated Flow video when its gallery tile's URL fingerprint has rotated. AutoVideoAI refreshes the recorded fingerprint only when the same project/request is bound, every saved pre-request baseline tile is still visible, and exactly one fresh typed video exists. It records the rematch, then uses the project tile's **Download → Original size** option (usually displayed as **360p — Original size**). It will not guess among multiple tiles or submit a replacement generation. See the included `V7_0_1_FLOW_VIDEO_FINGERPRINT_RECOVERY.md` for the exact safeguards.

The existing v7.0.0 Content Studio features remain included: editable source, English/Hindi/Odia workflows, Factozone and TechniVella RSS idea discovery, category guardrails, destination MP4 exports, and local manual-upload packets. Publishing remains manual; no social OAuth, account login, remote upload, or remote scheduling is implemented.

**Important:** No live Flow session or original job sidecars were available for end-to-end validation, so the historical job outcome remains unverified. The fix only auto-rematches when all strict baseline/unique-video checks pass; otherwise it leaves the job pending.

### Validation status

- Clean-extraction Flow/recovery tests: **143 passed, 3 skipped**.
- Full offline test suite: **592 passed, 5 skipped, 8 failed**. The eight failures require system `ffmpeg`/`ffprobe`, which are unavailable in the build sandbox; install both before using render/export workflows, then rerun those media tests.
- The archive passed CRC validation and all **319** source-file hashes matched its embedded `RELEASE_MANIFEST.json`.
- The committed v7.0.0 and v6.0.19 ZIPs remain unchanged.

## Previous releases

- [AutoVideoAI v7.0.0 — Content Studio](AutoVideoAI-v7.0.0-Content-Studio.zip) — preserved unchanged.
- [AutoVideoAI v6.0.19 — Flow Video Download Recovery](AutoVideoAI-v6.0.19-Flow-Video-Download-Recovery.zip) — preserved unchanged.
- [AutoVideoAI v5.8.4 — Settings Hotfix](AutoVideoAI-v5.8.4-Settings-Hotfix.zip).

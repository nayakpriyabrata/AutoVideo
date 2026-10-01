# v4.7 — Flow video completion + poisoned-frame-cache repair

This release targets the observed v4.6 run where Flow visibly replied:

> I'm going to generate a 4-second video interpolation between your two tech studio frames.

but AutoVideoAI still reported `Flow credit confirmation blocked` and fell back to image motion.

## Fixes

1. **No generic confirmation buttons.** `Generate`, `Create`, `Continue`, `Proceed`, `Yes`, etc. are no longer treated as Flow credit approvals. Only explicit approval controls (`Approve`, `Approve once`, `Always approve`) are eligible.
2. **Generation-progress text wins over stale history.** If the newest Agent turn says it is generating/creating the video or interpolation, old approval text remaining in the DOM is ignored.
3. **Plain historical `Approve` text cannot block the run.** A blocking confirmation now requires an actually clickable approval control. Nonsemantic current approval rows are still supported when the newest turn is an explicit credit question.
4. **Video result validation.** A new Flow asset is downloaded, but AutoVideoAI accepts the paid Flow scene only if the file is really a video (ffprobe or container signature). A poster/image cannot silently become a `.mp4` take.
5. **Video-aware media wait.** New video tiles are preferred. If Flow renders the video as an image poster tile, the fresh asset is downloaded after generation finishes and validated as a video.
6. **Safer image-editor exit.** Instead of driving Flow's fragile image-editor target back to the project, AutoVideoAI opens the canonical project URL in a fresh tab in the same browser context and adopts it. `Done` is no longer the normal fallback.
7. **Poisoned frame-cache repair.** v4.6 logs showed identical content hashes for `shot_001_open.jpg` and `shot_001_close.jpg`. v4.7 detects same-byte opening/closing pairs, removes the bad closing cache entry, regenerates a visibly different closing frame, and stores the repaired frame under the normal cache key.
8. **Old-job cache bootstrap guard.** Closing frames from older jobs are not indexed when their bytes are identical to the same shot's opening frame.

The existing `--flow-video-retries 1` remains: one extra Flow video attempt is made before image-motion fallback.

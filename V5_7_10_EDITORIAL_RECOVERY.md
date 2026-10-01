# v5.7.10 — Editorial recovery testing build

## What the supplied evidence showed

The screenshots show the response ellipsis opening an export/report menu; chat deletion belongs to the current sidebar conversation's ellipsis, followed by the Delete chat confirmation. The attached film samples repeatedly show the same cloud view. Its execution log assigns a 7.2-second source to a 139.9-second narration window and schedules the outro after the actual 287.9-second runtime. These are real defects, not something that more credits will fix.

The ten-clip run reports five verified Gemini candidates, throws an exception solely because five is less than ten, then discards them. This release preserves them. A maximum requested count is not a guarantee that enough standalone, non-overlapping moments exist.

## Changes

Additional September 29 Flow fixes: the tile-download listener is installed before the initial Download click, covering immediate image downloads as well as resolution submenus. New Agent submissions record a `*.flow-request.json` sidecar before submission, including project binding and pre-generation asset signatures. Once recorded, an unresolved request pauses instead of authorizing another generation. A subsequent resume downloads only the recorded asset (or a single identifiable new asset). Missing/ambiguous matches require assisted recovery. Matching a different tile is explicitly refused.

These records protect **new requests made by this build**. They cannot reconstruct which requests or credits belonged to older runs. Keep the project at `https://flow.google.com/project/0c4d2cc7-88d0-4fe6-b349-71beb08d3925`; recover already-created media before attempting a new job. The final lines of the supplied September 28 log say safe-concat recovery passed, so that excerpt shows a slow, problematic generation run followed by a successful technical render recovery, not a final render exception. It does not prove editorial quality.

Do not delete a pending-request sidecar to make Resume generate again. If automatic download fails, manually download the correct asset to the exact path printed in the error, then resume; the file is validated locally. Keep the sidecar and original project URL. Live WSL browser closure itself cannot be certified fixed by offline tests.

| Area | Change | Boundary |
|---|---|---|
| Gemini cleanup | Captures submitted conversation ID, uses its sidebar row only, selects Delete inside its menu and confirmation dialog, verifies removal | Fails safely on unknown UI; never deletes unrelated/previous chats |
| Capture safety | Saves complete response under `logs/gemini/response-*.txt` before cleanup; failed responses stay in Gemini | Saved JSON-shaped response still needs downstream semantic validation |
| Cleanup diagnostics | `logs/gemini/cleanup-latest.json` records verified deletion or safe failure | Live signed-in Gemini must be tested on your machine |
| Partial clips | Retains valid Gemini selections when fewer than requested; report and Studio show requested/actual counts | Does not fill a quota with weaker clips |
| Titles | Uses complete short clauses, skips filler-only openings, has a labelled topic-summary fallback | A local summary still needs editorial review |
| Reruns | Existing MP4 filenames get collision suffixes; selected moments saved before render | Latest `highlights.json` remains the current-run report; not a complete clip-resume engine |
| Source cache | Downloads for different source strings use separate hashed work folders | URL aliases may create separate caches |
| Progress | Shared clip logs, real elapsed time, per-render encoding progress, waiting heartbeats, default 180-second encoder no-progress limit | Percentages outside rendering are stage estimates, not provider completion percentages |
| Timing | Removes unsafe greedy ASR re-anchoring; implausible gaps/collapsed timings trigger explicitly logged estimated timing | Estimated script timing is not exact forced alignment |
| Generation guard | Rejects huge timing gaps/windows before new shot requests | Existing damaged plans are not silently replaced or regenerated |
| Coverage gate | Stops excessive short-source extension, missing/unaccepted shots and identical-file reuse exceeding 20% across multiple slots in long videos | Exact-file hashing does not detect every re-encoded duplicate or semantic mismatch |
| Stock | Tracks used API IDs/local paths through per-job source sidecars; rejects unrelated tiny local-library fallback; removes generic image-prompt style filler; AI-agent queries prefer computing | Search results are not multimodal relevance-verified; browser results can still require replacement |
| Graphics | Prefers matching approved beat headings; otherwise complete short clauses; skips broken fragments; clamps events/outro to real audio length | Does not invent missing content; complex tables and behind-head segmentation are not new in this release |
| Renderer | Full-video pipeline uses normalized hard-cut concat first, not a failed xfade followed by a second full render | Dissolves are not used by the main full-video path |
| QC | Detects a freeze continuing to EOF; missing clip black/motion metrics cannot silently pass; technical pass is not upload approval | No virality or copyright clearance certification |

## Upgrade safely

Stop Studio and any running CLI job first. The folder name `AutoVideoAI-v5.7.0` does not tell you the installed version; read `VERSION`.

If your installed VERSION is exactly **5.7.9**, back up the whole installation from its parent directory:

```bash
cp -a AutoVideoAI-v5.7.0 AutoVideoAI-backup-v5.7.9
cd AutoVideoAI-v5.7.0
cat VERSION
patch --dry-run -p1 < ../AutoVideoAI-v5.7.9-to-v5.7.10.patch
patch -p1 < ../AutoVideoAI-v5.7.9-to-v5.7.10.patch
python3 -m compileall -q cli.py app.py engine
```

Only run the second patch command if the dry run succeeds. Do not force a patch over a different version or local edits. Restore the backup to roll back. The patch contains no API keys, outputs, job database or browser profiles.

For a clean installation, extract the ZIP, follow README installation instructions, then copy your `.env` locally. Keep the previous installation intact. To migrate existing jobs, copy `outputs/` and `data/` into the clean installation while both tools are stopped. Keep browser profile/CDP settings unchanged. Do not upload `.env`, cookies or browser profiles for support.

## First clip test: browser only

This intentionally skips the failing API step so cleanup and partial selection can be tested independently. Set the source-rights value truthfully; the example is for a video you own.

```bash
python3 cli.py v3 gemini-open
python3 cli.py v3 clip \
  "https://www.youtube.com/watch?v=XUvGaXnBtXE" \
  --source-rights own_content \
  --output outputs/gemini-clips-v5710-test \
  --count 10 \
  --min-seconds 25 \
  --max-seconds 55 \
  --caption-provider groq \
  --ranking-provider gemini-web-hybrid \
  --gemini-chat-cleanup delete-after-read
```

No spaces after the line-continuation backslashes. Alternatively use `clip_config.yaml` and `python3 cli.py v3 clip-config clip_config.yaml`.

Expected: if five valid moments exist, render five and report `requested_count=10`, `actual_count=5`, `partial_result=true`. Never silently discard those five to satisfy the count. Inspect `highlights.json`, each `.qc.json`, and `logs/runtime.log`. Review beginning/end sentence completeness, title accuracy, subject framing, captions and audio yourself before upload.

For API plus browser fallback, use `--ranking-provider gemini-hybrid`. HTTP 503 is a provider-side unavailable response; this build cannot guarantee service availability. API attempts remain bounded (default 60-second request timeout; retry delays 2/5/10 seconds). Use `GEMINI_CLIP_TIMEOUT` to change the per-request timeout.

Do not assume a hard-coded model name is enabled on your API key. A read-only helper lists models advertising generateContent:

```bash
python3 -m engine.providers.gemini_models
```

Choose a currently available model with video-input support and supply `--gemini-model MODEL_ID` or `GEMINI_CLIP_MODEL` in `.env`. Listing is not itself proof of YouTube video support or guaranteed availability. Official model-discovery reference: https://ai.google.dev/api/models . Existing model configuration is not silently rewritten by the patch.

## Test Gemini cleanup safely

1. Use a new automation request, not a manually selected old conversation.
2. Verify the complete response was saved under `logs/gemini/response-*.txt`.
3. Confirm only that newly submitted conversation disappears, and inspect `cleanup-latest.json`.
4. On `deleted=false`, leave the chat in place; share a screenshot and the diagnostic JSON without private response content if possible. The tool will not guess another Delete button.
5. A timed-out/incomplete answer is intentionally retained, even when delete-after-read is selected. This replaces the unsafe older cleanup-on-failure behavior.

## Test full-length videos and existing jobs

Start with a short, new 30–45 second test using your normal YAML, then a full-length test only after checking the short output. The new timing repair applies while planning new shots. It does not rewrite existing paid assets or change the bound Flow project.

```bash
python3 cli.py v3 status YOUR_JOB_ID
python3 cli.py v3 render YOUR_JOB_ID
```

If coverage QC blocks an old damaged job, read `outputs/YOUR_JOB_ID/render/coverage_qc.json` and `timeline.json`. Replace the listed source with an appropriate longer clip via the existing assisted association workflow (`python3 cli.py v3 associate --help`), or plan a separate corrected job after reviewing its cost. Do not repeatedly resume a job with 100-second shot windows: rendering cannot manufacture missing meaningful coverage. Existing Flow URL binding, download recovery and credit guards are retained unchanged.

The renderer permits only modest short-source extension. It will no longer convert a 7-second clip into minutes of repeated clouds. It does not automatically spend more credits or erase accepted takes to clear QC. Encoder stalls stop after 180 seconds without output-time advancement; `AUTOVIDEO_ENCODER_STALL_SECONDS` can be raised on unusually slow systems.

## Test scope and remaining roadmap

Build validation: **251 tests passed** on Python 3.12 (seven dependency deprecation warnings), Python compilation passed, and a real two-source FFmpeg smoke render with a transparent text overlay produced 6.0 seconds of video with 100% video coverage, 0% black intervals and 0% detected freeze. These are local technical tests, not live Google-service results.

Regression tests cover selection retention, filename collisions, timing repair, coverage checks, EOF freezes, caption/card boundaries, stock queries and scoped cleanup safety. Local FFmpeg smoke tests verify actual encoding; live Google/Flow, API availability, your WSL browser and editorial quality need testing on your setup. Offline selector tests are not live-site certification.

This release does **not** implement the entire production roadmap. Still needed: multimodal narration-to-footage relevance scoring, robust re-encoded-duplicate detection, active-speaker tracking, general subject masking for behind-head typography, rich generated diagrams/tables, character-consistent cartoon direction, semantic hook/payoff evaluation, and rights-reviewed publishing. Reels cannot honestly be declared production-ready solely because the file decodes and has a high heuristic score. No automatic uploads or extra paid generations were performed to validate this release.

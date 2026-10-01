# v5.8.2 — Full-video Gemini cleanup policy

Full-video Studio previously defaulted to `keep`, while Clip Studio defaulted to `delete-after-read`. The reported full-video log has no cleanup-armed message, consistent with that policy being disabled; the submitted screenshots do not show the setting itself, so they cannot establish which value was selected. The new build logs the effective policy at the start of every job.

- New Studio and YAML jobs default to `delete-after-read`.
- Existing job settings are preserved. Resume accepts `--gemini-chat-cleanup delete-after-read` or `keep` and saves the choice before starting.
- Completed responses are saved before cleanup; this also covers completed narration expansion requests using the same provider. Failed/incomplete responses remain for diagnosis.
- Gemini composer detection checks visible editable matches instead of relying only on the first DOM match, which can be hidden.
- Old conversations are not bulk-deleted. Explicit `keep` remains supported. Legacy direct create calls still retain their existing defaults; use Studio/YAML or the resume override.

## Upgrade from exactly 5.8.1

Stop Studio, back up the installation, and check `cat VERSION`. Put the patch inside the installation folder:

```bash
patch --dry-run -p1 < AutoVideoAI-v5.8.1-to-v5.8.2.patch
# Apply only if the dry run succeeds:
patch -p1 < AutoVideoAI-v5.8.1-to-v5.8.2.patch
python3 cli.py v3 resume YOUR_VIDEO_JOB_ID --gemini-chat-cleanup delete-after-read
```

Use the relevant full-video job ID, not a new job. Look for `Gemini temporary-chat policy ... delete-after-read`, then `cleanup armed`, followed by `deleted`, safe failure, or a retained-incomplete-response message. Cleanup diagnostics remain in `logs/gemini/cleanup-latest.json`. Existing completed chats are not revisited by this operation.

The screenshot's “composer did not become ready” error and narration length repair loops are separate from the cleanup setting. Visible-editor detection is improved, but current Gemini browser behavior has not been tested with the user's account. This release does not claim all script-length problems are fixed.

## Flow recovery remains unresolved

The Flow screenshot shows several assets and a five-credit video approval, while the paused request is for `shot_001_open.jpg`. Approving a new video does not repair that pending image match. This build makes no changes to Flow generation or matching and spends no credits during its validation.

To diagnose the remaining mismatch, provide these two files from the paused job's `storyboard` directory:

- `shot_001_open.jpg.recovery.json`
- `shot_001_open.jpg.flow-request.json`

Redact URL authentication/signing values before sharing, preserving asset IDs, URL paths, kind and dimensions. Keep original files unchanged on disk. Screenshots alone cannot reliably map a similar thumbnail to the stored asset signature.

## Validation scope

Regression tests cover policy persistence without changing Flow settings, visible composer selection after a hidden editor, new Studio defaults, and explicit keep behavior. No live Gemini deletion or Flow download is claimed verified. ZIP integrity and exact patched-baseline file matching are checked during packaging.

# AutoVideoAI v5.8.3 — download callback hotfix

## What failed

The screenshot shows `builtin_function_or_method` has no attribute `_pw_impl_instance_` when opening the tile download menu. The download listener used Python's built-in `list.append`. Playwright caches a wrapper attribute on callbacks, which built-in methods cannot store. Registration failed before the Download button could be clicked. This was incorrectly presented as an unavailable Download control.

The listener now uses a normal Python function and removes the same callback on success or failure. Existing request records, project URLs and asset matching checks remain intact. This fixes the identified callback error; it does not prove every live Flow menu or asset download will work.

## Upgrade from 5.8.2

Stop the dashboard with Ctrl+C. Back up the installation, then run from its directory:

```bash
patch --dry-run -p1 < AutoVideoAI-v5.8.2-to-v5.8.3.patch
patch -p1 < AutoVideoAI-v5.8.2-to-v5.8.3.patch
cat VERSION
```

VERSION should be 5.8.3. If the dry run fails, do not force the patch. Use the full ZIP in a separate directory, install its requirements and copy your configuration, saved browser profiles, and outputs from the old installation. Keep the same output paths/settings where possible. Do not overwrite the only copy of the old installation.

## Resume the screenshot's job

```bash
python3 cli.py v3 resume 20260930-104836-winners-mindset-fc4f --gemini-chat-cleanup delete-after-read
```

Resume will try downloading the recorded pending image; it must not submit another paid request for that pending asset. Later ungenerated shots can still spend the configured generation budget. Do not delete `.flow-request.json`, clear the job or create a replacement job to bypass the pause.

The dashboard now hides manual MP4 association instructions, including ones in old pause states. No manual download is required by the normal recovery workflow. The separate legacy CLI association command remains available for deliberate local imports. Safety pauses remain when an asset cannot be identified or downloaded, or QC fails; suppressing them would risk wrong media or repeated paid generation.

## Narration length handling

The supplied log had 733 words against a target of 654, so that draft was over target, not short. It reached TTS successfully (288 seconds in the screenshot). Length targets are estimates; measured speech duration is more useful.

Length repair now stops when a response makes no improvement. If an optional repair fails or returns no narration, it keeps the existing draft for the caller's editorial and runtime checks. It does not request manual text entry, fabricate filler, remove editorial checks, or guarantee the requested duration. Incomplete initial scripts and substantively poor scripts can still fail validation.

## Verification and limits

The regression tests exercise the actual installed Playwright callback mapper, direct download and failure cleanup, unchanged/unavailable length repairs, and automatic-only pause actions. Existing tests cover download submenus and pending-request persistence. Live Google Flow and signed-in Gemini were not exercised. No credits were used for validation.

If resume still pauses, send the new terminal error plus `storyboard/shot_001_open.jpg.recovery.json` and `storyboard/shot_001_open.jpg.flow-request.json` from this job. Remove authentication and signed URL values before sharing, preserving asset IDs and URL paths. Do not send API keys or browser profiles.

The full README documents installation, Studio, YAML, clips, render/QC, recovery and known production limitations. This release contains previous fixes; it is not a claim that every historical live-provider problem is solved.

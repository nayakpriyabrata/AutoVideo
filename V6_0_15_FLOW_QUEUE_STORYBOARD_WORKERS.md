# AutoVideoAI v6.0.15 — Flow queue recovery and Storyboard Economy workers

## What changed

- Flow now treats an accepted **scheduled/high-demand queue card** and its image thumbnail as pending, not as a finished video. It waits within the configured generation timeout (900 seconds by default), emits 30-second heartbeats, and never attempts to download the thumbnail as an MP4.
- A timed-out queued request remains in its request journal. `Resume` checks only the saved Flow project and the media newer than the saved baseline. If Flow still shows only the queue card, no new generation is submitted. Once a distinct, typed video is available, recovery downloads that asset; it does not guess from DOM order or substitute another file.
- Storyboard Economy's **Parallel Flow image workers** option now accepts 1, 2, or 3 workers. Independent opening photos and closing frames can run concurrently in isolated Flow projects/tabs. Continuity-linked openings are still exact copies of the previous scene's closing frame, and selected Flow-video scenes retain their distinct opening/closing pair. The existing long-form single-frame optimization remains limited to image-motion scenes.
- Storyboard Economy also offers **Flow video input**: `Storyboard frames (continuity)` or `Prompt only (no images attached)`. Prompt-only applies only to paid Flow motion scenes; stills remain available for image-motion scenes and fallback. Existing jobs default to frame-guided mode and keep their previous request fingerprint so they can resume safely.
- Worker project URLs and generated-frame request evidence are stored under the job. New worker browser profiles are kept outside the job folder and excluded from the release ZIP. An older job may already contain `.flow-workers/worker-*` profile copies from a previous build; treat those as private credentials and never share them.

Mini Reels' visible Gemini Web drafting, reviewable prompt, and explicit approval flow are unchanged. No API Veo route or separate TTS fallback was added.

## Resuming the reported queued job

The request for `shot_001` was already accepted by Flow. Do not click Generate or create a replacement request. After Flow finishes rendering, resume the same saved job:

```bash
python3 cli.py v3 resume 20261003-155029-how-to-be-unforgettable-348a
```

If the video is still queued, the app will keep the saved request unresolved and will not spend again. If the exact playable video is present in the saved project, resume performs download-only recovery.

## Replacing the application ZIP safely

Stop Studio and any running job first. Keep the old installation until the resumed job has been checked. For a clean extraction into a new folder, preserve **all** of the following:

1. The **entire job directory**, not only `flow/`:
   `outputs/20261003-155029-how-to-be-unforgettable-348a/`
   It contains the manifest/settings, accepted media, storyboard frames, request journals and recovery evidence. Hidden files and sidecars matter; copy the directory as a whole.
2. `data/jobs.db` if dashboard history, job listing, and stored provider/project bindings should carry over.
3. Local runtime configuration needed by the job, such as `.env`, `config/user_settings.yaml`, `config/flow_ui.yaml`, custom `assets/`, and any local music/stock libraries. Keep these local; never place secrets in the release ZIP or share them.
4. The signed-in Flow browser profile or the configured CDP browser/profile. On non-WSL installs, the default `.flow-profile/` is relative to the installation folder and must be carried over if you extract to a new folder. Under WSL the default is `~/.local/share/autovideoai/flow-profile`, so leave it in place. Stop browser processes before copying a profile. Do not share profile folders or cookie files.

The job folder is the **primary resume state**, but copying only that folder is not sufficient for a complete fresh installation: it does not carry the dashboard database, runtime configuration, custom assets, or Google sign-in session. For paths that are absolute in older manifests, the safest option is to upgrade in place after making a full backup, or keep the old installation available while validating the copied job.

Example for a new extracted folder (adjust paths to your installation):

```bash
# Stop Studio/jobs before copying; keep the old tree as a backup.
mkdir -p AutoVideoAI-v6.0.15/outputs AutoVideoAI-v6.0.15/data
cp -a AutoVideoAI-old/outputs/20261003-155029-how-to-be-unforgettable-348a \
      AutoVideoAI-v6.0.15/outputs/
cp -a AutoVideoAI-old/data/jobs.db AutoVideoAI-v6.0.15/data/
# Copy only the local config/assets/profile you actually use; keep credentials private.
```

Then run Resume from the new installation directory. Do not delete the old tree until the job and its final download have been verified.

## Validation notes

Offline regressions cover queue-card classification, bounded queue waiting, download-only queued-request resume, prompt-only versus frame-guided request identity, parallel Economy frame generation, and continuity-linked opening/closing frames. Live Google Flow queue behavior still depends on Google's UI/account and must be validated in the user's signed-in browser.

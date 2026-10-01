# v3.6 - Flow Agent / Migrated Editor Adapter

## Why v3.5 failed on the current Flow UI

The account is on the rebuilt `flow.google.com` project UI. In the screenshots the right-side **Google Flow Agent** panel is active (`Untitled session`, prompt `What do you want to create?`). There is no fixed `Text to Video` tab in that surface.

The old fallback was also dangerous: the generic `generation_type_picker` selector could match the Agent quick action **Edit an image** simply because it contained the word `Image`. That explains the Agent reply saying it could not see an image while AutoVideoAI was attempting video mode.

## v3.6 behavior

`flow-direct` now detects which editor is open:

- `standard`: migrated Angular editor with `.settings-trigger-button`. AutoVideoAI opens the settings panel, chooses Video, aspect ratio, duration/count and optional model using structural controls.
- `agent`: expanded Google Flow Agent. AutoVideoAI does **not** search for Text-to-Video tabs. It converts the scene into a precise Agent instruction such as “Create exactly one VIDEO clip ... portrait 9:16 ... 8 seconds ...” and sends it through the Agent composer.
- `legacy`: old Flow controls, kept only as a fallback for older cohorts.

For Agent mode, `--review` fills the instruction but does not send it. Without `--review`, AutoVideoAI sends the instruction and briefly looks for the normal credit confirmation button. It does not change the user's persistent “Confirm before generating” setting.

Automatic download from the expanded Agent panel remains disabled in this build; generated media remains in the current Flow project. Standard-editor download continues to use the existing code path.

## Safe test

```bash
python3 cli.py v3 flow-direct \
  "A cinematic drone shot flying over a futuristic Indian city at sunrise, warm golden light, slow forward camera movement" \
  --aspect 9:16 \
  --duration 8 \
  --review \
  --browser bundled
```

Expected output includes:

```text
[Flow] Editor strategy: agent
[Flow] Flow Agent is active...
[5/5] Prompt inserted. Review mode is ON...
```

Then run without `--review` to submit.

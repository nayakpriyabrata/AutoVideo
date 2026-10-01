# AutoVideoAI — Chrome Companion mode (recommended for Google Flow)

This mode avoids Playwright/CDP/WSL browser ownership completely. Your normal
Windows Chrome stays logged into Google Flow. A small unpacked extension reads
jobs from a **localhost-only** Python bridge and fills the Flow UI for you.

## Why use it

- no Gemini/Veo API key or API billing
- uses the Google Flow account/subscription already logged into Chrome
- no remote-debugging port, no `chrome-debug.bat`, no separate Playwright profile
- works even if AutoVideoAI itself is running inside WSL
- when Flow changes UI, the extension pauses at the prompt instead of losing the job

## 1. Install the extension once

1. In Chrome open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this project's `chrome_extension` folder.
5. Pin **AutoVideoAI Flow Companion**.
6. Open `https://flow.google.com` and log into Google normally.

The extension never receives or stores your Google password.

## 2. Start the local bridge

Windows cmd / PowerShell:

```bat
python -m engine.bridge.server
```

WSL/Linux/macOS:

```bash
python3 -m engine.bridge.server
```

Health check in a browser: `http://127.0.0.1:8765/health`.

## 3. Test one scene

In another terminal:

```bash
python3 -m engine.bridge.server --enqueue "A cinematic aerial shot of Bhubaneswar at sunrise, slow forward camera motion" --aspect 9:16
```

Keep the Flow tab open. Within a couple seconds the companion panel should say
it is preparing the scene, insert the prompt and click Generate.

## Recommended production workflow

AutoVideoAI creates the script/storyboard locally -> queues one Flow scene at a
time -> the Chrome companion fills Flow -> you review/approve the generation ->
Flow download is detected by the extension -> AutoVideoAI associates it with the
scene -> FFmpeg assembles narration, clips, music and captions -> final 9:16 Reel/
Short or 16:9 YouTube video.

For channels where consistency matters, generate/reference one character/style
image and reuse it with Flow's current Ingredients/Frames workflows. Flow supports
vertical output and reference-driven video generation.

## Important limitation

This is UI automation, not a private API. Google can redesign Flow. The companion
therefore deliberately uses runtime DOM discovery and an assisted fallback. It
will never try to bypass login, CAPTCHA, credit limits, content blocks or other
service controls.

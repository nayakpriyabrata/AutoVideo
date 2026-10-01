# Managed Chrome / No-Extension Setup

If Chrome shows **"Your browser is managed by your organisation"** and loading
`chrome_extension/` fails with **"Extension installation is blocked by policy"**,
the companion extension cannot run in that Chrome profile. The localhost bridge
may still accept jobs, but they will stay queued because no extension is polling it.

Use **Direct Browser Mode** instead. It does not install an extension and does not
use a Gemini/Veo API key. Playwright drives a separate persistent Chromium profile
and you log into Google manually once.

## 1. Verify the visible browser works

```bash
python3 cli.py v3 browser-test
```

At least one **headed** variant should PASS.


### WSL note (v3.3)

If `browser-test` reports **native Wayland PASS** but the normal Flow browser previously
failed with an XServer error, v3.3 fixes that mismatch. `flow-open` and `flow-direct` now
try the same native Wayland transport first and fall back to X11 only if needed. No XServer
repair should be attempted just because the X11 probe fails while Wayland passes.

## 2. Open Flow and login once

```bash
python3 cli.py v3 flow-open --browser bundled
```

A Chromium window opens. Sign in to the Google account that has your Google AI
subscription, open Flow if needed, then return to the terminal and press Enter.
The session is saved under:

`~/.local/share/autovideoai/flow-profile`

## 3. Safe prompt test (does NOT click Generate)

```bash
python3 cli.py v3 flow-direct "A cinematic drone shot flying over a futuristic Indian city at sunrise" --aspect 9:16 --review --browser bundled
```

## 4. Generate

```bash
python3 cli.py v3 flow-direct "A cinematic drone shot flying over a futuristic Indian city at sunrise" --aspect 9:16 --browser bundled
```

To wait for the generation and try to download the newest result automatically:

```bash
mkdir -p outputs
python3 cli.py v3 flow-direct "A cinematic drone shot flying over a futuristic Indian city at sunrise" --aspect 9:16 --browser bundled --download outputs/test-flow.mp4
```

## Optional: CDP route

If your company policy allows remote debugging, Windows Chrome may be launched
with `chrome-debug.bat` and AutoVideoAI can attach with CDP. Modern Chrome requires
a non-default `--user-data-dir` for remote debugging. On WSL, localhost reachability
depends on WSL networking, so bundled Chromium is the simpler first choice.

## Important

Do not keep sending `extension-prompt` jobs when the extension is blocked. They
will only accumulate in the bridge queue. Stop the bridge with Ctrl+C and use
`flow-direct` / the main v3 factory instead.

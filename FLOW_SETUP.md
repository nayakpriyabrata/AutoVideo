# 🌊 Flow Setup — Login, Onboarding, Troubleshooting

Flow (Google's Veo app) is the **primary premium engine**, using your existing
Google AI subscription. No Veo API key or API billing required.

## Choose your browser (SETTINGS → Browser, or `FLOW_BROWSER_MODE`)

**Option A — your own Chrome via CDP (recommended).**
Run the one-click launcher from the project folder — `chrome-debug.bat`
on Windows, `./chrome-debug.sh` on Mac/Linux. It opens your real Chrome
with remote debugging on `127.0.0.1:9222` using a dedicated `flow-chrome`
profile (your main Chrome stays untouched) — log into Google once there.
`auto` mode finds it with zero configuration; or set mode `cdp`,
CDP URL `http://127.0.0.1:9222`. FLOW SESSION → "Attach to YOUR open
Chrome" tests the connection live. The app never closes your browser or
tabs — it only disconnects when done.

> Chrome 136+ requires remote debugging to use a **non-default**
> `--user-data-dir` (security change) — that is why the launcher uses a
> separate profile. "Reuse my main Chrome window" via remote debugging is
> no longer possible on modern Chrome.

**Option B — installed Chrome, driven directly (native OS only).**
Mode `system` (or `auto`) drives installed Chrome/Chromium. One manual
Google login, saved to `.flow-profile/`, then it just works. Nothing to
download — this also fixes the
`Executable doesn't exist at .../.cache/ms-playwright/...` error.

**Option C — bundled Chromium (fallback, always works).**
```bash
python3 -m playwright install chromium   # note: python3 -m (bare `playwright` may not be on PATH)
python3 -m playwright install --with-deps chromium  # if it complains about missing Linux libs
```

## First login (Options B/C)

1. Open the app → **FLOW SESSION** → **🔑 Open Flow**.
2. A visible browser window opens at flow.google.com.
3. **Log into Google yourself** in that window (including any 2FA).
4. The session is saved to `.flow-profile/` (git-ignored, stays on your machine).
5. Future runs reuse the login — no browser needed until Google expires it.

## WSL2 notes (Ubuntu on Windows) — READ THIS

- Linux Playwright **cannot launch** Windows Chrome (`/mnt/c/.../chrome.exe`):
  cross-OS process driving always dies. The app now **skips that path
  entirely** — never put a `/mnt/c/...` path in the executable override.
- `auto` mode under WSL = **CDP (Windows Chrome) → bundled (Linux Chromium)**.
- Recommended: run `chrome-debug.bat` **on Windows**, then in the app use
  mode `cdp`, URL `http://127.0.0.1:9222` (auto-probed if you leave it blank).
- If CDP says unreachable while Chrome IS running with the flag, it is WSL
  networking (NAT vs mirrored mode), not Chrome — see Microsoft's WSL
  networking docs, or just use bundled Chromium (renders visibly via WSLg).
  Debug it from the Windows side: run `check-cdp.bat` (endpoint, port owner,
  Chrome flags, WSL version, `.wslconfig`) and read its verdict lines.
- Bundled Chromium needs WSLg (Windows 11, or updated Windows 10).
  `DISPLAY` set but headed launch says "without having a XServer running"?
  The GUI layer is down despite the env vars — check `ls /mnt/wslg/
  /tmp/.X11-unix/` (sockets must exist), then PowerShell (admin):
  `wsl --update`, `wsl --shutdown`, reopen WSL. Corporate VPNs can also
  break WSLg — retry off-VPN. No-WSLg alternative: CDP to Windows Chrome
  (mirrored networking + `chrome-debug.bat`).
- If bundled Chromium dies at launch ("Target page...closed"), run
  `python3 cli.py v3 browser-test` — it tries headed/headless × flag sets,
  saves screenshots to `logs/flow/`, and prints a VERDICT naming the cause
  (GPU/display vs profile corruption vs broken install). Paste that output
  when asking for help.
- Missing Linux libs → `python3 -m playwright install --with-deps chromium`
  (`v3 doctor` runs an `ldd` check and names the missing ones).
- The browser profile auto-lives at `~/.local/share/autovideoai/flow-profile`
  under WSL (never `/mnt/c` — Chromium lock files break there). An existing
  `./.flow-profile` session is migrated automatically on first run.

> The app NEVER asks for, automates, or stores your Google password.

## Recommended first run

1. **CREATE** → pick `FLOW_BALANCED` → check **DRY RUN** → Generate.
   Verify: 6–8 shots, sane budget, good prompts. Zero credits.
2. Uncheck dry run → Generate for real. The browser works visibly; don't close it.
3. If anything looks wrong, the job pauses and tells you why.

## Scene images → reference-first video

Every Flow-profile job first generates K stills per scene (CREATE → Advanced
slider, default 2, 0 skips; CLI `--images-per-shot`) via Flow's image mode,
then scores them (sharpness/exposure/resolution) and feeds the BEST still as
the reference/ingredient into that scene's image-to-video generation. Stills
are much cheaper than video takes, so this buys quality per credit.
- If Flow image mode fails (UI changed, quota UI), the free local image
  fallback still delivers stills — video generation is never blocked.
- If you're logged out or truly out of credits, the job pauses to Assisted.
- Verify image cost in your Flow plan: set `credits_per_image` in
  `config/flow_models.yaml` (`imagen_flow`) to what Flow actually charges
  (0 if images are free on your plan); the budget line `image_credits`
  in `budget.json` uses it.
- STORYBOARD shows the gallery (best first) and a **Download script** button
  (`script.md` is also saved in the job folder next to `script.json`).

## Assisted Flow Mode

If Flow's UI changed or a dialog blocks automation, the job PAUSES and waits
for you (it will not move on its own — that's normal, not "stuck"):
1. Copy the prompt shown in FLOW SESSION → Assisted panel.
2. In the already-open Flow window: open the `AutoVideo-<job>` project
   (the app creates it for you) → Text to Video → paste → Generate.
3. Download the clip into the job's `downloads/` folder.
4. Click **🔍 Check folder & associate**, then **▶️ Continue job**.

Every failure also saves `logs/flow/<job>_<shot>_<time>.png` (screenshot) +
`.json` (page text + buttons seen) — include it if you report an issue.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Could not start any browser. channel: ... not found at /opt/google/chrome/chrome` | Normal on WSL — there is no Linux Chrome. Use `exe` (auto-translated profile) or CDP below. |
| `exe: ... browser has been closed` with a `/mnt/c/...chrome.exe` path | Old bug (Linux profile path sent to Windows Chrome) — update to the latest zip, which translates the profile to `C:\...` automatically. |
| `bundled: Executable doesn't exist at .../.cache/ms-playwright/...` | Run `python3 -m playwright install chromium` (note `python3 -m`), or skip it and use system/CDP mode. |
| Login page loops | Complete login fully in the opened window (wait for Flow home), then retry |

> First step for ANY browser problem: run `python3 cli.py v3 doctor`
> (or FLOW SESSION → 🩺 diagnostics). It reports Python/WSL status, bundled +
> system browsers, profile path translation, and CDP reachability.
| `FlowUIChanged` / element not found | Flow redesigned something → use Assisted Mode; report which step broke; fix selector in `config/flow_ui.yaml` |
| Screenshots in `logs/flow/` | They capture URL + state at failure — attach when asking for help |
| Quota/credits error | Top up or wait for monthly reset; job resumes where it stopped |
| Content rejected | Soften the prompt in STORYBOARD (remove people/brands), regenerate that shot |
| Browser opens but nothing happens | Close stray Chromium processes, delete nothing, retry — session is in `.flow-profile/` |

## Cost control

- Estimates live in `config/flow_models.yaml` — calibrate with your real usage.
- `FLOW_ECONOMY` drafts cheap and upscales winners only.
- `MAX_CREDITS_PER_VIDEO` pauses the job BEFORE overspending.
- `MAX_RETRIES_PER_SHOT` caps burn on stubborn shots.

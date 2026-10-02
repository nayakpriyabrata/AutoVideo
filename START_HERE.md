
# Start here — AutoVideoAI v6.0.0

Start with [the v6.0.0 Content Studio guide](V6_0_0_CONTENT_STUDIO.md) for source imports,
languages, original-character recreation and manual delivery review.

For music-only reels and readable card controls, start with
[V5_8_6_MUSIC_ONLY_TEXT_CARDS.md](V5_8_6_MUSIC_ONLY_TEXT_CARDS.md).
For installation, saved-job upgrades and pause diagnosis, read
[V5_8_5_QUALITY_PAUSE_DIAGNOSTICS.md](V5_8_5_QUALITY_PAUSE_DIAGNOSTICS.md) and
[README.md](README.md). Do not delete old outputs, request journals or browser
profiles to bypass a pause. The earlier runbook below includes legacy commands.

## ⭐ v4.0 recommended profile: Storyboard Economy

For limited Flow credits, use `STORYBOARD_ECONOMY`. It routes only meaningful-motion scenes to Omni 360p, creates opening/closing stills for continuity, animates most scenes locally for 0 Flow credits, and can insert local/Pexels stock B-roll. Start with a no-spend preflight:

```bash
python3 cli.py v3 create --topic "How AI agents will change work" --type faceless_youtube --duration 300 --profile STORYBOARD_ECONOMY --max-credits 50 --video-share 0.18 --stock-share 0.20 --max-flow-scenes 6 --frame-source auto --dry-run
```

Then run a real job without `--dry-run` after reviewing `outputs/<job>/economy_plan.md`. Full details: `V4_0_STORYBOARD_ECONOMY.md`.


> **Managed work Chrome?** If Chrome says *Extension installation is blocked by policy*, skip the companion extension and follow **MANAGED_CHROME_SETUP.md**. Use `python3 cli.py v3 flow-direct ... --browser bundled`; it needs no extension and no Gemini/Veo API key. **v3.3 automatically uses native Wayland on WSLg when that is the working headed-browser path.**

# 🎬 AutoVideoAI — Step-by-Step Runbook

**What this tool does:** you type a topic → it writes a script, narrates it,
generates visuals, adds captions, and gives you a finished MP4 (Shorts/Reels or YouTube).

**Two ways to make videos:**
| | 🆓 FREE path (start here) | 💳 FLOW path (premium quality) |
|---|---|---|
| Cost | $0 forever | Uses your Google AI subscription credits (no API key needed) |
| Visuals | Free AI images + cinematic motion | Veo/Omni AI video clips via Flow |
| Login needed? | No | Yes — log into Google once |
| Time for 20s short | ~3–8 min | ~20–60 min (AI clips render slowly) |
| Good for | Testing, faceless facts channels | High-end shorts, ads, explainers |

---

## STEP 0 — One-time setup on Windows (10–20 min, mostly downloads)

Do this once. Use **Command Prompt (cmd)**, not WSL.

1. **Install Python** (skip if you have 3.10+):
   - Download from https://www.python.org/downloads/
   - ⚠️ On the first install screen, tick **"Add python.exe to PATH"**, then Install.
   - Verify: open cmd, type `python --version` → should print `Python 3.1x.x`.
2. **Install FFmpeg** (video engine):
   - In cmd: `winget install ffmpeg`
   - If that fails: https://ffmpeg.org/download.html → add to PATH.
   - Verify: `ffmpeg -version` prints a version.
3. **Unzip** `AutoVideoAI-v3.zip` anywhere, e.g. `C:\AutoVideoAI`.
4. **Double-click `setup_windows.bat`** → let it finish (installs packages + browser).
   - Needs internet. Takes 5–15 min first time. Don't close the window.
   - It ends with "DONE! Now double-click run_windows.bat to start!"
5. **Double-click `run_windows.bat`** → dashboard opens at http://localhost:8501
   - Keep this black window open while working. Bookmark the page.

> 🐧 WSL/Linux/Mac: same idea — `pip install -r requirements.txt`,
> `python3 -m playwright install chromium`, `streamlit run app.py`.
> The FREE path works everywhere; for FLOW, plain Windows cmd is simplest.

---

## STEP 1 — Make your FIRST video free (proves everything works)

1. Open the dashboard → click **CREATE** (left sidebar).
2. At the top, open **⚡ FIRST TIME HERE? Make a FREE test video**.
3. Type any topic, e.g. `Why octopuses have three hearts`.
4. Click **⚡ MAKE MY FIRST FREE VIDEO**.
5. Watch the progress bar. What's normal (don't panic):
   - `🎙️ Narrating...` — **first ever run downloads a voice model (~150 MB), can sit here 5–10 min. It is working, not stuck.** Later runs take ~1 min.
   - `🖼️ Storyboard frames...` — downloading AI images, 1–3 min.
   - `🎬 shot_00X take...` — rendering motion clips, ~30s each.
   - `🎬 Rendering 1080p...` — final assembly, 1–3 min.
6. When done you see ✅ **Done!** + a video player → **⬇️ Download final MP4**.
   - The file also lives at `outputs\<job-id>\render\*-final.mp4`.

**If anything looks frozen:** is the `run_windows.bat` window printing new lines?
- Yes → it's working, wait.
- No new lines for 15+ min → note the last line and ask for help with that line.

## STEP 1.5 — Make free videos LIVELY (2 min, still $0) 🎥

Out of the box the free path animates AI stills (nice, but slideshow-like).
One free key upgrades it to **real video footage with real motion**:

1. Go to https://www.pexels.com/api/ → **Get Started** → describe use
   ("personal YouTube shorts automation") → copy your free API key (instant).
2. In the project folder, open `.env` (create from `.env.example` if missing) and add:
   ```
   PEXELS_API_KEY=paste-your-key-here
   ```
3. Re-run your video (same CREATE form / same CLI command).
   - Shots now pull real portrait stock clips; only hero shots stay AI-animated.
   - No key? Everything still works — AI stills + motion, just less lively.

Already built-in: per-shot zoom/drift moves, clips cover the full voiceover
(no frozen frames), narration auto-paced to your target length, word-pop
captions burned with FFmpeg (uses Windows fonts automatically under WSL).

---

## STEP 2 — Make a PREMIUM video with Flow (your Google subscription)

Prerequisite: a Google AI Pro/Ultra plan (Flow credits). No API key needed.

1. **Plan first, spend nothing:** CREATE → fill topic → profile `FLOW_BALANCED`
   → ✅ keep **DRY RUN** checked → **🚀 GENERATE**.
   - Check STORYBOARD: 6–8 shots, sane budget, good prompts. Zero credits spent.
2. **Log into Google once:** go to **FLOW SESSION** → **🔑 Open Flow**.
   - A Chrome window opens at flow.google.com → **log in yourself** (2FA too).
   - Session is saved; you won't log in again for a long time.
3. **Generate for real:** back in CREATE (or QUEUE → resume the job),
   **uncheck DRY RUN** → **🚀 GENERATE**. Now it spends Flow credits.
   - ⚠️ Don't close the Flow browser window or the `run_windows.bat` window.
   - Each AI clip takes minutes. A 45s video ≈ 20–60 min total. Walk away.
4. **If it pauses with 🧑‍✈️ Assisted Flow Mode:** this is NORMAL, not an error —
   the app is waiting for you (~2 min of help per shot):
   1. Copy the prompt in the Assisted panel.
   2. In the open Flow window: open the `AutoVideo-<job>` project → Text to Video → paste → Generate.
   3. Download the clip → save the MP4 into the `downloads` folder path shown.
   4. Click **🔍 Check folder & associate** → **▶️ Continue job**.
   - Every pause also saves a screenshot in `logs\flow\` showing what the app saw.
5. **Review & finish:** DIRECTOR REVIEW (watch takes, Accept/Reject) → RENDER
   (quality → Render) → **⬇️ Download final MP4**. Script: STORYBOARD → 📜 Download script.

**Money safety:** budgets (MAX CREDITS PER VIDEO, default 100) are enforced
*before* anything generates. DRY RUN vs FLOW CREDITS vs LOCAL FREE is always
labeled on screen. The app never touches your Google password.

---

## STEP 3 — Know the dashboard pages (30-second tour)

| Page | What it's for |
|---|---|
| CREATE | Start new videos (free one-click box at top, full form below) |
| STORYBOARD | Shot list, scene stills, prompts, **📜 Download script**; edit + Save |
| DIRECTOR REVIEW | Watch every AI take, Accept/Reject, trigger retries |
| QUEUE | All jobs — **resume** paused ones, see status at a glance |
| FLOW SESSION | 🔑 login, 🩺 diagnostics, 🔗 attach to your Chrome, 🧑‍✈️ Assisted panel |
| ASSETS | Browse storyboard / downloads / audio / captions files |
| RENDER | Build the final MP4 from accepted takes (+ download) |
| HISTORY | Past jobs, cost stats, re-download old videos |
| SETTINGS | Browser choice (auto/system/cdp/bundled), TTS voice, budgets |

Typical loop: CREATE → (wait) → DIRECTOR REVIEW → RENDER → download.
Interrupted? QUEUE → resume — every stage is saved, nothing re-runs from zero.

---

## 🩺 When something looks wrong

| Symptom | What to do |
|---|---|
| `Could not start any browser` (esp. in WSL) | Run in **cmd**, not WSL — your Chrome is found automatically. Or FLOW SESSION → 🔗 attach to your open Chrome. Last resort: `python -m playwright install chromium` |
| `python3 cli.py v3 doctor` | Paste me its output — it diagnoses browser setup without launching anything |
| Stuck at `🎙️ Narrating...` first time | Wait 10 min (model download). Still stuck? Check internet; Edge TTS auto-falls-back to gTTS |
| 🧑‍✈️ Assisted pause | Follow the 5 steps in STEP 2.4 — ~2 min per shot |
| `Out of credits / quota` in Flow | Job pauses safely. Top up / wait for reset, then QUEUE → resume |
| Job died halfway (power cut, closed window) | QUEUE → resume. It continues from the last finished stage |
| Want clips 100% manual | Generate in Flow yourself → drop MP4s in `outputs\<job>\downloads` → `python cli.py v3 associate <job> <shot> <file>` per shot → RENDER |

**Command-line shortcut (no dashboard):**
```bat
python cli.py v3 create --topic "Why octopuses have three hearts" --profile FREE_HYBRID --type shorts --duration 20
python cli.py v3 queue                       :: list jobs
python cli.py v3 resume <job-id>             :: resume a job
python cli.py v3 doctor                      :: browser diagnosis
```

Job folders: `outputs\<job-id>\` — `script.md`, `storyboard\`, `downloads\`,
`render\*-final.mp4`. Failure screenshots: `logs\flow\`.

---

## ⭐ Recommended FLOW connection (v3.1): Chrome Companion

If Playwright/CDP is troublesome (especially WSL + Windows Chrome), use the
Chrome Companion instead. It lets AutoVideoAI control the Flow page already
open in your normal signed-in Chrome without owning the browser process.

Read `FLOW_EXTENSION_SETUP.md`. Quick start:

```bat
python cli.py v3 extension-bridge
```

Then load `chrome_extension` once from `chrome://extensions` → Developer mode →
Load unpacked. Open Flow and test:

```bat
python cli.py v3 extension-prompt "cinematic sunrise over an Indian city" --aspect 9:16
```

Use `--review` if you want AutoVideoAI to fill the prompt but leave the final
Generate click to you.

## Current flow.google.com / Flow Agent (v3.6)

If your Flow project opens an **Untitled session** panel on the right with the prompt **What do you want to create?**, that is the new Flow Agent UI. v3.6 detects it automatically and sends video requests through the Agent instead of looking for the removed Text-to-Video tab.

Safe test:

```bash
python3 cli.py v3 flow-direct "cinematic city at sunrise" --aspect 9:16 --duration 8 --review --browser bundled
```

See `V3_6_FLOW_AGENT_ADAPTER.md` for details.

## v3.7 economy Flow Agent quick test

```bash
python3 cli.py v3 flow-direct "your visual prompt" --aspect 9:16 --economy --approval once --max-generation-credits 10 --browser bundled
```

This fixes the expanded Agent `Approve` prompt and refuses a generation whose displayed cost exceeds the configured cap. See `V3_7_ECONOMY_CREDIT_GUARD.md`.

## v4.1 note — long-form videos
For 3–15 minute videos, use STORYBOARD_ECONOMY with `--shot-max-seconds 8`. Run `python3 cli.py v3 audit JOB_ID` after a production to see whether Flow/stock actually generated the planned media or whether scenes fell back locally. See `V4_1_LONGFORM_AUDIT_FIX.md`.

## v4.2 long-form reliability note
For a 5-minute Storyboard Economy test, use a **fresh job**. v4.2 fixes the script-length bug that previously produced only ~8 shots for a 300-second target.

Recommended no-spend validation:

```bash
python3 cli.py v3 create \
  --topic "How AI agents will change work" \
  --type faceless_youtube \
  --duration 300 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 50 \
  --video-share 0.18 \
  --stock-share 0.20 \
  --max-flow-scenes 6 \
  --shot-max-seconds 8 \
  --frame-source flow \
  --flow-approval once \
  --max-generation-credits 10 \
  --dry-run
```

Expected scale: roughly 40-60 visual shots for 300 seconds, depending on narration timing. `audit JOB_ID` should say `Actual providers: NOT EXECUTED` for a dry run.

For the real run, remove `--dry-run`. `--frame-source flow` is recommended when you do not want Pollinations/free-image fallback. If a Flow frame fails twice, the job stops visibly; after Flow is ready again, run `python3 cli.py v3 resume JOB_ID` and cached frames are reused.

## v4.3 Flow reliability

If Flow image generation opens an image editor, v4.3 automatically downloads **1K Original size** and clicks **Done**. Paid Agent video confirmations are automatically handled by `--flow-approval once` while respecting `--max-generation-credits`. Temporary Internet drops pause/recover for up to `--network-wait-seconds` rather than discarding completed frames. See `V4_3_FLOW_RESILIENCE.md`.

# Recommended architecture: subscription-first creator engine

```text
Topic / CSV / Scheduler
        |
        v
Script + scene director (local planner; optional logged-in AI assistant later)
        |
        v
Storyboard JSON + prompts + reference assets
        |
        v
127.0.0.1 job bridge  <---- Streamlit / CLI
        |
        v
Chrome Companion Extension
        |
        +--> existing signed-in Google Flow tab
        |       prompt / aspect / model hint / Generate
        |       user can take over at any time
        |
        +--> Chrome Downloads event
                |
                v
scene clip association -> QC -> FFmpeg render -> Shorts/Reels/YouTube MP4
```

## Why this replaces the old browser-owner design

Old design: Python/Playwright launches or attaches to a browser. On WSL this
creates cross-OS process/profile/networking problems and is sensitive to modern
Chrome remote-debugging restrictions.

New design: Chrome owns Chrome. Python owns planning/rendering. The companion is
only the narrow local bridge between them.

## Phase 2 (recommended)

Add adapters with the same companion pattern for *script assistants* only if
needed. Keep the canonical script/storyboard in AutoVideoAI, not in any website.
The safest workflow is: engine prepares a structured draft -> user/assistant tab
refines it -> engine validates JSON -> scenes go to Flow.

Do not build the product around scraping one vendor's page structure. Every web
assistant adapter should be optional and have assisted/manual fallback.

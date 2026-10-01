# v5.3 - MovieFlow Studio Cartoon Provider

v5.3 adds a real browser-provider path for MovieFlow Studio. Unlike the v5.2
`cartoon_story` preset, this mode actually opens `studio.movieflow.ai`, submits
the story through the visible MovieFlow UI, waits for the completed video, and
downloads the time-based video back into AutoVideoAI for QC, narration, captions
and final rendering.

## Modes

### Full story (recommended for cartoon/kids channel)

`--cartoon-provider movieflow --movieflow-mode full_story`

AutoVideoAI writes the script/character bible, collapses the visual plan to one
MovieFlow story-generation job, and sends MovieFlow a prompt containing:

- complete narration/story
- main character consistency rules
- setting/location bible
- visual style and mood
- target runtime and aspect ratio
- explicit no-text/no-logo visual constraints

Google Flow image/video generation is bypassed in this mode.

### Scene mode

`--cartoon-provider movieflow --movieflow-mode scenes`

The normal STORYBOARD_ECONOMY planner chooses motion-critical shots, but those
selected video shots are sent to MovieFlow instead of Google Flow. This is useful
when you want AutoVideoAI to assemble the final cartoon scene-by-scene.

## First-time login

MovieFlow credentials are never automated. Run:

```bash
python3 cli.py v3 movieflow-open
```

Log in manually in the visible browser and create/open a project once if needed.
The persistent profile is stored under:

`~/.local/share/autovideoai/movieflow-profile`

If you already use a Windows Chrome debugging session, MovieFlow can attach to the
same CDP browser. Optional dedicated environment variables are:

- `MOVIEFLOW_BROWSER_MODE`
- `MOVIEFLOW_CDP_URL`
- `MOVIEFLOW_BROWSER_CHANNEL`
- `MOVIEFLOW_BROWSER_EXE`

## Session-close safety

After AutoVideoAI submits a MovieFlow generation, a browser/page closure does NOT
cause a second generation request. The provider reopens/adopts the same MovieFlow
project and waits for the already-running job before it allows the Factory to fail
or retry.

## Important current limitation

MovieFlow does not currently expose a documented public story-to-video Studio API
in the material used for this integration. v5.3 therefore drives the visible UI
with Playwright. The adapter is selector-tolerant and saves failure screenshots to
`logs/movieflow/`, but MovieFlow can change its UI. The provider code and tests are
validated locally; an authenticated live MovieFlow generation cannot be guaranteed
until the first real account run confirms the current selectors.

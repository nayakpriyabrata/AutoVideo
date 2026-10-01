# Migration notes: v2 → v3

v3 is **additive**: every v2 module still exists and the v2 pipeline runs
(`Quick (v2)` page, legacy `cli.py` flags, `create_video_from_topic`).

## What changed

| v2 | v3 |
|----|----|
| `visual_mode` (auto/flow/stock/ai/kenburns) | Production **profiles** (Flow Cinematic/Balanced/Economy, Local Free, Free Hybrid, Manual Director) |
| Shared `assets/flow_clips/` | **Isolated** `outputs/JOB-ID/flow/shots/shot_NNN/take_MM.mp4` |
| `plan_shots()` keyword prompts | **Director + Story Bible + Prompt Compiler** (model-aware) |
| Equal-split scenes | **Voice-timed shots** from TTS/whisper word timings |
| `COST_PER_SEC` constants | `config/flow_models.yaml` (estimates, user-calibrated) |
| Mixed provider code in `ai_video.py` | `engine/providers/*` behind `VideoProvider` interface |
| Whisper-always captions | **Edge native WordBoundary** → whisper fallback → ASS/SRT templates |
| MoviePy-only render | **FFmpeg primary** (xfade, ASS burn, sidechain duck, loudnorm) + MoviePy fallback |
| Fixed 10% music | **Audio director** (SFX spotting, ducking, loudness) |
| No persistence | **SQLite job DB** + resumable manifests |

## Removed / replaced behavior

- `collect_flow_clips()` (shared folder) → per-job downloads + `associate_download()`.
- `auto` silently preferring stock → profile routing, `NeedsDecision` pauses premium jobs.
- Blind clip looping → trim/freeze (≤1s) + warnings.
- Generic script templates → content planner (12 content types, hooks, beats, CTA rules).

## Upgrading

1. Copy your v2 `.env` over (keys unchanged).
2. `pip install -r requirements.txt` (adds pyyaml, pydantic, tenacity, opencv, pytest, playwright).
3. `playwright install chromium` (only for Flow browser bridge).
4. Old `outputs/` still readable; v3 jobs get the new folder layout.
5. Try `python cli.py v3 create --topic "..." --profile FREE_HYBRID` first (free),
   then a `--dry-run` Flow job before spending credits.

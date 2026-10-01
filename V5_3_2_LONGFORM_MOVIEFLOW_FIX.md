# AutoVideoAI v5.3.2 — Long-form + MovieFlow full-story recovery

This maintenance release fixes two failures reported in v5.3.1.

## 1. Long-form jobs no longer appear frozen at `Storyboard frames...`

When `STORYBOARD_ECONOMY` used `--frame-source flow`, the pre-storyboard stage still called
Pollinations for every planned shot before the real Flow-frame pass. A 5-minute job can have
40–50 shots, and each free-image request can wait/retry for minutes. Those preview calls are
redundant in strict Flow mode and are now skipped.

For strict-Flow jobs of 180 seconds or longer, non-video image-motion shots now use one Flow
still each. Selected AI-video shots still receive distinct opening + closing frames. This roughly
halves the number of Flow still generations on long-form jobs while retaining first/last-frame
guidance where it actually matters.

Progress lines now include `[current/total]` while generating long-form Flow frames.

## 2. MovieFlow `full_story` no longer enters Google Flow frame generation

v5.3.1 correctly planned a single MovieFlow story shot, but a generic Flow-image branch ran
afterwards and created two Google Flow images. `full_story` now bypasses both economy-frame and
generic Flow-image generation.

## 3. Fixed MovieFlow `current_prov` crash

The compiled provider payload referenced `current_prov` before it was assigned, producing:

`UnboundLocalError: local variable 'current_prov' referenced before assignment`

The provider is now resolved before provider-specific fields are constructed.

## 4. API-key migration across clean version folders

CLI/dashboard startup now reuses API credentials from a sibling `AutoVideoAI-v*/.env` when the
current clean install has no cloud keys. Secrets are loaded into the process only; they are not
copied or printed. This prevents clean upgrades from silently falling back from Groq/Gemini to
the deterministic planner and broken local Whisper.

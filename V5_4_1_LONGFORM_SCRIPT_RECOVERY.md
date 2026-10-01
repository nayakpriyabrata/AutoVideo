# AutoVideoAI v5.4.1 - Long-form publish script recovery

v5.4.1 fixes an early publish-mode failure where Groq could return a valid but incomplete JSON object for a long (for example five-minute) script.

Changes:

- Long-form scripts (>=120 seconds or >=300 target words) use **two-stage generation**: compact outline first, narration-only second.
- The provider no longer has to duplicate hundreds of narration words inside both `beats[].text` and `narration`.
- Groq/OpenAI-compatible calls request a larger completion budget (default 8192 tokens).
- Publish-quality critic/repair passes rewrite only the narration while preserving the validated outline.
- A malformed optional polish response can no longer destroy an already publishable draft.
- TTS retiming also uses narration-only JSON, preserving the list/chapter structure.
- Failure diagnostics report output size, JSON keys, narration word count, and target word count without printing API keys or script content.
- Explicit `--script-provider groq` remains strict: retries stay on Groq and never silently fall back to the deterministic planner.

For provider failover while still forbidding the deterministic planner in publish mode, use `--script-provider auto --script-quality publish`.

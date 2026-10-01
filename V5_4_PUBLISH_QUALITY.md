# AutoVideoAI v5.4 — Publish Quality Gate

v5.4 moves quality checks **before** expensive image/video generation.

## Why this release exists

A technically valid v5.3.4 render exposed a content failure: an explicitly requested Groq script silently fell back to the deterministic planner, whose long-form filler drifted into automation/workflow language and repeated the title phrase. The video rendered correctly, but the script was not publishable.

## Changes

- `--script-quality publish` is now the default.
- Explicit `--script-provider groq|gemini|openai|grok|ollama` is strict. If that provider is unavailable or fails quality checks, the job stops before TTS/visual generation. It never silently substitutes the planner.
- `auto + publish` requires at least one working AI writer and tries the configured AI providers in order.
- List-promise titles such as `5 habits`, `7 mistakes`, `10 tips`, etc. are detected automatically. The AI must return exactly that many structured beats and clearly enumerate them in narration.
- Editorial QC rejects keyword stuffing, repeated sentences, unrelated automation/workflow drift, missing list items, and missing closing CTA.
- `editorial_qc.json` is saved before media generation.
- Retiming preserves the original semantic beat structure instead of replacing a five-item outline with arbitrary sentences.
- Long-form shot-to-beat mapping is proportional across the full timeline, so a 51-shot video no longer uses only the last script beat for most visuals.
- `--flow-reuse-mode exact` is the default so a rewritten script does not accidentally inherit old same-topic images from a bad draft.
- Explicit `--caption-provider groq` / `local` is strict and cannot silently fall back to another recognizer.
- Caption grouping is phrase-aware (up to ~7 words, punctuation-aware) instead of mechanical 4-word fragments.
- Automatic render quality defaults to `high`.
- FFmpeg output is tagged H.264 High / BT.709, AAC 48 kHz, faststart.
- `publish_readiness.json` summarizes editorial, visual, caption, render, and acceptance checks after render.

## Recommended publish test

Use a fresh job and `--flow-reuse-mode exact`. For the first v5.4 validation, keep Flow motion scenes at 1 so script/voice/visual quality can be judged without spending hours on Flow retries.

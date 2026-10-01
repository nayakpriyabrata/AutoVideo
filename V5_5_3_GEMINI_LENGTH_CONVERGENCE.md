# AutoVideoAI v5.5.3 — Gemini Length Convergence

Fixes publish-mode failures where Gemini Web produced a coherent script but repeatedly returned roughly 430–500 words for a five-minute target of about 650 words.

- Preserves the good Gemini draft and asks Gemini to expand/trim that same narration.
- Adds up to two precision length-repair passes.
- Lets an editorially clean long-form draft proceed when only approximate planning length remains; measured TTS duration becomes the source of truth.
- Adds bidirectional measured-TTS retiming: short narration is expanded and overlong narration is shortened.
- Allows up to two measured retime/synthesis convergence passes before media generation.
- Keeps topic-drift, list-promise, repetition, CTA, and keyword-stuffing checks.

If the video promises a specific number of items, keep the number in the topic (for example, `5 habits winners build for a successful life`) so structural QC can enforce exactly five items.

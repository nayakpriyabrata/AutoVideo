# AutoVideoAI v5.4.3 — Groq caption recovery

- Keeps Groq Whisper prompts safely below the documented 224-token prompt limit.
- On HTTP 400, retries the same Groq transcription without the optional prompt.
- If word timestamps are still rejected, retries Groq with segment timestamps and derives timing anchors from those segments.
- Error messages now include the Groq response body, making future 400 errors diagnosable.
- Preserves strict `--caption-provider groq`: no silent switch to local Whisper or estimated-only timing.
- Includes all v5.4.2 rate-limit-aware script routing fixes.
- Resume after caption failure reuses the already-generated narration checkpoint instead of synthesizing the voice again.

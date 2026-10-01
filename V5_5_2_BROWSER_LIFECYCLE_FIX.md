# AutoVideoAI v5.5.2 — Browser Lifecycle / Edge TTS / Flow Retry Fix

This release fixes a same-process lifecycle conflict exposed by the new Gemini Web writer.

## Symptoms fixed

- Gemini Web script generation succeeds, then Edge TTS reports `asyncio.run() cannot be called from a running event loop`.
- The first Flow launch reports `It looks like you are using Playwright Sync API inside the asyncio loop`.
- Later Flow retries degrade into `NoneType ... wait_for_timeout` because a half-started browser bridge was cached.

## Changes

1. Gemini's shared Playwright session is closed after the complete writing pass and after retiming. The signed-in profile remains persisted.
2. Edge TTS runs its coroutine in a worker thread only when the caller already owns a running event loop.
3. Flow browser startup is transactional: a failed launch is discarded instead of being reused by later retries.
4. `--plan-only` help now accurately states that it creates the job configuration only.

Existing paused jobs can be resumed; completed script, narration, and storyboard checkpoints are preserved.

# AutoVideoAI v5.4.2 — Rate-limit-aware script failover

This release prevents HTTP 429 responses from wasting all publish-script retries on the same provider.

- In `--script-provider auto`, a provider that returns HTTP 429 is skipped immediately and the next configured AI writer is tried.
- In an explicitly selected provider such as `--script-provider groq`, HTTP 429 remains strict and fails immediately with a clear message rather than retrying three times.
- The same behavior applies to AI retiming after TTS duration measurement.
- Publish mode still never falls back to the deterministic planner.

Recommended production setting: `--script-provider auto --script-quality publish`.

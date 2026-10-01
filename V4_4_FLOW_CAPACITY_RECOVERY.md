# v4.4 — Flow Agent Capacity + Browser Recovery

This patch addresses the Sep-2026 Flow Agent message:

> The agent is experiencing high demand. Please try again later.

## What changed

1. **High-demand is no longer a normal frame failure.** `Try again` was removed from generic failure text matching.
2. **Dedicated capacity recovery.** AutoVideoAI detects Flow Agent capacity messages, uses the existing **Try again / Retry** control, and applies bounded backoff without resubmitting the prompt.
3. **Capacity recovery does not consume `--flow-frame-retries`.** If Flow remains overloaded for the configured recovery window, strict `--frame-source flow` pauses cleanly and keeps completed frames cached.
4. **Stale capacity cards are ignored once a newer generation is running.** This prevents an old high-demand message in Agent history from triggering repeated retries.
5. **TargetClosed/browser-session recovery.** If Flow successfully generates an asset but Playwright loses the page/context/browser during download, the provider rebuilds the session and tries to download the already-generated newest asset before generating again.
6. **Generic failure scanning now favors the latest Agent text**, reducing false positives from older conversation history.

## New CLI options

```bash
--flow-capacity-wait-seconds 900
--flow-capacity-retries 8
```

Defaults use retry delays of `0, 30, 60, 90, 120, 180` seconds, bounded by the overall wait limit.

## Recommended command

```bash
python3 cli.py v3 create \
  --topic "How AI agents will change work" \
  --type faceless_youtube \
  --duration 45 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 10 \
  --video-share 0.20 \
  --stock-share 0 \
  --max-flow-scenes 1 \
  --shot-max-seconds 8 \
  --frame-source flow \
  --flow-approval once \
  --max-generation-credits 10 \
  --flow-frame-retries 3 \
  --network-wait-seconds 300 \
  --flow-capacity-wait-seconds 900 \
  --flow-capacity-retries 8
```

For the already-created job, keep using:

```bash
python3 cli.py v3 resume 20260923-140741-how-ai-agents-will-chang-f0ae
```

Expected capacity-recovery output resembles:

```text
[Flow] Agent is at capacity; retrying now (1/6)...
[Flow] Capacity recovery: clicked 'Try again'.
[Flow] Agent is at capacity; waiting 30s before retry (2/6)...
```

If capacity does not recover inside the configured window, the strict Flow frame job is paused rather than burning all normal frame retries.

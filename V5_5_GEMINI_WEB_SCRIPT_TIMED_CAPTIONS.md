# AutoVideoAI v5.5 — Gemini Web writer + script-timed captions

## Why
The previous publish-quality pipeline still depended on cloud API quotas for
long-form scripts and Whisper transcription. v5.5 adds two independent paths
that avoid those failure modes:

* `--script-provider gemini-web` drives the visible signed-in Gemini website in
  a dedicated persistent Playwright profile. It does not need a Gemini API key.
* `--caption-provider script-timed` builds phrase-friendly timing from the exact
  authored script and measured narration duration. No Whisper/transcription API
  is required.

## One-time Gemini login

```bash
python3 cli.py v3 gemini-open
```

Complete Google login manually in the visible window. The profile is stored at:

```text
~/.local/share/autovideoai/gemini-profile
```

Press Ctrl+C after the Gemini composer is visible. The login is reused later.

## Recommended publish command

```bash
python3 cli.py v3 create \
  --topic "5 habits for a successful life" \
  --type faceless_youtube \
  --duration 300 \
  --content-type education \
  --profile STORYBOARD_ECONOMY \
  --max-credits 30 \
  --flow-scenes 1 \
  --max-flow-scenes 1 \
  --frame-source flow \
  --flow-video-retries 0 \
  --flow-reuse-mode exact \
  --script-provider gemini-web \
  --script-quality publish \
  --tts-provider auto \
  --caption-provider script-timed \
  --max-tts-speedup 1.08 \
  --render-quality high
```

## Browser separation
Gemini Web, Google Flow and MovieFlow use different persistent profiles. A Flow
browser crash therefore does not invalidate Gemini login or script creation.

## Limitations
Gemini Web is UI automation. If Google changes the Gemini DOM, the provider may
need selector updates. Publish-mode script QC still validates every returned
script before TTS or media generation, so a malformed browser response stops
cheaply before expensive Flow work.

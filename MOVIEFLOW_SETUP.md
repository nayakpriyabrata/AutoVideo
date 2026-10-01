# MovieFlow Studio Setup

1. Install/use the same Playwright browser setup as Google Flow.
2. Run `python3 cli.py v3 movieflow-open`.
3. Sign in manually to MovieFlow Studio. AutoVideoAI never enters passwords.
4. If the landing page does not expose the Agent composer automatically, click
   Start Creating / New Project once. Leave the project open until the CLI prints
   `MovieFlow Studio ready`.
5. Press Ctrl+C. The persistent browser profile is kept for later jobs.

Recommended first production:

```bash
python3 cli.py v3 create \
  --topic "The little inventor who learned to never give up" \
  --type faceless_youtube \
  --duration 120 \
  --content-type kids_story \
  --preset cartoon_story \
  --profile STORYBOARD_ECONOMY \
  --cartoon-provider movieflow \
  --movieflow-mode full_story \
  --script-provider groq \
  --script-quality high \
  --tts-provider auto \
  --caption-provider groq \
  --movieflow-wait-seconds 1800 \
  --movieflow-recovery-wait-seconds 300
```

If a project/workspace URL is stable and reusable, add:

`--movieflow-project-url "https://studio.movieflow.ai/..."`

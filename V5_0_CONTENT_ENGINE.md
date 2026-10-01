# AutoVideoAI v5.0 — Content, Voice & Caption Engine

v5.0 keeps the v4.9 Flow browser/session/reuse fixes and upgrades the parts that were still making the final videos feel synthetic: script writing, narration, timing and captions.

## 1. Full-script AI director

`--script-provider auto` now tries a complete structured script provider in this order:

1. Gemini (`GEMINI_API_KEY`, default model `gemini-3.8-flash`)
2. Groq (`GROQ_API_KEY`, default model `openai/gpt-oss-120b`)
3. Ollama local
4. OpenAI (only when `OPENAI_API_KEY` is present)
5. xAI/Grok (only when `XAI_API_KEY` is present)
6. deterministic built-in planner

The AI owns the whole narration + hook + beat plan. It is no longer limited to rewriting a few hard-coded beat sentences. High quality mode performs an editor/critic pass.

## 2. Natural-duration scripts

AI scripts target about 2.18 spoken words/second. If the selected TTS still comes out more than ~11% over target, v5 rewrites the narration to a shorter, complete-sentence version and synthesizes it again. Only a small final pitch-preserving speed correction is allowed (`--max-tts-speedup 1.08`). Audio is no longer routinely squeezed from ~57 seconds to 45 seconds.

## 3. Narration router

`--tts-provider auto` uses the best configured option and keeps gTTS as a last resort:

- Gemini 3.8 Flash TTS
- Gemini 3.8 Flash-Lite TTS
- Groq Orpheus TTS (English, if `GROQ_API_KEY` is configured)
- ElevenLabs (if configured)
- Kokoro local (if installed)
- Edge TTS
- gTTS last-resort only

Provider-specific voice IDs can be supplied with `--tts-voice`. Delivery can be controlled with `--tts-style` for providers that support it.

## 4. Exact-script captions

The authored script is now the subtitle source of truth. ASR is used to find word timing, not to rewrite the words.

`--caption-provider auto`:

- Groq Whisper Large V3 Turbo when `GROQ_API_KEY` exists
- local `faster-whisper small` otherwise
- exact-script estimated timing if neither timing engine is available

The aligner maps ASR timing onto the exact script, so a recognition mistake no longer becomes a visible caption mistake.

## 5. Free/local options

For an almost entirely free content stack:

- Gemini free tier: script + TTS (subject to Google free-tier limits/policies)
- Groq free tier: script/timing, subject to account rate limits
- Ollama: local script fallback
- Kokoro: local TTS (`pip install 'kokoro>=0.9.4' soundfile`, plus `espeak-ng`)
- faster-whisper: local caption timing

All existing Flow project reuse, video rescue, guard-tab/soft-page recovery and cross-version caches from v4.9 remain intact.

## 6. FFmpeg/libass render fix

The ASS caption style row now follows the 23-field V4+ Styles schema exactly. Older builds emitted a malformed 25-field row, which could make libass fail and force the MoviePy fallback. v5 keeps MoviePy as a safety net but restores FFmpeg as the expected primary 1080p renderer.

## Recommended setup

`.env`:

```env
GEMINI_API_KEY=your_google_ai_studio_key
GROQ_API_KEY=your_groq_key
# Optional:
ELEVENLABS_API_KEY=
OPENAI_API_KEY=
XAI_API_KEY=
```

## Recommended command for the existing Flow project

```bash
python3 cli.py v3 create \
  --topic "How develop a winner mindset" \
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
  --flow-video-retries 1 \
  --network-wait-seconds 300 \
  --flow-capacity-wait-seconds 900 \
  --flow-capacity-retries 8 \
  --flow-reuse-mode topic \
  --script-provider auto \
  --script-quality high \
  --tts-provider auto \
  --caption-provider auto \
  --caption-local-model small \
  --max-tts-speedup 1.08 \
  --flow-project-url "https://flow.google.com/project/e2b54ab2-78ad-4dda-97ca-708abae6216c"
```

Expected early log when Gemini/Groq keys are configured:

```text
[  5%] Director: planning content...
[  7%] Script ready: ~95-105 words for 45s target via gemini:gemini-3.8-flash+critic
[ 12%] Narrating...
Transcribing timing with Groq whisper-large-v3-turbo...
```

If the measured voice is too long:

```text
Narration measured 50.8s; rewriting script to ~94 words instead of over-speeding it...
Retimed script: 95 words; narration 45.9s
```

# AutoVideoAI v5.7.4 — Editorial Integrity

This release addresses two independent failures observed in real outputs:

1. YouTube sources downloaded as AV1 could be rendered by FFmpeg but not sampled
   reliably by OpenCV under WSL.
2. A technically valid five-minute MP4 could contain several minutes of one
   frozen frame and still pass the former black-frame-only check.

## Clip extraction

- yt-dlp prefers H.264/AVC plus M4A audio, with compatible fallbacks.
- Face samples are decoded through FFmpeg in software.
- `--ranking-provider auto` uses Groq for editorial ranking when
  `GROQ_API_KEY` is configured.
- The local fallback now rewards standalone openings and clear takeaways while
  penalizing clips that begin with context-dependent conjunctions/pronouns.
- `highlights.json` records a headline, ranking engine and editorial reason.

## Long-form integrity

- Broken ASR/script alignment that covers less than 85% of measured narration is
  replaced with exact-script timing spanning the complete audio.
- Final renders are measured with FFmpeg `freezedetect`.
- A render with at least 20% frozen picture or one freeze of at least eight
  seconds is rejected. A full-render fallback is not allowed to republish it.
- Professional communication/career topics use strongly anchored stock queries
  and generated prompts explicitly exclude nightlife, casinos, dancing and
  unrelated vacation imagery.

## Graphics

Numbered videos receive a transparent side agenda showing all points, with the
current point highlighted, plus a final recap. Channel watermarks are now off
unless `watermark: true` is explicitly selected.

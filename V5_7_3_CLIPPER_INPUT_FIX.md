# AutoVideoAI v5.7.3 — reliable long-video clipping inputs

- Long MP4 files are no longer posted directly to Groq transcription.
- FFmpeg extracts mono 16 kHz/32 kbps audio in five-minute chunks.
- Transcribed word timestamps are offset back onto the original video timeline.
- `yt-dlp` installed with `pip --user` works through `python -m yt_dlp` even if
  `~/.local/bin` is missing from PATH.
- `recover-flow-video` is idempotent: an already-accepted shot returns a clear
  zero-credit status instead of a Python traceback.

The v5.7.2 rendered video supplied with the report was also inspected: it has
full 30.5-second video/audio coverage and no detected near-black interval. The
remaining reported failures were both in the clipper input/transcription stage.

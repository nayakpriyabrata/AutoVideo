# v5.7.9 — bounded render recovery and publish-ready clip QC

## Why the Studio appeared stuck

The primary FFmpeg render correctly detected a 98% black / 91% frozen output.
Its safe-concat repair also failed QC, after which older builds started a full
MoviePy rebuild without progress. A five-minute 1080p project can leave that
Python renderer apparently idle for 30 minutes or longer.

## New render behavior

- Safe recovery uses hard cuts and repeats short source motion instead of
  extending the final frame.
- Recovery prints encoded-time progress plus a heartbeat when FFmpeg has not
  emitted a new frame update for 15 seconds.
- Recovery is bounded by a duration-aware watchdog (5–40 minutes).
- If black, truncated, corrupt, or frozen output still fails QC, the job stops
  with a clear message. It does not start the silent full-MoviePy rebuild.
- Existing project/job data is preserved. Rerun `resume` or `render` after
  installing v5.7.9; no new Flow generation is needed for a render-only retry.

## New clip filenames and QC

`highlight_01.mp4` is replaced by a headline-derived name such as:

```text
unlock-your-future-3-mindset-shifts.mp4
unlock-your-future-3-mindset-shifts.qc.json
```

The sidecar verifies streams, duration, 1080×1920 output, decoding, black
frames, frozen picture, audio and captions. `PASS` is ready for human publish
review, `REVIEW` needs attention, and `BLOCK` is not marked ready. The displayed
0–100 value combines editorial selection and technical readiness; it is not a
virality guarantee and is not claimed to reproduce OpusClip's proprietary score.

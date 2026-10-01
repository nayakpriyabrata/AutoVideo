# v5.3.4 - Render stream coverage QC

This release fixes a blank-final-video case where FFmpeg returned success but the
H.264 video stream ended early while the audio/container continued for the full
runtime. The old black-frame guard divided detected black time by container
length, so an early-ended video stream could evade the 75% threshold.

v5.3.4 now:

- probes video and audio stream durations separately;
- treats a missing video tail as visually blank;
- triggers safe-concat recovery if the video stream covers <95% of the expected
  timeline, even when FFmpeg returned code 0;
- computes black ratio against the expected visual timeline rather than the
  audio-driven MP4 container duration;
- validates the safe-concat output with the same duration and black-frame rules
  before replacing the primary render;
- refuses to publish a render whose video stream is still truncated.

Existing jobs can be repaired without regenerating Flow assets:

    python3 cli.py v3 render JOB_ID

# v5.3.1 — Blank Render Recovery

Fixes a render failure observed on WSL where the final H.264 file was technically valid
but became black immediately after the first scene.

## Changes

- The existing xfade renderer is preserved for compatibility.
- The emergency safe-concat renderer resets every segment with `setpts=PTS-STARTPTS`
  before hard-cut concatenation, avoiding timestamp/transition edge cases.
- Post-render visual QC uses FFmpeg `blackdetect`.
- If >=75% of a multi-scene output is essentially black, AutoVideoAI automatically
  rerenders the same timeline with a transition-safe hard-cut `concat` graph.
- The safe rerender is written to a temporary file and only replaces the primary output
  after it passes visual QC.
- If both renders are still mostly black, AutoVideoAI refuses to publish the blank result
  and lets the higher-level fallback/error handling take over.

This is independent of Google Flow and MovieFlow generation; it protects the final local
render path for either provider.

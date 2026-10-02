# AutoVideoAI v6.0.4 — Long-form voiceover resilience

This maintenance release improves long-form voiceover length handling and prevents caption-timing outages from discarding a valid narration.

## Changes

- For voiceover jobs of two minutes or longer, script generation uses a bounded word-count buffer. A five-minute request asks for roughly six minutes of narration words; this does **not** change the requested video duration or manifest target.
- The measured voiceover remains authoritative. Long-form narration is accepted within a duration window capped at plus or minus 60 seconds (the window scales proportionally for targets from two to five minutes). Outside the window, the existing bounded two-pass script/TTS retiming runs toward the buffered narration goal. Short-video tolerances are unchanged.
- If Groq/local ASR caption timing fails, the production path now falls back to deterministic word timings from the exact authored script and measured audio duration. It logs the fallback and continues, rather than failing after narration has already been synthesized. Timings are approximate and should be reviewed for close word-level sync.
- The original audio checkpoint is reused on resume; the change does not add retries to paid video generation or remove the existing short-audio safety gate.

## Validation

The offline regression tests cover buffered targets, long-form and short-form duration windows, and the script-timing fallback when ASR is unavailable. Live TTS/ASR provider behavior still depends on the user's provider session and credentials.

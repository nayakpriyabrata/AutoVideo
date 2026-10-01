# AutoVideoAI v5.7.7 — Gemini Hybrid Clips

This release adds public-YouTube video understanding to the existing local
clipper without removing its deterministic fallback.

## Selection pipeline

1. The user explicitly declares the source-rights basis.
2. Gemini analyses the public YouTube URL and proposes timestamped, standalone
   moments using the spoken and visual content.
3. Groq/local speech timing verifies the proposed region against the downloaded
   source and moves cut points to complete sentence boundaries.
4. AutoVideoAI combines Gemini editorial score with explainable local hook,
   payoff, density and context scoring.
5. Invalid and overlapping candidates are rejected before FFmpeg renders the
   requested top clips.
6. Gemini/API errors fall back to the existing Groq/local ranker and are written
   to `highlights.json`.

## Rights and music controls

URL clipping requires `source_rights`. AutoVideoAI stores the declaration and
warnings in the report but does not grant or verify legal rights. Commentary or
private-draft declarations are not marked as cleared for public upload.

Optional background music requires a local file plus `music_license`; volume is
limited to a quiet 0.00–0.35 range. Music, captions, crops and motion are editing
choices, not copyright clearance.

## Interfaces

- CLI: `python3 cli.py v3 clip ...`
- YAML: `python3 cli.py v3 clip-config clip_config.yaml`
- Dashboard: **CLIP STUDIO**

Existing clip commands using `--rights-confirmed` remain compatible.

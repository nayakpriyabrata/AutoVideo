# v6.0.14 — Clip workflow and Gemini Web repairs

## Clip framing

`Framing: Fit` now keeps the complete source frame and its display aspect/orientation. Landscape input remains landscape, portrait input remains portrait, and output dimensions are even and capped at a 1920-pixel long edge. Captions, technical QC, stock-search orientation, and B-roll compositing follow the selected output dimensions. `Face crop` remains the separate vertical 9:16 option. Existing rendered files are not modified.

## B-roll workflow

When Clip Studio B-roll is enabled, the main clip action automatically searches for up to the selected maximum after rendering highlights (at most one suggestion per highlight). The maximum is not a guarantee: there may be fewer highlights than the cap, or a configured stock source may have no valid downloadable match; unmatched slots show the reason. Candidates are previewed in the review panel. Every exact asset still requires an explicit approve-or-skip decision, a saved decision, and a separate Apply action before a B-roll edit is rendered. Original highlights and their audio remain unchanged. Missing candidates and source errors are shown instead of silently inserting unrelated footage.

## Optional music search

Pixabay lookup now follows concrete music-item pages rather than guessing a result from a fixed link position, starts the track preview to expose lazy audio, and tries a small bounded number of tracks. Direct MP3/audio files are distinguished from Pixabay's `/audio/` cover thumbnails; provider domain, response type, size, and audio signature are checked before a file is accepted. The helper never substitutes an arbitrary internet track. WSL browser failures now identify whether Playwright, Chromium, network access, or a usable audio download is missing, without exposing signed media URLs. Pixabay item-page and licence provenance continue to be saved when available.

## Gemini Web composer

Gemini's current rich-text composer is detected through its visible Quill `.ql-editor` instead of an ambiguous generic editable node; the hidden `.ql-clipboard` is explicitly excluded. If the composer is still unavailable, the safe diagnostic reports DOM structure counts only and never dumps page text/account data. This is a pre-submit check: no prompt is sent until a visible, editable composer is found. Mini Reels continues to use visible signed-in Gemini Web with an editable prompt and explicit approval before any Flow generation; there is no API or separate TTS fallback.

## Dashboard startup warning

Replaced deprecated Streamlit `use_container_width` calls with `width="stretch"` and raised the supported Streamlit minimum accordingly. The message shown by older v6.0.13 builds was a deprecation warning, not a startup failure; this update removes that warning on supported Streamlit versions.

## Validation

The full test suite passes: **571 passed**. This sandbox lacks a system FFprobe package, so the run used bundled imageio-ffmpeg plus a temporary, test-only FFprobe compatibility shim; install FFmpeg and FFprobe normally for production use. The remaining test output includes upstream ImageIO and Pillow deprecation warnings. A live signed-in Gemini/Pixabay browser session was not available in this sandbox, so those external pages were not exercised end-to-end.

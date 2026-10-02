# AutoVideoAI v6.0.5 — Mini Reels: Gemini Web → Google Flow/Veo

## Added

- A standalone **MINI REELS** page for single, 8-second, 9:16 Flow/Veo clips.
- Optional current Google Trends daily search ideas for India, the United States, and the United Kingdom; manual topic entry remains available if the feed fails.
- Original prompt/creative-brief generation through the visible signed-in Gemini Web browser session only. The page does not fall back to Gemini API credentials.
- Selectable miniature diorama, miniature stop-motion, macro realism, cinematic, and original playful 3D styles.
- Optional Flow-native voiceover, ambient-only audio, or silent prompt direction. Native audio is best-effort, account/model dependent, and must be reviewed; no separate TTS job is performed.
- An editable final Flow prompt, explicit one-generation user approval, model selection, result preview/download, and saved project link.
- Durable reel metadata and request journaling under `outputs/mini_reels/`, with exact-request recovery after interruption.

## Safety and boundaries

- Google Trends is a search-interest signal, not a source of Reels/TikTok performance or a guarantee of virality.
- The numeric Flow approval cap applies when the current Flow Agent UI exposes a credit-approval card. It is not a price estimate and may not be enforceable in every Flow UI mode; users must review Flow's displayed approval and account terms.
- Native Flow audio is experimental; short requested speech may still fail. See [Google's Flow prompting tips](https://blog.google/technology/ai/flow-video-tips/) and review every clip.
- No uncertain video request is blindly resubmitted. Changed prompt/model options are blocked for an unresolved request, and the app holds new reel generations while a previous mini-reel request is pending.
- A missing native audio track produces a warning; the video is not automatically regenerated or replaced, avoiding unexpected extra credits.
- No multi-clip assembly, external voice synthesis, API-based Veo generation, or automatic publishing is included.

## Verification

- Focused unit tests cover RSS parsing/bounds, prompt validation, native-audio prompt directives, saved Flow results, pending-request locking, and dashboard rendering without provider calls.
- Full test suite: **493 passed, 5 skipped, 12 existing deprecation warnings**.

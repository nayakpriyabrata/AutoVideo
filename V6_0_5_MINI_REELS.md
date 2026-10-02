# AutoVideoAI v6.0.5 — Mini Reels (Gemini Web → Flow/Veo)

## What it adds

The **MINI REELS** page is a separate prompt-first path for one original **8-second, 9:16 Flow/Veo clip**:

1. Optionally refresh current Google Trends daily search ideas for India, the United States, or the United Kingdom. You can also type an idea yourself.
2. Ask the visible, signed-in Gemini Web browser session for an original concept and Flow prompt.
3. Review/edit the exact Flow prompt and explicitly approve one Flow generation within the selected credit cap.
4. Generate directly in the existing browser-based Google Flow/Veo provider, then preview/download the saved MP4.

This is deliberately **not** a long-form storyboard, multi-clip editor, external text-to-speech job, Gemini API integration, or automatic social-media uploader. Choose among miniature diorama, miniature stop-motion, macro-realism, cinematic, and playful 3D visual treatments. “Mini reel” here means a short vertical clip; the miniature looks are optional.

## Setup

- Sign in to Gemini Web once with `python3 cli.py v3 gemini-open` if that browser profile is not already authenticated.
- Configure/sign in to Google Flow using the existing Flow browser setup in this installation. No Gemini API key or Veo API key is used by this page.
- Open the Streamlit app and select **MINI REELS**.

## Audio

Select **Flow-native voiceover**, **Flow-native ambience (request no speech)**, or **Prompt for silence**. The page places the audio direction in the reviewed Flow prompt; it does not invoke AutoVideoAI's TTS providers. Native speech/audio depends on the selected Flow/Veo model and account, can vary by language, and must be listened to and reviewed. A silence instruction is also only a prompt request; if Flow returns audio anyway, the app warns and keeps the original clip. The app detects whether an audio stream is present when `ffprobe` is available, but cannot determine whether the requested words were spoken correctly.

Google describes Flow audio as experimental; its prompting guidance notes that speech is less likely when requested dialogue does not fit the eight-second clip. See [Google's Flow prompting tips](https://blog.google/technology/ai/flow-video-tips/). If the generated video has no audio stream, AutoVideoAI warns and keeps the original clip. It does **not** silently regenerate or replace that video, avoiding an unexpected second credit-bearing generation.

## Credit and retry safeguards

- Trend loading and prompt creation do not submit a video to Flow.
- Video generation requires a separate prompt review and explicit one-generation approval checkbox. The numeric cap applies when the current Flow Agent UI exposes a credit-approval card; it is not a price estimate and may not be enforceable in every Flow UI mode. Review any Flow credit prompt and your account terms before proceeding.
- A Flow request is recorded in `outputs/mini_reels/<reel-id>/mini-reel.mp4.flow-request.json` before submission. Repeated clicks/recovery reuse the same request; recovery does not send a new prompt.
- A changed prompt/model cannot be substituted into an unresolved request. The exact pending request must be recovered first.
- The app will not start a second mini-reel generation while another mini-reel request is unresolved. Recover or resolve the saved request first.
- Trend feed failure has no hard-coded fallback; enter a manual idea instead. Google Trends search interest is only an idea signal and does not establish Reels/TikTok virality.

Drafts and generated clips are stored under `outputs/mini_reels/` (ignored by Git). Review trend-derived concepts and generated media before publishing.

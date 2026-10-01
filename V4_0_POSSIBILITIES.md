# AutoVideoAI v4.0 — What We Can Build From Here

AutoVideoAI v4.0 treats Google Flow as one execution engine, not the entire product. The project owns the script, timing, storyboard, references, budget, media choices and final edit.

## Already in this build

- Credit-aware `STORYBOARD_ECONOMY` routing.
- Script/narration planning without requiring an external LLM API; local Ollama can improve narration if available.
- Voice-first scene timing: visual shots are planned around narration windows.
- Character/location/style reference prompts.
- Opening + closing frame pairs for every economy scene.
- Closing-frame -> next-opening-frame continuity.
- Free/local image-motion scenes with pan/zoom/crossfade.
- Meaningful stock/B-roll scenes from `assets/stock_library` without any API.
- Optional Pexels/Pixabay stock search when the user adds a key.
- Paid Flow motion only on selected high-value scenes.
- Gemini Omni Flash 360p economy video route with a per-generation credit guard.
- Flow Agent one-time approval handling.
- Safe fallback to image-motion when a Flow scene cannot be completed/downloaded.
- FFmpeg/MoviePy final timeline, narration, captions and scene assembly.
- Shorts/Reels 9:16 and YouTube 16:9 layouts.
- Dry-run economy plan before spending credits.
- Streamlit controls for video share, stock share, maximum paid scenes, frame source and credit caps.

## High-value next upgrades

### Browser-based script director (no Gemini/OpenAI API)
Use a logged-in Gemini or ChatGPT browser tab as an optional script/storyboard assistant, then validate its JSON locally before production. Keep the project manifest as the source of truth so UI changes never destroy a job.

### Stronger character continuity
Maintain multiple canonical character references (front, 3/4, profile, full body, outfit), attach the most relevant references per scene, record wardrobe/location continuity, and block a generated scene when visual identity changes too much.

### Smarter stock layer
Build a searchable local cache of legally obtained Pexels/Pixabay/other stock clips, tag them automatically, avoid reuse within one video, prefer real stock for generic office/city/nature/technology B-roll, and reserve AI video for shots stock cannot express.

### Motion from stills without credits
Add depth/parallax, foreground/background separation, camera push/pull, pan, tilt, crop re-framing, light motion, particles, animated text and transitions. This can make image-heavy long videos feel much less static.

### Flow media retrieval
Improve current Agent result detection/download so generated media is automatically matched to its shot id, verified, renamed and reused as the next scene's continuity input.

### Automatic QC and retry policy
Detect black frames, wrong aspect ratio, too-short clips, corrupt downloads, obvious duplicate media and poor subject visibility. Retry only high-value shots and never exceed the configured budget.

### Multi-format derivatives
Render one master project into 16:9 YouTube, 9:16 Shorts/Reels and 1:1 social variants. Reframe shots and reposition captions automatically instead of regenerating the media.

### Publishing package
Generate title ideas, description, chapters, hashtags, thumbnail brief, caption file and upload-ready assets. Actual publishing can remain manual or use a connected publishing integration if desired.

## Recommended production philosophy

For long-form video, target roughly 15–25% paid AI-motion scenes, 10–25% real stock/B-roll, and the rest free image-motion/graphics. Spend AI video credits on hooks, reveals, transformations and motion that matters to the story—not on every sentence.

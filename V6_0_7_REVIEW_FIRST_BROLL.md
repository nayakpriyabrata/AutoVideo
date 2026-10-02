# v6.0.7 — Review-first stock B-roll cutaways

## What changed

Adds an **opt-in, preview-first B-roll cutaway editor** for both regular production renders and source-derived CLIP STUDIO highlights. It uses the currently configured local stock library or stock provider; it does not call Flow/Veo or overwrite an accepted source clip.

The Facebook share link could not be fetched from the development environment (HTTP 403). This implements the described behavior—related stock cutaways interleaved with the main picture—not a frame-by-frame recreation of that reference.

## Regular production videos and reels

1. Finish and accept the production shots as usual.
2. Open **RENDER → Optional related stock B-roll cutaways**.
3. Choose a bounded suggestion count/duration and explicitly click **Find related stock cutaways**.
4. Preview each downloaded candidate, review its source/licence, adjust its position and length, then explicitly choose **Approve** (with rights review) or **Skip** for every suggestion. A pending suggestion blocks the production render.
5. Click **Save cutaway decisions**, then render.

Approved cutaways default to scene boundaries. They replace only the picture for the selected time; existing narration, music, captions, overall timeline length, and the accepted scene media are preserved. The B-roll render is written as a separate `*-final-broll.mp4`; the normal `*-final.mp4` remains untouched. A failed B-roll render does not silently fall back to an edit without the approved cutaways.

## CLIP STUDIO highlights

Enable **Optional: find related stock B-roll cutaways for these highlights** after creating the source-derived clips. The suggestion count only limits the search; it does not insert footage. Click **Search related stock**, preview the original highlight beside each exact stock candidate, adjust the cutaway time/length, then explicitly choose **Approve** (with rights review) or **Skip** for every suggestion. Save decisions before clicking **Apply saved cutaways to separate copies**. Pending decisions cannot be applied.

Each approved B-roll edit is a new `*-broll-*.mp4`. Existing highlight files and their original audio remain unchanged. Since CLIP STUDIO currently emits separate highlight files, the cutaway is placed inside each selected highlight; this does not create a single compilation from all highlights.

## Stock and rights safeguards

- Searching is opt-in and bounded (up to 10 production suggestions or 5 CLIP STUDIO suggestions per run).
- Candidates come from the configured local library or configured stock provider; no new AI video, Flow request, or TTS is started.
- Nothing is included in a final render unless its exact downloaded file passes the saved SHA-256 check and the user has both reviewed its rights and approved it.
- Provider/source, public page, creator, licence text, query, and timeline placement are recorded in the job's provenance files where available. Raw media download URLs are not shown in the UI.
- A missing/unmatched stock asset is reported; neighboring clips are not silently substituted.
- The rights checkbox records the user's review; it is not legal advice or a guarantee of commercial-use rights.

## Verification

Full suite: **508 passed, 5 skipped, 12 existing deprecation warnings**.

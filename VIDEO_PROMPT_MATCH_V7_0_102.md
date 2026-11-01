# AutoVideoAI 7.0.102 · why the scan said "no verified match" although your clip was right there

Your recovery worked: the reviewed download saved `take_04.mp4`, QC decided **ACCEPT** (technical 100,
continuity 74.4, motion 100, overall 93.6) and shot_014 is now an accepted take — the second run correctly
answers `already_accepted`. The interesting question is the one you asked.

```
[Flow] Exact video recovery scan: 8 gallery assets, 2 fresh candidates, 3 readable prompts,
       0 unavailable prompt controls; no verified match.
FlowUIChanged: No unique completed video matches the request. Review the exact editor URL or export …
```

Eight assets were visible and **three prompts were read successfully** — so this was not a blind scan. It
still refused, for two independent reasons.

## 1 · The saved prompt and the card's prompt were never the same string

A video request is written as one envelope:

> Create exactly 1 VIDEO clip. Do not create a still image. Use landscape orientation (16:9), approximately 6
> seconds, using Omni 1.1 Flash. Generate the media from this scene description exactly as the creative brief:
> **Close-up of Samridhi standing calmly in a brightly lit, elegant room …**

A tile's *Reuse prompt* usually returns **only the brief** (the part after the colon) — exactly as it does for
images, where the app already parses its own envelope (`image_creative_brief`). The video path had no such
parser, so it compared the full envelope with a brief and could never match. Three readable prompts were read
and all three "failed".

## 2 · Two fresh assets: "2 fresh candidates" forbade the answer

The video branch accepts a match only when **exactly one** candidate verifies, because Flow often exposes the
same clip twice — once as a `<video>` node and again as its poster `<img>`. With two fresh assets and no
verification step succeeding, nothing could ever be chosen.

## What 7.0.102 changes

| Piece | Behaviour |
|---|---|
| `video_creative_brief()` | parses our own video envelope (model labels with dots included — "Omni 1.1 Flash", "Veo 3.1 - Lite") and returns the brief |
| `same_video_generation_prompt()` | exact identity: the full envelope, **or** the brief on either side. Used by the scan and by `_reidentify_exact_video` too |
| double exposure | when several fresh assets verify with the same prompt, the one Flow renders as a real video element wins (its posters are the others); two genuinely different clips still refuse |
| candidate listing | every fresh candidate the scan considered is printed with its prompt, size and, when Flow exposes it, **its own `/edit/` URL**; the failure text then hands over a ready `--asset-url … --asset-reviewed` command per candidate |
| asset identity untouched | the new `edit_url` is read-only context and is **not** part of the persisted `sig`/baseline, so old journals keep matching |

The comparison stays exact — one changed word is still a miss. Nothing is adopted on resemblance, size or
order.

## Where your job stands now

shot_014 is accepted (take_04). Next: **Resume** — it continues with the remaining shots and the job no longer
needs recovery for this one. One note on that take: QC recorded `continuity 74.4` with the detail tag
`camera_too_fast`. The decision was still ACCEPT (overall 93.6), so nothing blocks the render; if the shot reads
too fast in the finished video, re-render/replace that one shot later rather than redoing the job.

## Tests

`tests/test_v7102_video_prompt_brief.py` — 16 tests:

- the brief is extracted from our own envelope for four model labels, including dotted ones;
- a card returning only the brief matches the saved envelope in both directions; a full prompt matches itself;
- a different scene and a one-word change are both misses (the comparison stays exact);
- an image envelope is never mistaken for a video brief, and the image path still works;
- the candidate listing is read-only, bounded to 5, reports a missing prompt as unreadable, and never promotes
  a relative media URL to an editor URL;
- the double-exposure case picks the `<video>` node; two different clips refuse and are listed;
- the scan records its listing on the journal and the failure text carries the ready command.

Targeted flow/video/resume/approval selection: 493 passed, 21 failed + 4 errors — the same set as the untouched
7.0.101 tree in this sandbox (environmental), 477 → 493 passed.

## Install

1. Stop the dashboard (all tabs).
2. Extract `AutoVideoAI-v7.0.102-Video-Prompt-Match.zip` beside your installation.
3. From inside the installation folder:

   ```
   python3 ../AutoVideoAI-v7.0.102/tools/update_v7101_to_v7102.py .            # dry run
   python3 ../AutoVideoAI-v7.0.102/tools/update_v7101_to_v7102.py . --apply    # installs the code
   ```

   Accepts an installed 7.0.101 (or an already-updated 7.0.102), backs replaced files up under
   `code-update-backups/v7.0.101-to-v7.0.102-<timestamp>`, and never touches outputs, jobs, Flow journals,
   browser profiles or Clip Studio folders.

## Not verified live

No Flow project was opened and no credit was spent here. The envelope parsing and the listing are covered by
tests; whether a particular Flow layout exposes `/edit/` links on its tiles can only be seen in your browser —
if it does not, the failure text says so and asks for the address-bar URL instead.

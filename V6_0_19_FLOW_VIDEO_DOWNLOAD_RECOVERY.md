# AutoVideoAI v6.0.19 — Flow video download recovery

## Diagnosis

The v6.0.18 recovery run identified the newly generated video tile in the saved Flow project and received the browser's download event. Flow then closed/replaced the Playwright target before `Download.save_as` could finish. The asset remained pending; no replacement generation was submitted.

## Fix

- If `save_as` fails, recovery first keeps the existing Playwright temporary-file salvage. For MP4s only, it can then stream the URL attached to that same browser `Download` event—the asset selected from the exact matched tile—into a temporary file and atomically save it.
- The fallback is download-only: it accepts HTTPS URLs on Google-owned hosts, follows only bounded same-allowlist redirects, limits transfer time and size, requires video content and an MP4 `ftyp` signature, and never logs or stores the signed URL. It does not copy browser cookies or call a private Flow API. Existing media validation still has to pass before a request is marked complete.
- The tile download menu now prefers **Original size** / **Download original** before resolution labels. For the supplied menu, this selects **360p Original size** rather than **720p Upscaled**.
- Exact request identity, baseline checks, and duplicate-generation safeguards are unchanged. The recovery path does not click Generate or submit a second credit-bearing request.

## Resume the existing request

1. Install v6.0.19 separately, or back up your current installation first.
2. Copy the entire job directory for `20261003-155029-how-to-be-unforgettable-348a` from v6.0.18's `outputs/` into v6.0.19's `outputs/`, preserving its Flow request journal and recovery diagnostic. Do not replace those files with the older v6.0.16 snapshot.
3. Use Resume once for that same job. It should reopen the recorded Flow project and attempt to download the exact saved asset; it must not submit a new generation. Leave the request journal and Flow browser profile in place.

If the exact tile cannot be verified or its download still fails validation, the job remains pending for assisted recovery; do not manually associate another MP4 or click Generate.

## Validation

Offline regressions simulate `TargetClosedError` after a video download event, verify byte-for-byte recovery from that event's URL, check that signed query values are not printed, and verify that **Original size** precedes **720p**. The full Flow/Google browser session was not available for live testing.

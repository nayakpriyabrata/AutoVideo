# AutoVideoAI v6.0.6 — Flow Resume Safety

## Changes

- CDP reconnects prefer an existing Flow page, reuse a blank tab, or create one persistent Flow tab without navigating unrelated user tabs.
- Resume preserves an existing `flow.google.com` project route.
- Repeated recovery against a still-loading exact project tab no longer opens another tab per poll; canonical guard tabs are reused.
- Pending recovery messages now identify the media kind and include the browser provider's concise returned error when available. Video recovery guidance explicitly forbids substituting an MP4 or clicking Generate again.
- Coverage-QC render stops expose their saved issue list and unaccepted shot statuses in a read-only dashboard panel; no QC bypass or automatic regeneration is introduced.

## Safety

- Unresolved requests remain download-only; exact media-signature and request-journal checks are unchanged.
- Flow pause remains opt-in.
- The Coverage QC gate still blocks renders containing unaccepted shots. Operators must review and resolve only the listed shots.
- No `.env`, cookie, profile, or raw signed media URL is needed for support.

## Tests

- Full test suite: **501 passed, 5 skipped, 12 existing deprecation warnings**.

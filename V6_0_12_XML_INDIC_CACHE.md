# v6.0.12 — Safe XML Feeds and Indic Font Cache Repair

## Fixes

- Hardened all RSS/Atom parsers used by Mini Reels and the Source Inbox with `defusedxml`. The previous raw-byte search for `<!DOCTYPE`/`<!ENTITY` could be bypassed by UTF-16 XML; the parser then expanded internal entities instead of rejecting them. The raw scan remains an early check, and parser-level DTD/entity rejection now applies regardless of encoding.
- Fixed a memory-retention bug in the Indic font fallback. Its class-level `lru_cache` used `self` as a cache key and retained up to 256 FreeType/HarfBuzz font instances after their render jobs ended. Rendering results are now cached per font instance with the same 256-entry LRU bound, so the cache is released with the font.
- Includes the v6.0.11 repair for v3 CLI JSON commands and versioned Mini Reels User-Agent labels.

## Verification

- Full test suite: **547 passed, 5 skipped, 12 deprecation warnings**.
- Python compilation: passed (`compileall`).
- Focused Ruff checks for syntax, undefined names, unsafe XML parsing and method-cache retention: passed (`E9,F63,F7,F82,S314,B019`).
- Streamlit AppTest smoke: STUDIO, CLIP STUDIO, RENDER, MINI REELS, and SETTINGS all loaded without exceptions.
- Regression tests reproduce and reject UTF-16 DTD/entity payloads and verify that completed Indic-font renderers can be garbage-collected while retaining a bounded local render cache.
- Existing Gemini, review-first B-roll, and optional-music behavior remained covered by the full suite. No live Gemini/Flow/Veo session, paid generation, or account action was used.

The release was validated offline. Live provider behavior and machine-specific browser/FFmpeg integrations can still vary by environment; the five skipped tests and pre-existing deprecation warnings remain visible in the test results.

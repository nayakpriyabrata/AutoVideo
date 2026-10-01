# v5.8.0 validation record

Testing date: 29 September 2026. Environment: Linux, Python 3.12, FFmpeg, local isolated virtual environment. The supported minimum Python version remains 3.10; this run was not performed on the user's WSL laptop.

| Check | Result |
|---|---|
| Full `python -m pytest -q` | 274 passed; 11 non-failing Pillow/MoviePy deprecation warnings |
| Compile CLI, dashboard and engine | Passed |
| CLI production-check help/parser | Passed |
| Streamlit AppTest: Studio, Production QC, Clip Studio | No page exceptions; framing control present |
| Real FFmpeg: six-second two-source render with structured overlay | Passed black/freeze/duration checks |
| Production check of synthetic final, zero model-call budget | Technical gate passed; overall NEEDS_REVIEW as intended |
| Real full Factory render with hashed media override and custom graphics | Passed; override applied, report invalidated, final not labelled publication-approved |
| Real 1080×1920 full-frame fit encoding | Passed |
| Horizontal/vertical graphics PNG checks | Rendered and transparency verified; representative graphics and final composite visually inspected |

No live Google Flow generation, Gemini browser deletion, or paid Gemini vision API request was run for this release. Browser behavior is covered by regression fixtures and requires account-specific testing. API verdict tests use controlled responses, including bad responses, missing budget and changed-content cache invalidation. The attached user clip was sampled to diagnose framing; it was not used as proof of semantic accuracy or publication rights.

The packaging procedure verifies ZIP integrity and extracted file hashes, applies the incremental patch to an exact clean 5.7.10 baseline, and compares every resulting file hash to the full build. Build archives exclude secrets, runtime jobs, browser profiles and caches.

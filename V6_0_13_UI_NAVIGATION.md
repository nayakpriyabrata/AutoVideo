# v6.0.13 — Workspace Navigation and Guided UI

## What changed

- Replaced the flat 18-page sidebar list with five workspaces: Create, Review & Render, Jobs & Recovery, Content & Delivery, and Setup & Legacy.
- Added reader-facing page names, including Guided Studio, Advanced Create, Render & B-roll, and Queue & Resume, while preserving the existing internal route values and features.
- Clarified Guided Studio as the recommended lower-friction path and Advanced Create as the full-control path.
- Added `UI_UX_AUDIT.md`: feature coverage against the requirements recorded in this session, a map of the current workflows, and a prioritized production-readiness roadmap.

## Verification

- Full test suite: **548 passed, 5 skipped, 12 existing deprecation warnings**.
- All 18 dashboard pages loaded through the grouped navigation in Streamlit AppTest without exceptions.
- Focused static checks, compilation, and whitespace validation passed.
- Existing Mini Reels prompt approval, B-roll review/identity, source-rights confirmation, optional music, and job-recovery behavior remain unchanged.

## Important limitations

This release improves discovery and labeling; it does not yet unify the overlapping creation forms or add the planned standard-production preflight, guided home dashboard, cooperative cancellation, or team/multi-user controls. See `UI_UX_AUDIT.md` for the independent assessment and suggested implementation order. No live provider or paid-generation workflow was used during UI verification.

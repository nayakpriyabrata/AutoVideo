# AutoVideoAI — independent UI/UX and production-readiness review

**Reviewed:** 2026-10-03
**Scope:** Current Streamlit dashboard, current README/release notes, existing automated UI/feature tests, and the feature requirements recorded in this session. No live Google/Flow account was opened and no paid generation was run.

## Are the discussed features present?

Based on the requirements recorded in this session, the main discussed workflows are present in the code and have offline regression coverage:

| Requirement | Current implementation | Boundary / note |
|---|---|---|
| Long-form and vertical production, resumable jobs, storyboard, render, technical QC | Guided Studio / Advanced Create, Queue, Storyboard, Director Review, Production QC, Render | Technical QC is not editorial, rights, or fact-check approval. |
| Mini Reels idea sources and visible Gemini Web drafting | Manual, Google Trends, and curated RSS ideas feed a visible Gemini Web prompt | Article/trend content is inspiration, not verified research. No API Veo fallback or separate TTS. |
| Review before credit-bearing Mini Reel generation | Editable final Flow prompt, explicit one-generation approval, bounded cap when Flow exposes its approval UI, exact-request recovery | Flow's own account price/approval UI remains authoritative; uncertain requests are not blindly resubmitted. |
| B-roll that is actually visible in the rendered picture | Production scene-boundary and Clip Studio cutaways are rendered as video-only layers; tests compare output frames | It is opt-in and review-first; the original clip/audio is preserved. |
| Exact B-roll approval and rights review | Preview the exact candidate, explicitly approve or skip each item, review rights, save decisions; content hash is checked before use | Search results are suggestions, not automatically cleared licences. |
| Optional music without a music-specific acknowledgement gate | Optional low-level bed, local or Internet-selected source, provenance/creator/page/hash when available | Source-video rights confirmation in Clip Studio remains separate and required. No claim that arbitrary Internet audio is copyright-safe. |
| Content Studio and delivery workflow | Source inbox, approved-plan imports, original-character library, review-gated recreation, manual destination exports and owned-account metrics | Social OAuth publishing and automatic posting are intentionally not implemented. |
| Hindi/Odia text support and memory-safe font fallback | Bundled fonts and Indic shaping/fallback path | Actual visual quality still needs human review on target devices and export formats. |

The v6.0.11/6.0.12 fixes and the above feature tests are present in the current workspace. This is a check of the recorded requirements, not proof that every historical idea or every live-provider state works in every account.

## Current user flows

1. **Standard production:** Guided Studio or Advanced Create → create/run or plan-only → Queue → review storyboard/director/QC → Render → History.
2. **Mini Reels:** choose manual/trend/article idea → ask visible Gemini Web → inspect/edit its brief and exact Flow prompt → explicitly approve one generation → review/download or recover the saved request.
3. **Clip Studio:** provide a source and confirm its rights declaration → analyse/cut clips → optionally add music → optionally search for B-roll → preview and decide on each exact cutaway → apply separate copies.
4. **Content/recreation:** import untrusted source text → review/approve a plan → define an original character → create and approve a recreation plan → export a local delivery package for manual review/upload.
5. **Troubleshooting:** select the job → Queue/Flow Session → recovery panel or redacted support report → resume the same saved job.

The sidebar now groups the 18 pages into **Create**, **Review & Render**, **Jobs & Recovery**, **Content & Delivery**, and **Setup & Legacy**, and uses reader-facing names such as **Guided Studio**, **Advanced Create**, and **Render & B-roll**. This reduces initial navigation load without removing the existing tools.

## Main usability findings

### Improvements made in this review

- Replaced one flat list of 18 page choices with five workspaces and a smaller page list per workspace.
- Distinguished the recommended lower-friction **Guided Studio** from **Advanced Create** so users can tell which creation path to start with.
- Clarified where Mini Reels, B-roll, job recovery, and the legacy v2 page live.
- Added automated Streamlit navigation coverage, including switching workspaces and visiting the content/review pages.

### Remaining gaps, ordered by impact

**P0 — before calling the UI production-grade**

1. **Add a real preflight/review step for standard production.** Before any job can spend credits, show the selected model/profile, estimated scene plan and budget/reserve, max-per-generation and max-per-video caps, expected providers, and any user-supplied files. Require a deliberate “Start within these limits” action. Keep plan-only/dry-run available and default-safe. Mini Reels already has a stronger prompt-review gate; the standard flow should reach the same clarity.
2. **Create a Home / Project Dashboard.** Show one obvious “New production” action, recent jobs, paused/failed jobs with next safe action, current setup readiness, and links to Clip Studio/Content Inbox. Queue is useful but currently a job table rather than a guided home.
3. **Unify the two standard creation forms.** Guided Studio and Advanced Create overlap but expose different defaults and settings. Use one shared configuration model and progressively disclose advanced controls so the two forms cannot drift.
4. **Handle job cancellation and browser disconnects explicitly.** The live-run view blocks while a background worker runs and has no clear safe cancel/pause control. Add cooperative cancellation at safe checkpoints, distinguish “stop waiting” from “stop job,” and ensure page reload cannot accidentally submit duplicate work.
5. **Harden settings recovery.** A malformed or hand-edited `config/user_settings.yaml` should produce a clear warning and safe reset path, not an uncaught exception while opening Settings.

**P1 — operational polish**

- Add a first-run checklist: FFmpeg/FFprobe, browser mode, required/optional providers, output-folder write access, disk space, and a no-generation test. Show key presence only—never key values.
- Replace raw exception text with short explanations, likely causes, and one safe next action; keep a collapsible technical detail and redacted diagnostic export.
- Make every job page share a compact status/progress strip (stage, elapsed time, accepted/total shots, budget vs cap, last event), with consistent Resume/Recover/Render actions.
- Add searchable/sortable job history, saved filters, and “duplicate settings as a new plan” without copying paid media or rerunning generation.
- Improve accessibility: keyboard path, visible focus, descriptive labels, contrast, small-screen behavior, and localized English/Hindi/Odia UI copy (not just generated video content).
- Add a persistent asset/provenance view so clip rights, music provenance, B-roll approval hashes, prompts, and final export lineage are visible together.

**P2 — product expansion**

- Reusable channel presets and project templates with versioned settings.
- Team workspaces, roles/permissions, approval assignment, audit history, and concurrent-job locking.
- Backup/restore and retention controls for jobs, media, logs, and browser profiles; quota and disk-space alerts.
- Optional social publishing only as a separately scoped feature: per-platform OAuth, explicit final approval, disclosure/audience fields, idempotent upload recovery, and a clear manual-export fallback. Do not turn on unattended posting by implication.
- Localization/research assistance with source citations and human fact-check workflow; do not treat trend/article RSS as verified evidence.

## Production-readiness judgement

AutoVideoAI already has meaningful safety foundations: bounded generation/retry controls, saved-job recovery, exact asset identity checks, prompt and B-roll review gates, provenance fields, offline tests, and redacted diagnostics. It is best described as a **local production-assistance tool with manual review**, not a team SaaS platform or unattended publishing system. The highest-value next investment is the standard-production preflight and a unified Project Dashboard; those reduce costly mistakes while making the first session much easier.

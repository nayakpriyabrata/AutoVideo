# AutoVideoAI v5.8.0 — testing release

Includes all changes from the supplied v5.7.10 baseline plus:

- Full-source `fit` framing by default for clip output, with an explicit static `face-crop` alternative in CLI, YAML and Studio. The supplied 41.05-second clip shows cut-off heads in sampled later frames; reprocess the original wide source to recover those pixels.
- Timed transparent-canvas list, comparison and bar-chart graphics, with active-row highlighting, final-duration checks, nonoverlap checks, measured text fitting and explicit chart evidence fields.
- `production-init`, `production-check`, `production-repair` and Studio's PRODUCTION QC page.
- Optional budgeted Gemini API sample review against narration and visual intent; cached by final-video hash and review inputs. Disabled by default and no API retry spending.
- Technical media review, long-hold/perceptual-duplicate flags, per-asset rights evidence registry, attribution output and factual-research records.
- Hash-checked local scene replacements, validated before committing the override map, then applied during ordinary rerender. No Flow requests are made by this repair workflow.
- Render success is no longer labelled PUBLISH_READY. Reports distinguish technical completion, editorial evidence and incomplete review.
- Clip API model selection is explicit instead of assuming a model-version ID; missing configuration is reported before the selected fallback path.

Read README sections 15–17 for safe upgrade, complete schemas, commands, and a feature status matrix. The incremental patch targets exactly VERSION 5.7.10. For older versions use the full build; do not force a patch.

## Validation

[Validation record](VALIDATION_V5_8_0.md): **274 tests passed**, plus real FFmpeg and full Factory integration checks and Streamlit page smoke tests. Automated tests cover cache/budget behavior, incomplete semantic responses, changed evidence, stale repairs, replacement tampering, graphics constraints, transparency and framing. Existing Flow, Gemini, clip, timing and rendering regressions remain included.

Browser cleanup/download behavior is tested with simulated browser events, not your live signed-in Google session. Sampled semantic review tests use controlled responses, not paid live calls. This release does not certify that Google's current UI, quotas, credentials or WSL display stack will work unattended. The supplied clip was sampled for visual framing review; that is not a full semantic/audio editorial review.

## First test

1. Stop processes, back up and install following README section 15.
2. Recover already-generated Flow assets before starting new paid generation.
3. Reprocess one owned wide-source clip with `--framing fit` and browser-only ranking if isolating the API 503 issue.
4. Add one short card to a completed job, render preview, check locally, then optionally enable a small semantic API call budget.
5. Review `production/review.json`, `render/coverage_qc.json`, `highlights.json` and the relevant runtime logs.

The broader autonomous-production roadmap is only partially implemented. Dynamic speaker tracking, behind-head compositing, automatic fact research, character rigs, autonomous stock repair, publishing and analytics remain future work; they are not advertised as working features.

# v4.2 - Long-form Duration + Flow Frame Reliability Fix

## Why v4.1 still produced only 8 shots for a 300 second request
The visual splitter was no longer the main issue. The fallback script planner stopped after a small number of expansion sentences, so a 5-minute request produced roughly 170-180 words (about 70-90 seconds of narration). The shot planner correctly followed the *actual narration*, so it only had enough material for about 8 shots.

v4.2 makes the no-API planner target the requested narration word count for long-form videos and adds a pre-generation duration safety gate. A 300 second job will not proceed to Flow if the narration is dramatically shorter than requested.

## Shot pacing
The shot windowing logic now flushes *before* a new sentence would exceed `--shot-max-seconds`. This prevents an 8 second target from becoming 12-14 second visual beats.

## Flow image fallback visibility
`--frame-source auto` now retries a failed Flow image once, then prints a visible warning before using the free fallback. The manifest records opening/closing frame sources and the audit reports them.

`--frame-source flow` is strict: after two failed Flow attempts, the run stops with a clear error instead of silently switching to Pollinations. Existing completed frames are cached, so `python3 cli.py v3 resume JOB_ID` continues from the missing frame rather than starting over.

## Dry-run audit
Dry runs no longer label planned providers as "actual providers". The audit explicitly says that providers were not executed and credits were not spent.

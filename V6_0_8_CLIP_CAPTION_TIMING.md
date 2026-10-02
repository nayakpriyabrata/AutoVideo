# v6.0.8 — Clip caption timing repair

## Reported failure

Clip generation stopped with:

```text
Invalid caption word[14]: expected 0 ≤ start ≤ end and ordered starts
```

The Clip Studio transcription route trusted the timing order returned by an ASR provider. An occasional word with an earlier timestamp later in the returned list (or an end slightly before its start) reached the shared caption validator and aborted rendering.

## Fix

- Normalize source-derived ASR records to finite, non-negative media times and sort them chronologically before highlight ranking.
- Repair a malformed end time to a zero-length-or-valid interval at that word's start, bounded by the source duration.
- For each selected highlight, clamp timings to that clip's exact window and recheck chronological order before building captions.
- Keep the shared caption renderer strict for authored/other caption workflows; this fix is scoped to provider-derived Clip Studio timings and does not weaken the validator globally.
- No clip text is changed by the timing repair, no Flow/Veo request is submitted, and original source footage remains unchanged.

## Verification

Full suite: **510 passed, 5 skipped, 12 existing deprecation warnings**.

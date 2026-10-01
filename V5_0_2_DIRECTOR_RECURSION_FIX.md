# v5.0.2 — Director recursion hotfix

Fixes a production-planner crash seen with some 60-second narrations where Whisper timing can leave an overlong sentence segment that cannot be split further.

## Symptom

`RecursionError: maximum recursion depth exceeded in comparison` from `engine/planning/director.py::_split_long_sentences`.

## Fix

- Replaces recursive sentence splitting with a bounded iterative work queue.
- Requires each split to make measurable timing progress before re-queuing it.
- Handles long segments containing fewer than six timed words instead of returning them unchanged and recursing forever.
- Preserves unsplittable timing segments rather than crashing or dropping narration.

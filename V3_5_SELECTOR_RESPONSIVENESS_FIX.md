# v3.5 - Flow selector responsiveness fix

This build fixes a misleading apparent hang on the Flow dashboard.

## Root cause
The old resolver waited the full timeout separately for every candidate selector.
For `new_project`, a 12-second timeout across five candidates could take about a
minute before reaching the visible-text selector that matches the current Flow
New project tile. The prompt box could suffer the same problem.

## Changes
- One shared timeout budget per UI action instead of per selector candidate.
- Poll all candidate selectors rapidly.
- Prefer visible text for the current New project dashboard tile.
- Add step-by-step terminal progress for `flow-direct`.
- Keep review mode non-generating: it fills the prompt and stops before Generate.

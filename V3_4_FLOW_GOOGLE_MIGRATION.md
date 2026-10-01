# v3.4 — flow.google.com migration

Google moved/rebuilt Flow at `https://flow.google.com/`. v3.3 still navigated to the old Labs root, so project discovery failed even though the Wayland browser worked.

Changes:
- Direct app URL is now `https://flow.google.com/`.
- `ensure_project()` reuses an already-open composer, can enter the app, opens an existing project, or clicks `+ New project`.
- New Flow generation flow: current model/type chip -> `Video`, rather than requiring the old `Text to Video` tab.
- Accessible-name regex matching for icon/ARIA controls.
- More prompt and Generate selector fallbacks.
- `flow-direct` is strict about selecting Video so it will not accidentally spend credits on an Image generation.
- Automatic screenshot + JSON UI dump on Flow selector failures.
- New `flow-inspect` command for diagnostics.

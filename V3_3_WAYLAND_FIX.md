# v3.3 — WSLg native Wayland runtime fix

## What was wrong
`browser-test` could prove that bundled Chromium worked with native Wayland, but the
production `flow-open` / `flow-direct` launcher still used the default X11 route. On
machines where WSLg Wayland worked but X11/Xwayland did not, the test passed while the
real Flow launch failed with “headed browser without having a XServer running”.

## Fix
- WSL headed Flow sessions now try native Wayland first using `--ozone-platform=wayland`.
- `DISPLAY` is removed for that launch so Chromium cannot silently choose X11.
- `WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR` are propagated exactly as in the passing
  browser-test variant.
- X11 remains an automatic fallback.
- Browser diagnostics now include a real-profile Wayland probe.
- Misleading “WSLg is dead” advice was replaced with transport-specific guidance.
- Added a regression test ensuring the production launcher actually selects Wayland.

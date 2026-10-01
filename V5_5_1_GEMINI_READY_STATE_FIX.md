# AutoVideoAI v5.5.1 — Gemini Web READY-state fix

## Fixed

`gemini-open` could visibly launch Chromium and then fail with an error ending in `bundled: READY`.
The Gemini browser adapter correctly called `FlowState.READY` after finding the Gemini composer, but the shared browser-state enum did not define `READY`. Python therefore raised `AttributeError: READY`; the generic browser launcher misclassified that post-connect error as a browser launch failure.

v5.5.1 adds the missing `READY` browser state. The persistent Gemini browser can now complete setup and remain open until the user presses Ctrl+C.

No Flow, MovieFlow, rendering, script-timed caption, or provider-routing behavior is otherwise changed.

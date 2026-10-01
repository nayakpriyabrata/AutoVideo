# v5.8.4 settings hotfix

The resume flag correctly saved gemini_chat_cleanup, but Factory._settings omitted it from both global and per-job merge lists. Execution therefore used keep. Both lists now include gemini_chat_cleanup and flow_image_workers. Per-job values override global defaults. Regression tests check effective runtime settings, not just saved JSON.

Stop the dashboard, back up the installation and apply the patch only to 5.8.3:

```bash
patch --dry-run -p1 < AutoVideoAI-v5.8.3-to-v5.8.4.patch
patch -p1 < AutoVideoAI-v5.8.3-to-v5.8.4.patch
```

If dry-run fails, do not force it. The full ZIP includes all prior changes. Preserve your settings, profiles and outputs when upgrading.

```bash
python3 cli.py v3 resume 20260930-104836-winners-mindset-fc4f --gemini-chat-cleanup delete-after-read
```

The first log should now say delete-after-read. This applies to new Gemini requests; it does not retrospectively delete chats from completed script runs. This job already has a script and narration, so resume may not open Gemini.

This release DOES NOT fix the reported Flow recorded-asset-not-visible pause. Do not clear request records or regenerate to bypass it. Diagnosis requires storyboard/shot_001_open.jpg.flow-request.json and storyboard/shot_001_open.jpg.recovery.json from the affected job, with authentication and signed query values redacted but asset IDs and URL paths preserved. Exact asset matching and duplicate-credit protection remain enabled.

Offline tests cover settings precedence. Live Google sessions were not exercised.

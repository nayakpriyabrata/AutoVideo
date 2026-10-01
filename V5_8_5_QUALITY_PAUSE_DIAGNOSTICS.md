# AutoVideoAI v5.8.5 — quality and pause-diagnostics build

This full source ZIP includes the v5.8.4 Settings Hotfix, the audio/caption
improvements in [VIDEO_QUALITY.md](VIDEO_QUALITY.md), and the diagnostic changes
below. It is a testing build. Live signed-in Google sessions were not exercised.

## What the supplied log tells us

The September 30 log reaches script generation, narration, Groq timing and then
Flow storyboard-image tile downloads. The estimated-caption-timing warning is
not the observed stopping point: Flow continues afterwards. Repeated "matched
image" / "opened tile menu" lines alone do not identify the shot, prove duplicate
generation, or establish why the job paused. The excerpt ends before a pause
reason, failed download, traceback or final job status appears.

The dashboard caught some pause exceptions and displayed them only in its UI,
so a terminal log could end at a download line without showing the actual reason.
**This release improves that missing evidence; it does not claim the exact live
Flow pause has been fixed.** Exact asset matching and duplicate-credit protection
remain enabled. Assets that cannot be identified or validated still stop safely.

## New diagnostics

- Saving a pause now prints `[PAUSED]` with job/shot, category, redacted reason,
  and the path to `pause_state.json` in both console and active job runtime log.
- Tile downloads log their output file, download-event arrival, saved byte count,
  or failure. Opening a menu is no longer the last useful diagnostic message.
- A failed initial submitted request now attempts to write `.recovery.json`
  immediately, not only after a later resume. Diagnostic collection inspects only
  an already-owned bridge; it does not launch/restart a browser or submit a prompt.
  Unavailable or stale asset snapshots are explicitly labelled.
- The pause panel offers **Download redacted pause report**. The equivalent CLI
  works offline, even with Chrome closed:

  ```bash
  python3 cli.py v3 support-report YOUR_JOB_ID
  ```

  It prints the path to a new `outputs/YOUR_JOB_ID/logs/support-report-*.json`.
  `--outputs-root /path/to/outputs` is available for a separate installation, and
  `--output new-report.json` selects a new filename. Existing files are never
  overwritten. The command does not construct the Factory or call providers.

The report includes saved pause/progress metadata, bounded recent log lines,
pending Flow request/recovery records, and local file sizes. It does not read
settings, `.env`, browser profiles, media files or script documents. Known credential fields,
authentication strings and signed URL query values are redacted; useful media
IDs/URL paths are retained. Inline data-URI media is replaced with a fingerprint.
**Review the JSON before sharing it**, and never send API keys, cookies or browser
profiles. This is best-effort redaction, not a guarantee against every possible
secret in arbitrary free-form logs.

The production audio mixer also now uses a bounded internal drain guard before
trimming the mixed output to narration duration. This prevents music disappearing
near EOF on the tested FFmpeg 7 build without lengthening the movie.

## Upgrade without losing the paused job

Your folder name `AutoVideoAI-v5.7.0` does not establish which hotfix code is
currently installed. Check `cat VERSION`; the new dashboard title also reads this
file and will show **5.8.5**.

1. Stop the dashboard with **Ctrl+C** before replacing code. Do not run two
   copies against the same job/browser. A submitted Flow request may continue in
   Google's project after the local app stops.
2. Back up your entire installation first, including `outputs/`, `data/`, `.env`,
   `config/user_settings.yaml`, custom presets, media libraries and browser/CDP
   configuration. Do not delete your old installation or request sidecars.
3. Extract the ZIP into a **separate staging folder**, not over the only copy of
   your installation. It contains one top-level folder: `AutoVideoAI-v5.8.5`.
4. After backup, overlay the staged source files into your existing installation
   directory if you want to keep absolute media paths unchanged. The ZIP does not
   contain runtime outputs, SQLite databases, `.env`, user settings or browser
   profiles, so it does not intentionally replace them. It **does** contain
   shipped configuration/preset files: preserve and reapply your custom settings,
   especially the `browser:` block in `config/flow_ui.yaml` if you edited it there.
   Do not blindly restore the old engine over the update.
5. Activate your existing virtual environment (or make a fresh one), install
   `requirements.txt`, then check:

   ```bash
   python3 -m pip install -r requirements.txt
   cat VERSION                         # 5.8.5
   chmod +x dashboard.sh run.sh         # WSL/Linux if needed
   ```

A separate fresh installation is also possible, but copied manifests can retain
absolute references to old media locations. Keep those locations available and
preserve/reapply your saved browser configuration. Do not create a replacement
job simply to clear a pause.

## Safest next step for the reported job

After the upgrade, collect evidence **before resuming or creating any job**:

```bash
JOB_ID=20260930-212349-winners-mindset--for-suc-a5a7
python3 cli.py v3 status "$JOB_ID"
python3 cli.py v3 support-report "$JOB_ID"
```

The ID is inferred from the named Flow project in the supplied log. If it is not
found, use `python3 cli.py v3 queue` to select the actual saved job ID.

You can also diagnose the old installation without overlaying it: run the **new**
ZIP's CLI with your existing Python environment and point it to the old outputs:

```bash
# From the extracted AutoVideoAI-v5.8.5 folder:
python3 cli.py v3 support-report "$JOB_ID" \
  --outputs-root /path/to/your/current/installation/outputs
```

Share the redacted report, or at least the final pause reason and last error.
If your currently installed code cannot export reports, `v3 status` and the job's
`pause_state.json` are the starting point. Remove credentials and signed query
values before sharing any raw file.

For a matching saved pending request, `v3 resume YOUR_JOB_ID` attempts to download
that existing asset without submitting it again. **This protection depends on the
saved request journal.** If an older job has no `.flow-request.json` record, do not
assume resume is duplicate-credit-safe; diagnose its history first. Once recovery
succeeds, later unsubmitted shots can still use the normal configured budget.
`recover-flow-video` is for a pending **video**, not the storyboard **image**
requests shown in these logs. Never clear request records or relax exact matching
to force a job through.

## Build and verification

Rebuild the same source-only distribution with:

```bash
python3 tools/build_release.py
```

Archives are written to `releases/` (ignored by Git). The ZIP includes a
`RELEASE_MANIFEST.json` with per-file hashes, preserves executable shell scripts,
and has a sibling SHA-256 checksum. Source-only packaging excludes credentials,
profiles, outputs, local media libraries, virtual environments and older ZIPs.

Offline regressions cover pause logging/redaction, read-only exports, initial
failure diagnostics, zero resubmission for pending requests, ZIP exclusions and
hashes, plus real FFmpeg/libass quality checks. No generation credits were used.

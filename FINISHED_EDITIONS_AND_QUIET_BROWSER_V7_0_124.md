# v7.0.124 · three languages finish, and the browser stops popping up

Two reports from the same install, plus nine defects found by auditing the shipped suite against a
real FFmpeg. The suite was **12 failed / 1946 passed** before this release and is **1 failed / 1987
passed** after it; the one remaining failure is an artifact of this sandbox's FFmpeg build and fails
identically on the untouched 7.0.123 tree.

> *"I have added some features like to generate videos with three language, however its not generating
> video with 3 language"*
> *"can we do something which will not show me the annoying pop-up chromium browser during the video
> generation process … this create issue when i am working by sharing the screen, i have to stop the
> video generation during that time"*

## 1 · A three-language production re-rendered its editions for ever

**The editions were being made. They were never allowed to count as finished.**

`render_job_editions()` decides what is still pending with `_bundle_is_current()`, and since 7.0.113
it also re-opens an edition through `_captions_contradict()` - "the record says this file is right, but
the picture disagrees". That check compared the burned-caption evidence with the job's wish in **both**
directions:

```python
return shown is not None and bool(shown) != bool(wants)   # 7.0.113 .. 7.0.123
```

Only one of those directions is evidence. A caption is not on screen every second, so sampled frames
that find no text prove nothing - `engine/render/caption_check.explain()` has always said exactly that:

```python
if expected and not result['looks_like_text']:
    # Deliberately not a warning: a caption is not on screen every second, so a handful of samples can
    # land between cues. The check only ever reports text it can see.
    return ''
```

and the render loop only ever sets `captions_disputed` - the "stop re-rendering this for ever" marker -
for the visible-text direction. So a language whose transcript is **on** had no escape hatch at all:

```
Hindi export, captions_burned = True      (the file really does carry them)
caption_check.probe()  ->  15.53 % bright / 2.32 % edges  ->  looks_like_text = False
                                    EDGE_RATIO threshold is 3.5 %, so a bright, high-contrast
                                    picture alone hides the glyphs from the heuristic
_captions_contradict(wants=True)  ->  False != True  ->  True  ->  Hindi is pending again
```

Every run therefore re-encoded Hindi into a brand-new `language_editions/<stamp>/exports/` folder, and
`_mark_superseded()` stamped the previous file *"this is not the current video"* - a marker that was
itself about to be replaced. Consequences, all observed:

* a second `render_job_editions()` on an unchanged job returned a **different path** for Hindi;
* `edition_diagnosis()` - which only calls `_bundle_is_current()` - reported `exported` while the
  renderer reported `pending`, so the Three-language panel and the job disagreed about the same file;
* a job could never reach "every selected language is exported", so resume, repair and the
  *Add intro/outro and render pending language editions* button each re-ran the whole render stage
  instead of finishing - minutes of FFmpeg per language, per press, for ever.

Now the contradiction is one-directional, matching the check's own documented contract:

```python
if wants:
    return False      # asked for a transcript: undetected glyphs are not a defect
```

"Shows text although this job asked for none" still forces exactly one repaint and is then marked
`captions_disputed` and explained - the 7.0.113 field defect stays fixed.

Also hardened on the way: an entry that says `exported` but carries no readable path used to raise
`ValueError: PosixPath('.') has an empty name` **out of the whole edition loop** - precisely the
one-language-kills-every-language failure 7.0.95 removed for every other cause. It now reads no
provenance and returns "no contradiction".

Three shipped tests pin this and now pass: `test_each_selected_language_is_rendered_with_its_own_narration`,
`test_switching_the_transcript_re_renders_only_that_language`, and a new
`tests/test_v7124_three_language_convergence.py` (11 tests) that also asserts a third run produces the
same two files, that the panel and the renderer agree, and that switching Odia's transcript on repaints
**only** Odia and then settles.

## 2 · No Chromium window during generation - on Windows and macOS too

Quiet browser existed since 7.0.22 and did the right thing on Linux/WSL: a headed browser on a private
hidden `Xvfb` display, with a localhost-only password-protected VNC viewer for sign-in. Everywhere else
it refused:

```python
if os.name != 'posix' or not Path('/proc').exists():
    raise RuntimeError('Quiet browser currently supports Linux/WSL only')
```

and the SETTINGS box said so - *"Quiet browser · experimental (Linux/WSL)"*. On Windows the popup was
therefore unavoidable, which is exactly the report above.

`engine/quiet_browser.py` now hides a browser on every OS, and stays **headed** everywhere:

| | mechanism | Show browser |
|---|---|---|
| Linux / WSL | private hidden X display (`Xvfb`), unchanged | VNC viewer on the same display, unchanged |
| Windows / macOS | headed window parked at `--window-position=-32000,-32000`, `--mute-audio` | moves **that same running window** on-screen over a loopback debugging port |

An off-screen headed window is never drawn, so a screen share, a recording or a presentation cannot
pick it up - and because it is not headless, the Google session, cookies, dialogs and Flow downloads
all behave exactly as they do visibly. `--headless` is deliberately **not** used: Google refuses a
headless sign-in.

The details that make it safe:

* **A sign-in is never hidden.** *FLOW SESSION → Open Flow* launches with `quiet=False`, and
  `_post_connect()` reveals the window by itself when it hits a sign-in wall, then conceals it again
  once `is_logged_in()` - the same session, no restart, so the authenticated profile is the one
  generation keeps using. An already-signed-in quiet session is never revealed at all.
* **Show / Hide are one button in the sidebar** and only appear when there is something to show. Both
  move the existing window through `Browser.getWindowForTarget` / `Browser.setWindowBounds`; neither
  restarts a browser or a profile, matching the 7.0.22 promise.
* **The debugging port is best effort.** If it cannot be allocated, or a launch with it fails, the
  launcher falls through to the same hidden window without it (`quiet-hidden-window-noport`) - losing
  the reveal handle never costs a hidden browser. Chromium binds it to `127.0.0.1` only.
* **CDP mode still refuses.** Quiet mode cannot hide a window you own; the message now says to pick
  bundled/system, or turn Quiet browser off, instead of the old "needs a local Linux browser".
* **Flow Music is quiet too**, via `launch_plan(cfg, record=False)` so a short-lived music browser
  cannot overwrite the Flow window handle the button reads. A music login stays visible.
* `browser_environment()` keeps its exact contract - a missing `Xvfb` still raises *"Quiet mode did not
  open a visible browser"* rather than falling back to a window.

`tests/test_v7124_quiet_browser_all_os.py` (19 tests) pins all of it, including that a quiet launch
passes `headless=False`, that an ordinary launch is byte-for-byte unchanged, and that the Linux VNC
path still starts `vncviewer` and nothing else.

## 3 · The Uploads picker could navigate away from your project

`_picker_uploads()` had lost the contract `tests/test_v758_uploads_picker.py` was written for:

```python
if not scope:
    return self._click_text_action('Uploads', timeout_ms=700)   # <- the MAIN SIDEBAR
```

When the media picker could not be identified, this clicked *Uploads* in Flow's main sidebar - leaving
the project in the middle of a generation and losing every reference attached so far. It had also lost
its `timeout_ms` parameter (four tests raised `TypeError`), gave every retry a fresh 1500 ms instead of
sharing one budget, and had no answer for a tab whose own text node Playwright reports as unstable.

Now: bounded by one deadline, scoped (no picker → `False`, never the sidebar), and an unstable tab is
retried through its clickable ancestor - still without `force`, because a forced click lands on
whatever is underneath, which is how a wrong tile used to be attached. `_finish_agent_media_picker()`
also re-selects Uploads before reaching for the exact row again: the first click often lands before
Flow has swapped the tab's contents, so the row was not in the list yet.

The retry keeps the no-argument call, because `tests/test_v757_reference_picker.py` binds
`_picker_uploads=lambda: True`; both suites pass (10 tests).

## 4 · One channel mark per frame, not three

`render_overlay_png()` drew the playful pill badge with the channel name **and** then composited the
logo into the bottom-right corner - where `build_overlay_assets()` also schedules a separate `logo`
overlay that has stayed there since 7.0.109. A branded video therefore carried a name pill plus the
same logo twice, on every frame:

```
getbbox() = (134, 37, 1853, 1043)   expected (134, 37, 234, 87) - the 100x50 logo, nothing else
```

A channel logo **is** the channel mark: with one available the badge is not drawn at all, and the
trailing composite now only serves `intro`/`outro`. Without a logo the badge is the mark, exactly as
before, so an unbranded video is unchanged.

## 5 · Six more defects from the same audit

* **Project deletion stopped before deleting anything.** `flow_project_delete.delete()` did a blocking
  `wait_for(state='visible')` on the *first* menu item (`Rename`). A menu that was merely slow to
  animate was indistinguishable from the missing success toast at the end, so it raised *"No explicit
  success confirmation"* before `Delete` was ever clicked. It now polls the three items inside one
  deadline, and the two proofs - the right menu, then Flow's explicit toast - stay separate.
* **Gemini review attachment.** `_attach_files()` handed the file chooser a one-element list; the
  chooser callback is written for a bare path. A single review proxy is now passed as a path (a list
  is still used for the multi-image case).
* **Streamlit deprecation.** `st.dataframe(..., use_container_width=True)` is deprecated and going
  away; three call sites (`app.py`, `engine/channel_desk_ui.py` x2) now use `width='stretch'`.
* **Create step 4 control name.** The TTS selectbox had been renamed to *"TTS provider for the selected
  language batch"* in 7.0.82, which left `test_studio_music_only_plan_persists_independent_switches`
  unable to find the control it asserts is disabled in Music-only mode. The label is `TTS` again and
  the explanation moved into the control's own help text, so nothing is lost and the assertion that
  *Music only disables TTS and Speech captions independently* holds.

## Verified

* A pristine v7.0.123 checkout and the v7.0.124 tree, both under the same real FFmpeg: **12 failed / 1946
  passed** before, **1 failed / 1987 passed** after. The single remaining failure is environmental (below).
* `tests/test_v7124_three_language_convergence.py`, 11 new tests with real FFmpeg media and no Gemini, TTS or
  Flow call: a second and a third `render_job_editions()` return the same two files, nothing is superseded, the
  Three-language panel and the renderer agree the job is exported, an undetected transcript does not make an
  edition pending again, the v7.0.113 direction (text on screen when none was asked for) still repaints exactly
  once and is then disputed and explained, switching Odia's transcript on repaints **only** Odia and then
  settles, and an `exported` entry with no readable file cannot raise out of the loop.
* `tests/test_v7124_quiet_browser_all_os.py`, 19 new tests: the hidden-window arguments, a per-OS launch plan,
  `browser_environment()` refusing on Linux without `Xvfb` and on every other OS, the settings copy, a quiet
  launch passing `headless=False` and off-screen, an ordinary launch byte-for-byte unchanged, `quiet=False`
  forcing a visible window for a login, CDP still refused, a Windows `.exe` from WSL still ignored, a refused
  debugging port still producing a hidden headed window, CDP reveal/hide bounds on the same process, the
  unchanged Linux `vncviewer` path, a login wall revealing and then concealing, an already-signed-in session
  never revealing, and Flow Music quiet without overwriting the Flow handle.
* Three shipped tests that pinned the convergence bug and now pass:
  `test_each_selected_language_is_rendered_with_its_own_narration`,
  `test_switching_the_transcript_re_renders_only_that_language`, and the two dashboard tests.
* Full suite re-run from the **unzipped release folder**, not the working tree: `compileall` clean, same result.
* Updater: dry run, `--apply`, backup, idempotent re-run, edited-file guard (a locally edited
  `engine/quiet_browser.py` is preserved and nothing is changed), chain guard from 7.0.122, and an updated
  install passing `test_tools_folder_ships_only_the_current_updater`.
* The patch `AutoVideoAI-v7.0.123-to-v7.0.124.patch` applied to a pristine 7.0.123 tree reproduces the release
  tree exactly.

## Reproducing

```bash
python -m pip install -r requirements-test.txt
sudo apt-get install -y ffmpeg fonts-dejavu-core
python -m pytest -q -rs                       # 1987 passed, 4 skipped
python -m compileall -q engine tools app.py cli.py
```

`test_a_render_records_what_the_picture_shows` measures glyph brightness in a rendered caption band and is
sensitive to the FFmpeg/libass build; it fails identically on the untouched 7.0.123 tree under the FFmpeg
available here and is not a 7.0.124 regression. It passes under the FFmpeg 6.1 the CI workflow installs.

## Install

Stop the dashboard, extract the zip beside your installation, then from inside the installation folder:

```
python3 ../AutoVideoAI-v7.0.124-Finished-Editions-And-Quiet-Browser/tools/update_v7123_to_v7124.py . --apply
python3 cli.py v3 self-check
```

Then: **SETTINGS → Quiet browser · no visible window (all OS)** so generation never puts a Chromium window on
your screen share. The first Google sign-in still needs a visible window once - use **FLOW SESSION → Open
Flow**, or the sidebar's single *Show browser* button, which moves the same running window on screen and hides
it again; a sign-in wall does that by itself. Your saved jobs, language editions and their exports, speech
batches, Flow journals, character photos, channel profiles and browser profiles are never copied, moved or
deleted, and the files this update replaces are backed up first.

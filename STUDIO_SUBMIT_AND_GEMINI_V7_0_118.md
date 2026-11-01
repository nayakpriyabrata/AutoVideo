# v7.0.118 · Create production works again, and the Gemini video shots are where you can see them

Two things came from the same session: the app refused to create the job at all, and you could not find the
Gemini video option.

Your terminal, verbatim:

```
TypeError: Factory.create_job() got an unexpected keyword argument 'flow_auto_approve_video_requests'
  at app.py:1396
```

That traceback was the whole story, and it was not your typing.

## 1. Every "Create production" submit has been broken since v7.0.106

`engine/studio_config.py` grew a setting called `flow_auto_approve_video_requests` in v7.0.106 (the "approve each
saved Flow video request once" rule). The Studio form sends its **entire** configuration to
`Factory.create_job(...)`, and `create_job()` never learned that one keyword.

* The command line passes its arguments one at a time, so `python3 cli.py v3 create ...` kept working.
* The app failed - always, on every submit, for every video - and only after the form had been filled in:
  `Create plan only`, three languages, 360 s, Storyboard Economy, Flow approval `once`, one card per video.
  Nothing about that configuration was wrong.

v7.0.118:

* `create_job()` accepts `flow_auto_approve_video_requests`, saves it in the job's `settings.json` **and reads it
  back**, so switching it off really does switch automatic approval off. Before this, the key sat in the config
  and never reached the engine.
* The two 76-name key lists inside `_settings()` were also the same list pasted twice. They are now one
  `SETTING_KEYS` tuple, so a new setting cannot be honoured on one path and silently ignored on the other - the
  exact shape of this bug.
* If the app and the engine ever disagree again, you get a sentence instead of a `TypeError`:
  *"This installation mixes two releases: engine/studio_config.py sends X, but engine/factory.py create_job()
  does not accept it. Nothing was created. Repair: ... then check with `python3 cli.py v3 self-check`."*
* **New: `python3 cli.py v3 self-check`** (read-only, seconds, no browser, no credits). It checks the VERSION file,
  the engine imports, the Studio ↔ `create_job()` keyword agreement, and the render/edition modules, and prints
  either `All checks passed.` or the file that is out of step and its repair.
* **New: `python3 cli.py v3 create --no-auto-approve-flow-videos`** for the same choice from the terminal.
* The Create page shows a red banner at the top, before you type anything, if the folder holds two releases.

## 2. The Gemini video option was in the app - inside a collapsed cleanup expander

It lived under `Gemini video and project cleanup`, collapsed, in the middle of a long page. It read as a cleanup
setting, so it was invisible in practice.

It is now a visible section of Create:

```
3b · AI video shots · Flow or Gemini Web
   Gemini Web AI video shots (0-4)
   Approve each saved Flow video request once, automatically   [x]
```

with a plain sentence about where the *exact* shots are chosen. That picker already existed - the job panel's
**Gemini Web video shots** section - and it now:

* can change the cap of a job that was already created (`Gemini Web shots this job may use (0-4)` + a save button,
  or `python3 cli.py v3 gemini-shots <job> --count 2`). Until now a job created with 0 stayed at 0 forever, and the
  panel only told you to "raise it in Create", which an existing job cannot do.
* says the truth for a brand-new plan-only job: *"This job has no storyboard yet, so there are no shots to choose
  between. Run it ... each shot then appears here with why it is - or is not - eligible for Gemini."*
  Previously it claimed every Flow shot already had an accepted take - a state that did not exist.
* still never offers a shot that already has a video or a pending Flow request, so nothing can be generated twice.

After creating a job, the success message now says where the shots are picked, and that nothing is sent to Gemini
before that choice is saved.

## What was verified

* The real Streamlit page, driven by Streamlit's own `AppTest`: topic typed, "Create plan only" ticked,
  **Create production** clicked -> `Job created: 20261029-...`, no exception, the section and both widgets present,
  the picker panel rendered.
* `python3 cli.py v3 self-check` -> `All checks passed.`
* 16 new tests in `tests/test_v7118_studio_create_and_gemini_ui.py`: the keyword parity itself, the setting
  surviving into `settings.json` and changing `auto_allowed()`, a simulated mixed install naming the key and the
  repair, the visible section (and the absence of the collapsed one), the honest empty-storyboard message, the
  per-job cap change through the panel and the CLI, and the CLI switches.
* Full suite: the same 55 pre-existing FFmpeg failures (`drawtext`/`subtitles` missing from the sandbox build) as
  v7.0.117, with 16 more passing tests.

## What this release does **not** do

* Nothing was rendered, re-recorded, resubmitted or charged. No job was created or changed by the update.
* Your 3-language job still has to be created again after updating - the attempt that failed created nothing.
* Whether the Odia file still shows two cards at once is still answered by
  `python3 cli.py v3 language-outputs <job> --card-audit` from v7.0.117, before spending a render.

## Install

1. Stop the dashboard.
2. Extract `AutoVideoAI-v7.0.118-Studio-Submit-And-Gemini.zip` beside your installation
   (`.../Auto/AutoVideoAI-v7`), then from inside the installation folder:
   ```
   python3 ../AutoVideoAI-v7.0.118-Studio-Submit-And-Gemini/tools/update_v7117_to_v7118.py . --apply
   ```
   (dry run first without `--apply`). The updater only replaces the code files listed in it, keeps a backup in
   `code-update-backups/`, and never touches `outputs/`, saved jobs, Flow journals, browser profiles or
   `music_library/`. It refuses to overwrite a file you edited.
3. Restart the dashboard, then run `python3 cli.py v3 self-check`.

If you prefer a clean folder, unzip the release and copy your `outputs/`, `config/user_settings.yaml` and browser
profiles, as with every previous release.

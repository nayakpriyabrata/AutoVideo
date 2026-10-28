# AutoVideoAI v7.0.111 — the render was right; the file you watched was not the new one

You switched the Odia transcript off, rendered again, and the Odia video still had the same Odia captions.

**The render did what you asked.** The job's record and the new export both say *no captions*, and the new Odia
file has none. What was missing was any way to know **which** file was which: every render keeps the earlier video
on purpose, so the job now holds two Odia videos with equally convincing names — and the old one, the one with the
captions you switched off, plays exactly like a fresh render unless something tells you otherwise.

v7.0.111 makes the current file impossible to mix up, and makes the plan unable to resurrect the captions.

---

## 1. Which file is current

### In the app

The **Three-language output** panel (Queue, Create, or Storyboard → job panel) now labels what it plays:

> **Odia** · exported · no transcript
> **This is the current Odia video**: `…-or-edition.mp4` · without a burned transcript · rendered 2026-10-28 06:27
> ▸ **Older Odia videos in this job (not current): 1**
>     `or-20261027-214110-f0e33d42.mp4` · has burned captions · 2026-10-27 21:41

It also warns when the copy in `render/` is not the current export (a player holding that file open on Windows can
block the replacement), and it plays the export itself in that case.

### On the command line

```bash
python3 cli.py v3 language-outputs outputs/<job> --files
```

```text
Odia (or)
  watch: …/render/<job>-or-edition.mp4
  export: …/language_editions/20261028-…/exports/or-20261028-….mp4
  burned captions: no (provenance) · 2026-10-28 06:27 · sha 741e80864a4f
  earlier file (NOT current): …/language_editions/20261027-…/exports/or-20261027-….mp4 · burned captions: yes · 2026-10-27 21:41
No problem found: the files above are current, and their caption state is recorded.
```

`--files` is read-only and never renders. Add `--language or` for one language, `--json` for machine output.
A render now ends with the same list, so the file to watch is printed the moment it is made.

**How the caption state is known:** every export has its own `.provenance.json`, written by the renderer, holding
`captions_burned` and the reason (reviewed script, your correction, or suppressed). For exports older than 7.0.107
there is no provenance, and the listing says *unknown* rather than guessing from the plan.

### On disk

The older export's folder now carries a `superseded.json` naming the current file, so a file manager shows which
video is the earlier version. Nothing is renamed, moved or deleted — the version you already had stays exactly
where it is.

---

## 2. A stale plan can no longer re-burn captions

A plan is a snapshot. One built yesterday with `"captions": true` could be rendered today — after you switched the
transcript off — and it would burn the captions anyway, which is the one way the switch could genuinely be
ignored. Now the **job's setting wins over the plan**:

* the burn is skipped, the export records `captions_burned: false`, `captions_requested_by_plan: true`,
  `captions_job_setting: false` and a `captions_suppressed` sentence saying why;
* the edition's row in the panel says the same thing;
* the guard only ever *removes* captions the job switched off. It never adds captions a plan did not ask for.

---

## 3. What was already verified

To be precise about your job: the export recorded at `language_editions/20261027-214110-f0e33d42/exports/or-…mp4`
has no burned captions, and its copy in `render/` matches it. The Pillow check below is the same one your build
runs: on a test job, the caption band of the transcript-off export is 0.0 % near-white pixels, while the
transcript-on export of the same picture is 1.5 %.

---

## Updating

Stop the dashboard, extract this zip **beside** your installation, then:

```bash
python3 ../AutoVideoAI-v7.0.111/tools/update_v7110_to_v7111.py /path/to/AutoVideoAI-v7.0.110         # dry run
python3 ../AutoVideoAI-v7.0.111/tools/update_v7110_to_v7111.py /path/to/AutoVideoAI-v7.0.110 --apply
```

Code, docs and tests only. `outputs/`, saved jobs, Flow journals, browser profiles and `music_library/` are never
touched; a file you edited yourself is preserved and the run stops and names it. It refuses an installation older
than 7.0.110 and says which earlier update to apply first. Code backups go to
`code-update-backups/v7.0.110-to-v7.0.111-<stamp>/`; a second run says "already up to date".

From 7.0.109 or 7.0.108, apply the earlier zips one at a time first.

---

## Verification

New tests: `tests/test_v7111_which_edition_file.py` (**13**), including three real FFmpeg renders.

* provenance is the proof of what a file burned; a plan is reported as a plan, never as proof;
* the current file and every earlier file are listed, the earlier one marked *not current* with its own caption
  state, and the copy in `render/` is checked against the export;
* a current export that still has the captions, a missing file, and a copy that is not the export each produce a
  message that names the file and the next action;
* a new render writes `superseded.json` beside the previous one, naming the new file;
* a plan that asks for captions is rendered for a job whose transcript is off → `captions_burned: false`,
  `captions_suppressed` set, and the positive control (plan without captions, job off) burns nothing and blames
  nothing;
* a copy that cannot be replaced is renamed `.superseded-<stamp>.mp4`, is no longer advertised, and the record
  points at the export instead;
* **pixel check:** the export rendered without a transcript has no text in the caption band (0.0 % near-white),
  the one rendered with it does (1.5 %), and the two frames differ.

Full suite in this sandbox: **38 failed / 1 782 passed / 4 skipped**, and the pristine 7.0.110 tree fails the
*identical* 38 tests (environment-caused: browser, optional codecs) — no regressions, 13 new tests.

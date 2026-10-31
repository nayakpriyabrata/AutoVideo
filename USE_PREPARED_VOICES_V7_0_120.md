# v7.0.120 · From "my voices are ready" to a job that runs them

You could see and play the prepared narration after v7.0.119 — and then the page stopped. Nothing offered the
next step: *"i can see it, but i don't see how to progress from this or run these assets."*

Two buttons now sit in every finished batch, under **Use these voices**. Neither one generates a video, records
a voice, or spends a Flow credit.

## 1 · Create a production from these voices

This builds a job **whose script is exactly the words the voices speak**:

* an approved plan is written from the batch's own master narration, word for word - the app never rewrites it,
  and the plan stores where it came from (the batch, its scripts fingerprint, its time);
* the job is created from that plan, so the engine's own script is the narration, not a new story written around
  it;
* the English, Hindi and Odia voices are copied into the job (`speech-editions/…`, `production/prepared_speech.json`,
  `production/language_editions.json`), so a Resume reuses them instead of recording anything again;
* the duration comes from the **measured English voice**, not a word count;
* the new job becomes the Active job and the page switches to it, with the confirmation
  *"Created job … Nothing has been generated: its credit cap is 100 Flow credits and the first credit is spent only
  when you press Resume."*

Press **▶ Resume / continue job** when you want it to run. That is the one click that can spend credits.

**Your rights statement is required.** The button asks *"How may this narration be used?"* (I wrote this
narration or own it / I have written permission to use it / it is licensed to me) and only that statement is
written into the plan. The app never assumes it.

## 2 · Attach these voices to a saved job

If you already have a job that approved the very same script, its voices can be attached instead of creating a
new production. Only jobs whose approved script equals this narration are offered, on purpose: the engine reuses
prepared narration only when the script and language match, so attaching to anything else would be refused at
Resume — a promise the app would not keep. Every copy keeps the original files, the job keeps its picture and
plan, and `production/speech_attachment.json` records which batch was attached and when.

If no saved job has this script, the panel says so and points at **Create a production from these voices**.

## Also fixed: a crash in the three-language panel

Wiring this up exposed a real bug: the *"Fix the transcript text"* language picker handed Streamlit a
`LanguagePack` object instead of its label, so opening any job that had a narratable edition raised

```
TypeError: bad argument type for built-in operation
```

and the whole page stopped rendering. It now shows "English / Hindi / Odia". This is the same panel this release
touches, and it is why the new job was opened and checked end to end in a browser-driven test.

## Verified

* 12 new tests (`tests/test_v7120_use_prepared_voices.py`): the plan repeats the narration exactly; no rights
  statement, no plan; unfinished voices are refused by both paths; a job created from voices keeps the words, the
  duration, the three attached languages and **no shots, no Flow request**; attaching refuses a different script
  and a job that has no script yet; whitespace differences still match; the real Streamlit page creates the
  production from a button click, opens it, and shows `SCRIPT ✓`, `VOICE ✓`.
* Full suite on the unzipped release: **36 failed / 1887 passed / 4 skipped** against a pristine v7.0.119
  baseline of **36 / 1875 / 4** - the identical failure list, plus the 12 new tests. All 36 are the sandbox
  FFmpeg build (no `drawtext`/`subtitles` filter).

## Install

Stop the dashboard, extract `AutoVideoAI-v7.0.120-Use-Prepared-Voices.zip` beside your installation, then from
inside it:

```
python3 ../AutoVideoAI-v7.0.120-Use-Prepared-Voices/tools/update_v7119_to_v7120.py . --apply
python3 cli.py v3 self-check
```

The updater replaces only the code files it lists, keeps a backup in `code-update-backups/`, refuses to overwrite
a file you edited, and never touches `outputs/`, saved jobs, speech batches, Flow journals, browser profiles or
`music_library/`.

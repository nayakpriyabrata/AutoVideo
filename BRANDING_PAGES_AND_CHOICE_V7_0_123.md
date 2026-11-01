# v7.0.123 · Branding reaches a job made from prepared voices, TTS has its own page, and a blocked frame can be chosen

Three things from the same install, all real:

> *"I don't see the earlier selected channel profile is attached to either of the language"*
> *"keep the resume of the failed or scripted or planned jobs in this … we can keep the tts in a separate
> section to create a new job out of it, and give user option to attach the channel and character if it's
> missing"*
> *"one of the old failed job, i want you to fix it"*

## 1 · The channel profile you chose in Create now reaches the job

Create step 3 saved a channel profile per language (name, logo, intro, outro). That mapping was **never
recorded with the narration**, and a job created from prepared voices wrote no `production/language_editions.json`
at all - so its Three-language panel could only answer *"no intro, no outro"* and the video carried no channel
branding of its own.

* *4 · Review language scripts → all TTS* now records `channel_profiles` in `batch.json`, per language.
* `create_job_from_batch` applies them: the primary language's own channel name and logo go into the job's
  settings (watermark on), and the job is written the same `production/language_editions.json` Create writes -
  `editions`, `profiles` per language and the attached voices.
* The success notice says what the job got: `… voices attached; cast: Mira the presenter; channel: English → My
  Channel English (logo, intro, outro) · Hindi → … · Odia → …`.
* CLI: `python3 cli.py v3 use-voices <batch> --create-job --rights own_content --channel en=<profile>,hi=<profile>`.

## 2 · Prepared Voices is its own page; Queue & Resume is only about a saved job

The TTS panel, the batch list and the stopped-TTS section moved to **Jobs & Recovery → Prepared Voices** (the
sidebar label is *Prepared Voices · make a job from TTS*).

**Prepared Voices** opens with **Run your prepared voices**: *Batch to run* → **Character in this video** →
**Channel profile · name, logo, intro and outro** (one box per language, pre-filled from the batch) → rights →
**Create the job from these voices**. Then it lists the sessions that still need finishing, the other sessions,
and the stopped TTS runs a finished job no longer needs - nothing removed, nothing deleted.

**Queue & Resume** now answers one question: how do I move this saved job forward? It opens with a one-line
**Resume here** notice and a button to the other page, then the job's monitor, steps, narration, cast, channel,
saved images and Three-language output. Nothing about preparing narration is left on it.

Creating a job lands you on Queue & Resume with the confirmation and `SCRIPT ✓ · VOICE ✓`, because that is where
**Resume / continue job** is.

Because the list is one page instead of two, each option is now the identifying line itself (`Create step 4 ·
2026-10-24 10:10 · English, Hindi, Odia · ready · voices 3/3 · not part of any job yet · newest`) - it reads the
same in the dashboard and in the terminal.

## 3 · Attach a channel profile (and a character) to a job that is already saved

Queue & Resume now has two panels for what a job is missing, both writing settings only:

* **Channel profile · name, logo, intro and outro** - one box per language over the profiles on this
  installation, with *Save the channel profile for this job*. After saving, Three-language output can add the
  intro/outro and render each edition **from the picture the job already has**: no shot is generated again, no
  voice is recorded again, no Flow credit is spent.
* **Cast · who appears in the video** (v7.0.122) - the character, while the job has no storyboard yet.

CLI: `python3 cli.py v3 channel <job>` to read it, `… --set en=<profile>,…` or `… --all <profile>` to attach it.

## 4 · The failed job that could not get past shot_051

```
⚠️ shot_051 opening frame: Flow failed after 1 attempts → free fallback
Cause: FlowRequestPending: Two or more real images are saved for shot_051_open.jpg.
Recovery stopped without submitting or replacing; review the saved Flow project and choose which image to keep.
```

The app was right to stop - it cannot prove which of two generated images belongs to that frame, and guessing
would put the wrong picture in the video. What was missing was a way to *choose*. Both images are already
downloaded as probe files beside the frame, with their checksums in the request journal, so:

* Queue & Resume has **Saved images waiting for your choice**: it shows each frame that is waiting, the request
  text, the saved images side by side, and **Keep this image for …**.
* It commits your choice with the same checksum-verified path the automatic recovery uses, so the frame is then
  a normal saved frame and **Resume / continue job** continues from it.
* Nothing else is touched: no browser opens, no request is submitted, no Flow credit is spent, and the image you
  did not choose stays where it is.
* CLI: `python3 cli.py v3 keep-frame <job>` lists them, `… --image shot_051_open.jpg --keep 2` keeps one.

For that job specifically: open it in Queue & Resume, choose the image in **Saved images waiting for your
choice**, save the channel profile in **Channel profile**, then **Resume / continue job**. The remaining frames
and the shot generation continue from what is already saved - the 2½ hours of Flow work in that project is not
repeated.

## Nothing else moves

No voice is re-recorded, no shot is re-generated, nothing is deleted, and no Flow credit is spent by installing
this release. Saving a channel profile or choosing a saved image only writes settings and copies an image that
Flow already produced.

## Verified

* `tests/test_v7119_queue_narration_and_steps.py` now asserts the batches are on Prepared Voices, with their
  voices playable, and that Queue & Resume lists neither the batch nor its audio.
* 13 new tests in `tests/test_v7123_branding_pages_and_choice.py`: the batch recording its channel profiles, the
  job keeping them (editions, profiles, bundles, channel name, logo, watermark), `--channel` and
  `v3 channel`, an unknown profile refused, the two pages being disjoint (Queue has no picker, Prepared Voices
  has it), attaching branding to an existing job, listing and keeping a blocked image, a changed candidate
  refused, the CLI for both, the page creating a job and landing on Queue & Resume, and the page keeping a
  blocked image, and creating a job landing on Queue & Resume with its confirmation and steps.
* Full suite on the unzipped release compared with a pristine v7.0.122 checkout: identical failure set.
* Updater: dry run, `--apply`, backup, self-check, idempotent re-run, edited-file guard, chain guard from 7.0.121.
* The patch `AutoVideoAI-v7.0.122-to-v7.0.123.patch` applied to a pristine 7.0.122 tree reproduces the release
  tree exactly.

## Install

Stop the dashboard, extract the zip beside your installation, then from inside the installation folder:

```
python3 ../AutoVideoAI-v7.0.123-Branding-Pages-And-Choice/tools/update_v7122_to_v7123.py . --apply
python3 cli.py v3 self-check
```

Then: **Jobs & Recovery → Prepared Voices** to make a job from TTS, and **Queue & Resume** to resume a job,
attach its channel profile, or choose a saved image.

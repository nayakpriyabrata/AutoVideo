# v7.0.122 · Your chosen character actually appears, and every prepared narration is offered

Two reports from the same page, straight after v7.0.121 was installed:

> *"its only showing for the video which is have an activie job already"*
> *"I think another problem is its not picking the selected charecter for the video generation"*

Both were real. The first was the batch picker; the second was the cast, all the way from Create to the prompt.

## 1 · The character you pick is now the character in the video

The cast could be chosen in Create, but only inside a collapsed expander called **"Characters and recovery
preferences · optional"** - after step 4, below the button that starts TTS. A saved character could therefore
sit in Character Library while a video was planned without it. Worse, a job made from a prepared narration
batch passed **no** `character_ids` at all, so its storyboard invented a new person every time.

What changed:

* **The cast is a visible step of Create.** It sits right under *1 · Video setup* with the character cards,
  before the script, the branding and the narration. Under it the page says which character the video will
  show, or, when the box is empty, *"the storyboard will invent a new person"* - the sentence that was missing.
* **The narration remembers it.** *4 · Review language scripts → all TTS* records the selected characters in
  `batch.json` (`request.character_ids`), and `resume` keeps them, so a batch cannot lose the cast.
* **The picker asks for it, and writes it into the job.** *Run your prepared voices* now has a third control:

  ```
  Character in this video · optional (up to three)   [ Mira the presenter ]
  The video will show: Mira the presenter. Their saved photos travel with the job and are reused at Resume.
  ```

  The box is pre-filled with the character saved with that narration. Leaving it empty is allowed - and the
  caption says what that means. The success notice repeats the choice: `… voices attached; cast: Mira the
  presenter`.
* **A job can still be given its character afterwards.** Queue & Resume now has a **Cast · who appears in the
  video** panel. While the job has no storyboard it lists your saved characters and **Save the cast for this
  job** writes exactly the snapshots Create writes, so the next *Resume / continue job* plans that character.
  It refuses once scenes exist - those scenes were compiled for a cast, and changing it quietly is worse than
  saying no. Nothing on this panel generates, records or spends anything.
* **Command line:** `python3 cli.py v3 use-voices <batch> --create-job --rights own_content --cast <id>` and a
  new `python3 cli.py v3 cast <job>` (`--set <id[,id]>` to choose, no `--set` to read).

From the snapshot to the prompt, unchanged and now actually reached: `assign_cast` writes the character into
every shot's subject (`Mira the presenter, preserve face and wardrobe from the attached original character
photo`), and every frame request carries their saved photos.

## 2 · Every prepared narration is offered, not just the newest one

The picker was built from `usable_now`, which deliberately hides a batch **as soon as a job holds its voices** -
right for "what is still waiting", wrong for "what can I run". On top of that, the batch list only read
finished batches inside the *Active* job (`list_speech_batches(..., include_finished=[active job])`), so a batch
that lived in another saved job never appeared at all. With one unused batch in the installation, the list
looked as if only that one existed.

Now:

* **Batch to run** lists every finished narration of the installation: the ones no job holds yet first, newest
  first, then the ones whose voices a job already holds.
* Each line says where its voices live: `voices in job 20261022-143856-…` or `not part of any job yet`, plus
  time, topic, languages and `voices 3/3`.
* Choosing a batch a job already holds warns first: *"Creating a job from them makes a second video with the
  same narration; that job is not changed and nothing is generated until you press Resume."* - a second video
  is allowed, silently duplicating is not.
* `python3 cli.py v3 use-voices --list` prints the same full list and a final line naming every batch a job can
  be made from.

The to-do list further down the page keeps its v7.0.97 behaviour: it still shows only the Active job's batches
and the stopped TTS runs separated out. The picker is the one place that must see everything.

## Nothing else moves

No voice is recorded again, nothing is re-rendered, no Flow credit is spent and no saved job, batch, journal or
browser profile is deleted by this release. The cast of an existing job is only changed when you press
**Save the cast for this job**, and only before its storyboard exists.

## Verified

* 13 new tests in `tests/test_v7122_cast_and_every_batch.py`: the visible Create step and its caption, the batch
  recording the cast (and a resume keeping it), the job made from those voices holding `cast_snapshot.json` and
  `character_snapshot.json`, `--cast` and `v3 cast`, a missing character refused before a job exists, a job with
  scenes refusing a new cast, the picker listing a batch a job already holds (after the unused ones) and a
  finished batch inside another job, the shot prompt carrying the identity, and the real Streamlit page creating
  a job with the character chosen in the panel and saving a cast from the job panel.
* Full suite on the unzipped release compared with a pristine v7.0.121 checkout: identical failure set.
  v7.0.121: 55 failed, 1775 passed, 95 skipped, 11 errors. v7.0.122: 55 failed, 1789 passed, 95 skipped,
  11 errors - the sorted FAILED/ERROR node-id lists are identical (`diff` empty) and the 14 extra passes
  are this release's new tests. All 55+11 are the long-standing sandbox failures (this FFmpeg build has no
  `drawtext`/`subtitles`) and the browser-shim tests.
* Updater: dry run, `--apply`, backup, self-check, idempotent re-run, edited-file guard, chain guard from 7.0.120.
* The patch `AutoVideoAI-v7.0.121-to-v7.0.122.patch` applied to a pristine 7.0.121 tree reproduces the release
  tree exactly.

## Install

Stop the dashboard, extract the zip beside your installation, then from inside the installation folder:

```
# Windows Explorer names the extracted folder after the zip; `unzip` names it AutoVideoAI-v7.0.122.
python3 ../AutoVideoAI-v7.0.122-Cast-And-Every-Batch/tools/update_v7121_to_v7122.py . --apply
python3 cli.py v3 self-check
```

Then: **Queue & Resume** → *Run your prepared voices* → pick the batch → **Character in this video** → rights →
**Create the job from these voices** → **Resume / continue job**. A job that has not planned its scenes yet can
also be given its character from the **Cast** panel on the same page.

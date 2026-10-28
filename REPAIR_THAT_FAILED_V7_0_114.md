# AutoVideoAI v7.0.114 — the repair that stopped half way, and the file it must not hide

You ran the repair 7.0.113 introduced and it stopped:

```
[ 50%] Rendering Odia edition Odia
"error": "FFmpeg failed: av_interleaved_write_frame(): Input/output error
          Error writing trailer of .../.render-j06ayvm3/picture-fit.mp4: Input/output error"

Odia: no current video yet
! Odia has no current export, only earlier files. Render that language again.
```

The repair logic is fine — the render itself could not write. What was wrong is everything the app said about it:
it named a file in a temporary folder that had already been deleted, it did not mention the volume it could not
write to, and it then told you that you had no Odia video at all, while your previous Odia video sat on the disk,
complete. That is what this release fixes.

## What "Input/output error … Error writing trailer" means

FFmpeg says this when the **volume cannot take the rest of the file**: the disk is full, the folder is over quota,
read-only, or a drive/network share went away. It is not a codec problem and it is not caused by your script or your
narration. The two things to check are free space on the drive holding `AutoVideoAI-Shared`, and whether that folder
is still writable.

Two things made it worse in 7.0.113 and are fixed here:

* **the working picture was written twice.** When a narration is longer than the picture, the render makes a retimed
  copy of the picture first — a working file that is decoded again immediately and never played. It was being written
  with `+faststart`, which rewrites the whole file a second time *at trailer time* — precisely the moment this render
  died — doubling the writes on the drive that was already short of room. It is now written once, without it.
* **a failed render hid the file you had.** The language's record was replaced by the failure, so a video that was
  still on disk became "no current video yet".

## What the messages say now

A failed FFmpeg write now reports the file, the volume, and the room left on it:

```
FFmpeg failed: … Error writing trailer of …/picture-fit.mp4: Input/output error
The file being written was …/picture-fit.mp4. Disk free on that volume: 0.6 GB free of 465.7 GB (…).
This is what a full or read-only volume looks like to FFmpeg ("Input/output error", "No space left on device").
Free space there — the earlier exports and the working copies in render/ are the biggest files — or point the
outputs folder at another disk, then run the same command again: finished languages are not redone, no voice is
re-recorded and no Flow credit is spent.
```

And the listing keeps your file visible:

```
Odia (or)
  no current video: the render did not finish
  unchanged file from before it: …/language_editions/20261027-214110-f0e33d42/exports/or-…mp4 · burned captions: yes
  ! Odia has no current export because the render did not finish: FFmpeg failed: … Input/output error. The file from
    before it is unchanged at …/or-…mp4 - that is still the version you have, not a repaired one. Fix the cause above
    and render that language again.
  ! Disk free on the volume holding this job right now: 0.6 GB of 465.7 GB (…). The render that failed needed room
    there for a working copy of the fitted picture, as large as the video itself.
```

The job summary line becomes `Odia: repair did not finish · previous file kept: or-….mp4 · captions: yes` instead of
`no current video yet`, and the panel's next action is the command that retries it, not advice to press a button that
cannot help.

## How to finish your Odia video

1. **Free some room** on the drive holding `AutoVideoAI-Shared` — the earlier exports (`language_editions/`,
   `primary_branding/`) and the copies in `render/` are the big files. A fitted repair needs roughly one extra
   copy of the video while it works.
2. Run the same command again:

   ```
   python3 cli.py v3 language-outputs 20261022-143856-7-small-daily-habits-tha-9729 --fit-hold 8
   ```

Odia is the only language still not current, so only Odia is rendered: Hindi and English are not redone, no voice is
re-recorded, no Flow credit is spent. The new file is written next to the old one, the old one stays as the earlier
version, and the listing should then read `burned captions: no` with `no burned transcript detected`.

If the listing still reports less free space than the video's size, the retry will fail the same way — the numbers
are printed for exactly that reason.

---

## Updating

Stop the dashboard, extract this zip **beside** your installation, then:

```bash
python3 ../AutoVideoAI-v7.0.114/tools/update_v7113_to_v7114.py /path/to/AutoVideoAI-v7.0.113         # dry run
python3 ../AutoVideoAI-v7.0.114/tools/update_v7113_to_v7114.py /path/to/AutoVideoAI-v7.0.113 --apply
```

Code, docs and tests only. `outputs/`, saved jobs, Flow journals, browser profiles and `music_library/` are never
touched; a file you edited yourself is preserved and the run stops and names it. It refuses anything older than
7.0.113. Code backups go to `code-update-backups/v7.0.113-to-v7.0.114-<stamp>/`.

---

## Verification

New tests: `tests/test_v7114_failed_repair_keeps_file.py` (**6**), real FFmpeg renders where they matter.

* the retimed working picture is written once — no `-movflags`, no `+faststart` — while still holding the last frame
  and stopping at the narration length;
* a real FFmpeg write failure reports the file, the free space on that volume, what the error means, and that a
  retry costs no Flow credit;
* a failed repair keeps the previous export as `kept_export` in the record, names it in the panel diagnosis, says
  "nothing was lost", and offers the retry command instead of a dead-end button;
* the listing shows that file as *unchanged, not repaired*, with its real caption state, and measures the volume
  again; the one-line summary says `repair did not finish · previous file kept`;
* the language stays pending, so re-running after the cause is fixed exports a new file with `captions_burned:
  false`, keeps the old one, and drops the shadowing entry.

Full suite: **28 failed / 1 825 passed / 4 skipped**, against a pristine 7.0.113 tree failing the *identical* 28
tests (browser/codec availability in this environment). No regressions; 6 new tests.

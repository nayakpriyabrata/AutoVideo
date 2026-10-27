# AutoVideoAI 7.0.95 · a three-language production now produces three videos

## What was wrong in 7.0.94 (audited, with the exact code path)

Selecting English + Hindi + Odia in Create, with a reviewed language batch, was
supposed to produce three videos. The edition renderer itself worked: its own
tests pass with real FFmpeg media and three different voices. The failures were
in the **gates around it**, and every one of them ended the same way — the
English master is rendered, the extra editions are not, and the only clue is a
single sentence in the job warnings.

1. **One language aborted every language.**
   `render_job_editions()` raised `ValueError` for the whole job when *any*
   extra language was missing a narration, when the clean visual master was
   missing or changed, or when the plan for the *first* pending language was
   rejected. Factory caught that one exception, added one warning, and the job
   ended with the primary video only. Hindi could be perfect and Odia's bundle
   absent — no Hindi video was made either.

2. **A review mismatch was a refusal, not a warning.**
   `finishing_studio.create_plan()` raised
   *"Hindi text cards are on, but this language was prepared without cards"*
   when the Create "Include text cards" box was switched on **after** the batch
   was prepared, and *"points and cards were not saved"* when an educational
   batch had no `speech_cards.json`. Either message stopped the plan for every
   language. Reproduced before the fix:

   ```
   ValueError: Hindi text cards are on, but this language was prepared without cards.
   Prepare the language batch again.        -> 0 extra videos (English only)
   ```

3. **Nothing prepared the extra narrations by default.**
   `prepare_audio` was written to `production/language_editions.json` only when
   the Create box *"Also prepare every selected language automatically during
   production"* was ticked (default: off), and
   `speech_cards.prepare_selected_editions()` returned immediately when the flag
   was false. A production that selected three languages but did not complete the
   manual step-4 ritual rendered **one** video, because no other narration ever
   existed.

4. **Create refused to continue without that ritual.**
   `len(batch_languages)>1 and not (studio_voice_on and use_prepared_batch)`
   blocked "Create production" with a warning. The only way through was: draft
   one script → localize two → approve each → TTS all three → review all three →
   tick "reuse this exact batch" → create. Any skipped step produced either
   nothing or an English-only job, with no lasting explanation.

5. **A failed edition preparation killed the job.**
   `prepare_selected_editions()` was called unguarded in the narration stage, so
   a Gemini localization error or a TTS quota error raised out of the whole run:
   no English video either.

6. **No clean picture, no editions, forever.**
   `production/visual_master.json` is written only by the staged FFmpeg renderer.
   A production that used the MoviePy fallback (or an interrupted render) has no
   clean picture, so every edition was refused with *"The clean visual master is
   missing. Render this production again"* — and rendering again reproduced the
   same fallback. There was no recovery path from the UI at all.

7. **The result was never explained.**
   `language_edition_panel()` returned early when no extra edition was recorded,
   so a job with three selected languages and no narration showed **no panel**.
   The reason existed only inside `language_editions_render.json` and one line of
   `details.txt`. Nothing told the user which language was missing or what to do.

8. **One channel could hold only one logo.**
   A channel profile stored a single `assets['logo']`, and the Create page saved
   a profile per language using the *same* slug for the same channel name, so
   each save overwrote the previous logo. Uploading an English, Hindi and Odia
   mark for one channel ended with one logo used by all three videos.

## What 7.0.95 changes

### Every language is attempted on its own
`render_job_editions()` builds **one plan per language** and records a status per
language: `exported`, `failed`, `needs_narration`, `needs_picture` or `pending`.
A missing narration, a rejected plan or a failed render names that language and
the remaining editions still render. Nothing falls back to the English voice.

### Recoverable review mismatches are warnings
A batch prepared without text cards renders that edition **without cards** and
records `cards_warning`. A missing educational points file keeps the plain cards
and records why. The other languages are untouched.

### Preparation happens by default, and cannot kill the job
- Create: *"Also prepare every selected language automatically during
  production"* defaults to **on** for a multi-language production.
- `prepare_selected_editions()` prepares any selected language that has no saved
  bundle even when the flag is off; a complete saved batch is reused exactly as
  before (no repeat TTS).
- The call is wrapped: a localization/TTS failure now records
  `narration_error` in `production/language_editions.json`, logs
  `language_narration_error`, and the primary master still renders.

### A missing clean picture can be recovered (opt-in)
`ensure_visual_master(allow_recovered_picture=True)` copies the finished master
picture (`-map 0:v:0 -an -c:v copy`) into `render/visual-master.mp4` and records
`"recovered": true` with the note that the copy may still show the primary
edition's burned captions, text cards and channel mark. The job panel offers it
as a checkbox; the CLI offers `--recover-picture`. It is never used silently.

### The result is explained, per language
- Every job that selected extra languages shows a **Three-language output** panel
  (in Create and in Jobs & Recovery). Each language lists its status, whether the
  copy is in `render/`, its warning, and the one action that unblocks it.
- `python3 cli.py v3 language-outputs <job> --explain` prints the same diagnosis
  as JSON. It renders nothing.
- The final job warning names every language that did not render and why.

### Three language logos in one channel profile
- A profile can store `assets['logo-en']`, `assets['logo-hi']` and
  `assets['logo-or']` next to the shared `assets['logo']`.
- `save_profile(..., logos={'en':…, 'hi':…, 'or':…})` snapshots each mark.
- The edition renderer uses `logo-<language>` first and the shared logo second,
  so a Hindi video gets the Hindi mark and Odia gets the Odia mark.
- **Create** has a new step 3, *"Three-language branding · logos, channel names,
  profiles"*: one form saves a channel with its English, Hindi and Odia logos,
  the three channel names, and an optional intro/outro; that profile is then used
  for every selected edition. A profile created in the **Finishing Studio**
  appears in the same picker, so the same artwork is reused instead of uploaded
  twice. A table shows, per language, the profile, the channel name, whether the
  logo is language-specific and a preview.
- **Finishing Studio** shows the same three logo fields and prints which logo an
  edition will use.
- The primary (English) edition takes its name and logo from the primary
  language of the profile, so all three videos are branded consistently.
- Separately-saved per-language profiles still work (for channels that really are
  different); that path is now the secondary option.

### Executables are resolved like the rest of the app
The finishing/edition renderer called a bare `ffmpeg`/`ffprobe`. It now resolves
`ffmpeg` through `imageio_ffmpeg` exactly like the main renderer and raises a
clear message when `ffprobe` is missing, instead of a `FileNotFoundError` inside
a language edition.

## Using it

1. **Create → Reels & Long Videos.**
2. Step 1: choose the master language and up to two additional editions.
3. Step 3 (**Three-language branding**): type the channel name, upload the
   English, Hindi and Odia logos, optionally the three channel names and one
   intro/outro, then **Save this channel with its three language logos**. Leave
   *"Use this profile for every selected edition"* ticked.
4. Step 2: approve the master script (as before).
5. **Create production.** The job localizes the approved master, synthesizes
   every selected language, renders the primary video, then renders each edition.
   Watching step 4 first is still the way to review every narration before TTS is
   spent — its saved batch is reused instead of prepared again.
6. Check **Three-language output** under the job (or in Jobs & Recovery).

Existing jobs (7.0.68 – 7.0.94) keep their saved state. Their missing editions
now appear in the panel with the reason; preparing the narration batch from Jobs
& Recovery > Speech batches, then pressing
**"Add primary intro/outro and render pending language editions"**, renders them.

## Limits and review points

- Hindi and Odia wording still needs a fluent reviewer before publishing.
- The extra narration is prepared during production when no reviewed batch
  exists; that spends TTS once per language. Localization uses the Gemini Web
  session, so the browser must be signed in (as for script drafting).
- If a language's narration is more than 25 % longer than the approved picture,
  that edition still fails with a message asking for a shorter script. That is
  unchanged and intentional: speech is never cut to fit silently.
- A recovered picture master can show the primary edition's burned captions and
  channel mark. Re-render with FFmpeg to get a clean one.
- Editions still do not carry production-only extras (ambience, sound effects,
  B-roll graphics from the English timeline).
- Live Gemini Web, TTS and Flow accounts were not exercised here. The automated
  tests use real FFmpeg media and synthetic narration.

## Verification

- `tests/test_v795_three_language_render.py` (16 tests, real FFmpeg):
  a missing narration, a rejected plan and a failed render each leave the other
  languages exported; a batch prepared without cards renders with a warning; a
  missing points file keeps plain cards; a missing picture master is explained and
  can be recovered; the diagnosis names each language; the extra narration is
  prepared without the automatic checkbox while a complete saved batch is not
  re-prepared; one profile stores three logos; a language without its own logo
  uses the shared one; the edition plan carries the language logo; the Create
  page, panel, CLI and Finishing Studio wiring.
- Updated tests record the intended behaviour change:
  `test_v768…::test_missing_reviewed_narration_is_refused_for_that_language_only`,
  `…::test_create_page_prepares_extra_editions_instead_of_refusing_them` and
  `test_v777…::test_plan_without_prepared_cards_renders_that_edition_without_cards`.
- Full suite against the 7.0.94 tree: the same 26 environmental failures
  (fonts, browser fixtures, ffprobe/encoder differences), 1517 passing,
  0 new failures.

## Upgrading an installed 7.0.94 folder

Stop the dashboard first. Extract the 7.0.95 zip beside your installation folder,
then run from the installation folder:

```
python3 ../AutoVideoAI-v7.0.95/tools/update_v794_to_v795.py .            # dry run: shows the plan
python3 ../AutoVideoAI-v7.0.95/tools/update_v794_to_v795.py . --apply    # installs the code
```

The updater replaces only the code and documentation files listed in its plan,
refuses to run if a listed file was edited locally or the installed version is
not 7.0.94 (or an already-updated 7.0.95), backs the replaced files up under
`code-update-backups/v7.0.94-to-v7.0.95-<timestamp>`, and leaves outputs, saved
jobs, browser profiles, music, characters, uploaded logos and channel profiles
untouched. Existing single-logo profiles keep working; open the profile in Create
to add the Hindi and Odia marks.

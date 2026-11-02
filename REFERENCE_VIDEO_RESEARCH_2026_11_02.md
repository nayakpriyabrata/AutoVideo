# Reference-video teardown · what three top-performing Hindi/English education videos do, and what AutoVideo should copy

Reviewed 2026-11-02 from the three links supplied with the request. All three are education/self-development
videos; two are Hindi/Hinglish, one is English. They were picked well: two of the three are in the millions
of views, so the patterns below are not one creator's quirk.

| | SeeKen · *Your DoomScrolling Ends Here.* | The Urban Fight · *Tell Me About Yourself* | Riya Upreti · *Become a Dangerously Good Communicator.* |
|---|---|---|---|
| ID | `o2yGmRF_0vg` | `EzGH3hZuJVk` | `lPWeEX5XEpk` |
| Length | 19:48 | 07:48 | 18:14 |
| Views / likes | 25,893 / 909 | **24,090,654 / 1,262,021** | 2,634,124 / 44,369 |
| Published | 2026-11-01 | 2018-10-25 | 2026-09-27 |
| Language | Hindi / Hinglish | English | Hindi / Hinglish |
| Shape | metaphor cold-open → 7 chapters → named framework card → 21-day challenge | anecdote cold-open → **spoken numbered roadmap** → formula → bonus | contrarian hook → credibility proof → authority anchor → 5 numbered principles → named mental model → 30-day challenge |

## 1 · The four beats all three use

### 1.1 A cold-open that is *not* the topic

Nobody opens with "in this video we will learn about X".

* SeeKen opens with a **restaurant where eating makes you hungrier** - a metaphor for scrolling. 3:54 of
  runtime before the word "dopamine" appears.
* The Urban Fight opens with a **personal failure**: *"I said 'Hi, I'm doing my MBBS' … The problem was
  I'm an engineering graduate."* The viewer is told the answer is coming but first is told why the asker
  can be trusted to give it.
* Riya Upreti opens **contrarian**: "this world isn't fair … especially to people who can't communicate".

AutoVideo today writes `HOOK_101` as a first-person address to the viewer and then goes straight to the
outline. There is no room in the schema for an opening that is a *scene* rather than a statement.

### 1.2 An explicit, numbered roadmap spoken out loud

The Urban Fight, at ~0:40, says the roadmap: *"in today's video we are going to 1) what the interviewer
wants 2) a formula 3) bonus: English fluency"*. Riya Upreti does the same with five numbered principles,
and SeeKen with seven chapters. This is the single most transferable beat in all three: it is cheap, it is
structural, and it tells the retention curve where every payoff is.

**AutoVideo already has the machinery and does not use it.** `engine/speech_cards.py` builds an
`OUTLINE_CARD` for longer videos, and `plan_speech_cards()` emits `chapter` cards - but the outline is a
list of headings, not a spoken promise, and `render_language_outputs()` renders chapter cards only when
`cards_enabled` is on. There is no beat that says the numbers out loud.

### 1.3 A named framework / mental model card

* SeeKen: **3R RESET = Recognize / Reflect / Redirect**
* Riya Upreti: **WIIFM — "What's In It For Me?"**

These are the frames the viewer is meant to remember and repeat. They are given a *name* and a *fixed
number of parts*, which is what makes them shareable and what makes them a card rather than a paragraph.
This is the "text pop-up card" pattern the request asks about: a card whose value is the name, not the
amount of text.

### 1.4 Credibility, then authority, then the promise

Riya Upreti sequences three distinct trust beats in the first 90 seconds: her own reach (1.5 M Instagram
followers / 200 M monthly), then an **authority anchor** (Dale Carnegie, *How to Win Friends and
Influence People*, 1936, written in the Great Depression; plus the Warren Buffett public-speaking-course
story), then what the video will do for you. SeeKen does the same with Katy Tam & Michael Inzlicht's 2024
digital-switching research and Nir Eyal's *Indistractable* + the 10-Minute Rule.

A citation is a **card**, not a caption. AutoVideo's card types are `fact`, `hook`, `contrast`,
`chapter`, `stat`, `question`, `step`, `quote`, `summary`, `outline`, `watermark`, `logo`. There is no
`source` or `citation` card - the closest is `quote`, which has no author/year slot in the schema.

### 1.5 A dated challenge as the CTA

Both long videos end with a **challenge**: SeeKen a 21-day one, Riya Upreti a 30-day one, each tied to a
community/app. AutoVideo has three CTAs and they are all generic: *subscribe*, *like*, and
`CTA_SUBSCRIBE_LIKE_AND_COMMENT` with a 5-word minimum. There is no CTA that gives the viewer a task.

### 1.6 All three ship a timestamped chapter list in the description

Every description carries the full `00:00 …` chapter list. This is a YouTube-side ranking and retention
feature that costs nothing once you already know your chapter start times - and AutoVideo already computes
them (`plan_speech_cards()` returns `events` with `start`, and `burn_cards()` gets them per shot).
Nothing writes them out.

## 2 · Ranked, easiest-first implementation plan

Each row says what to change and where; nothing here needs a new provider or a new dependency.

### A. Chapter list in the description — trivially easy, zero risk

The description is already assembled per language. Add the `MM:SS Title` block from the same
`events`/`chapters` that `burn_cards()` uses, so the description and the burned chapter cards can never
disagree. This is the highest value-per-line change in the whole list, and all three reference videos do
it.

### B. A `roadmap` beat — easy

One new beat between the hook and the first chapter whose script is the numbered list spoken aloud
("today we will cover three things: one …, two …, three …"). `speech_cards.py` already has
`OUTLINE_CARD`; the change is to *speak* the outline, not only show it, and to derive the numbers from
the chapter list rather than from a fixed template. Because it is generated from the same chapter list as
(A), the two cannot drift.

### C. A named-framework card type — easy

Add a card kind that carries **a name plus a fixed number of labelled parts** (3R Reset → Recognize /
Reflect / Redirect). It renders as a centred plate with the name in the brand colour and the parts
beneath - which is exactly the shape of the pop-up cards in the reference videos, and it degrades
gracefully to one line per part on a 9:16 canvas. AutoVideo's card renderer already handles per-language
text and safe-area scaling, so this is a template plus a schema field, not new render code.

### D. A `source` / `authority` card — easy

`quote` already exists; give the schema an optional `source` with author, work and year, and render it as
a small attribution line under the quote. Then the Gemini script prompt can be told to produce at least
one authority anchor per long video. Riya Upreti's Carnegie/1936 beat and SeeKen's Tam & Inzlicht 2024
beat are both this card.

### E. A cold-open beat that is a scene, not a statement — moderate

`HOOK_101` is first-person address. Add an opening beat kind that is a **metaphor or a first-person
anecdote**, with the topic withheld for a beat. This is a prompt change plus a beat type; the risk is
script quality, which is why it is ranked below the structural ones.

### F. A challenge CTA — moderate

Add a CTA that assigns a task with a duration ("try this for 21 days"). It needs a slot for the number of
days and, ideally, where to report back. Both long reference videos end this way instead of "subscribe".

### G. Credibility beat — hardest, and channel-specific

The reference creators cite their own reach. AutoVideo would have to be *told* the channel's credibility
facts (subscribers, years, credentials) once per channel and then reuse them; they cannot be invented,
and an invented one is worse than none. Store it beside the existing channel branding (name, tagline,
logo) so it localises with everything else.

## 3 · Two constraints the reference videos make explicit

* **Mixed Devanagari + Latin text.** SeeKen's and Riya Upreti's transcripts switch between scripts
  mid-sentence ("3R RESET", "WIIFM", "dopamine" inside Hindi sentences). Any new card type must render
  both scripts in the same line. AutoVideo already does this for Hindi and Odia editions via
  `--subtitles_fontfile`, so a Latin framework name inside a Devanagari card is supported - but the new
  card templates must not assume a single script when measuring width.
* **Short-form is a different shape.** The 07:48 video is the 24 M-view outlier and has *no* chapters:
  anecdote → roadmap → formula → bonus. Chapter machinery should switch off below a runtime threshold
  rather than produce a two-item list.

## 4 · What this does *not* say

Nothing above is implemented in v7.0.124. This is the research record behind the request *"adapt the
best, easily implementable features … mainly for text pop-up cards and the AI video being used"*; the
release ships the two things that were blocking those features from being visible at all - editions that
finish, and a browser that does not cover the screen while you are working.

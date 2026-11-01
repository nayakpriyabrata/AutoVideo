# AutoVideoAI 7.0.99 · the Flow card that was waiting for a click

Your screenshot from 14:50 answered the question. The saved project
`37d8cf57-12b4-4a85-9934-5580e90d3781` holds the agent turn

> I'm going to generate 1 video clip interpolating between your start and end frames using Omni 1.1 Flash
> in 16:9 at 360p for 6 seconds. Would you like me to kick off this 1 video generation, costing 5 credits?
> **[Approve] [Always approve] [Reject]**

That card was never approved. **That is the whole blocker**: a Flow *video* request is confirmed by a
click, not by a wait, so no video exists in the project. Every download-only scan was telling the truth —
"6 gallery assets, 0 fresh candidates, no verified match" — and no amount of Resume could change it.
7.0.98 named the right request but still only offered recovery, so it would have paused the same way.

## The fastest fix, right now (5 credits, no new request)

1. Click **Approve** in that Flow tab — click **Approve**, not *Always approve*, and never *Reject*.
   That spends 5 credits once and generates the exact shot_014 take the job is waiting for.
2. Wait for the clip to appear in the project (about 1–2 minutes at 360p).
3. Pull it in (0 further credits, QC still runs):

   ```
   python3 cli.py v3 recover-flow-video outputs/20261022-143856-7-small-daily-habits-tha-9729 \
       --shot-id shot_014 --wait-seconds 180
   ```

   If the automatic match still cannot prove the identity, open the new thumbnail, copy its
   `/project/37d8cf57-…/edit/<id>` URL and add `--asset-url <url> --asset-reviewed`.

Then Resume the job. **Do not** archive the request or press Resume first: archiving would abandon a card
that is already waiting and a new video request would cost another 5 credits for the same shot.

## What 7.0.99 adds so this is never invisible again

| Piece | Behaviour |
|---|---|
| `engine/flow_pending_approval.py` (new) | read-only evidence per saved request: was it submitted, was an approval ever reserved/clicked, therefore is a card probably pending? Uses the submit ledger and the journal's `approval_reservations` |
| Queue panel | when that evidence says "submitted, never approved", the panel warns that Flow is waiting for an approval click and that Resume can only scan |
| Blocked-Resume message | the video paragraph now starts with the card: approve it once, or use the approve command; the download afterwards is free |
| `tools/flow_resume_preflight.py` | prints `Approval: no approval click is recorded…` plus the exact `Approve once:` command |
| `flow_browser.pending_approval_card()` | read-only probe: is an Approve control really clickable, what cost does the newest turn state, is it a video card. Never clicks |
| `cli.py v3 approve-request` | approves **one** card for that saved request, then downloads. Every guard runs *before* the click |

### The approve command

```
# read-only: is a card there, what does it cost? (never clicks)
python3 cli.py v3 approve-request outputs/20261022-143856-7-small-daily-habits-tha-9729 \
    --shot-id shot_014 --inspect

# approve exactly one card and then download it
python3 cli.py v3 approve-request outputs/20261022-143856-7-small-daily-habits-tha-9729 \
    --shot-id shot_014 --confirm-credits 5 --wait-seconds 180
```

It refuses, before touching anything, when:

- no Approve control is visible in the saved project;
- the card does not state a readable credit cost;
- the newest agent turn is not a video generation request (an image card needs no approval here);
- `--confirm-credits` is missing or differs from the cost on the card;
- the saved project in the request is not the one opened;
- the same card is already reserved (the existing ledger refuses a duplicate click — no double spend);
- an approval is already recorded for that request (it tells you to run the free recovery instead).

It clicks `Approve` once — never `Always approve` — writes an `approval` line to the take ledger, then runs
the normal download-and-QC path, so a recovered take still has to pass QC. `--inspect` opens the project,
reads the card and clicks nothing.

## Tests

`tests/test_v799_approval_pending.py` — 23 fakes-only tests:

- evidence: submitted-without-approval flagged; a recorded click clears it; a journal reservation counts;
  an image request never needs a card; a downloaded request is not pending; a phase alone is enough when the
  ledger is missing; the command uses the recorded cost when known;
- the guard: no visible card, unreadable cost, image card, wrong cost, missing cost, exact cost;
- the panel/preflight text: the card is named, the approve command is offered, a recorded approval is reported;
- the provider with a fake browser: clicks once with `approval='once'` and `max_credits=<cost>`, never
  `always`; never clicks when the cost differs or no card is visible; reports a refused click; refuses a
  journal that belongs to another project;
- the CLI exposes `approve-request` with an optional `--confirm-credits`.

Neighbour suites (`flow`, `resume`, `approval`, `wait` selections): **445 passed, 9 failed** — the same 9
environmental failures as the untouched 7.0.98 tree in this sandbox (no ffmpeg/ffprobe, Streamlit AppTest).

## Install

1. Stop the dashboard (all tabs).
2. Extract `AutoVideoAI-v7.0.99-Flow-Approval-Card.zip` beside your installation.
3. From inside the installation folder:

   ```
   python3 ../AutoVideoAI-v7.0.99/tools/update_v798_to_v799.py .            # dry run
   python3 ../AutoVideoAI-v7.0.99/tools/update_v798_to_v799.py . --apply    # installs the code
   ```

   It accepts an installed 7.0.98 (or an already-updated 7.0.99), backs replaced files up under
   `code-update-backups/v7.0.98-to-v7.0.99-<timestamp>`, and never touches outputs, jobs, Flow journals,
   browser profiles or Clip Studio folders.

You do not have to install 7.0.99 before clicking Approve — the click and the recovery above work on
7.0.98. Install it so the next card of this kind is named instead of silently pausing.

## Not verified live

No Flow project was opened and no credit was spent while building this release: the click path is exercised
against a fake browser, and the guards are pure functions. The card in your screenshot is the first real
approval, so watch that one run.

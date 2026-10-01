# AutoVideoAI v3.7 - Economy + Credit Guard

## Why v3.6 stopped at the confirmation
The expanded Flow Agent currently presents buttons labelled **Approve**, **Always approve**, and **Reject**. v3.6 did not include `Approve` in its exact confirmation selector list, so it could submit the request but could not authorize it.

v3.7 adds:
- exact `Approve` support
- optional `Always approve` support only when explicitly requested
- a per-generation credit guard
- an Economy preset for direct Flow prompts
- September 2026 Flow credit tables in `config/flow_models.yaml`

## Safest economy test

```bash
python3 cli.py v3 flow-direct \
  "A cinematic drone shot flying over a futuristic Indian city at sunrise" \
  --aspect 9:16 \
  --economy \
  --approval once \
  --max-generation-credits 10 \
  --browser bundled
```

Economy defaults:
- Gemini Omni Flash 360p
- 10 seconds when `--duration` is omitted
- one output
- one-shot approval
- refuses to approve a confirmation showing more than 10 credits

If Flow unexpectedly proposes a premium 100-credit generation, AutoVideoAI leaves the request at the confirmation screen and prints the reason instead of clicking Approve.

## Approval modes

`--approval once` (default): click `Approve` only for this request.

`--approval always`: click `Always approve`. This changes Flow behaviour persistently; use only after your budget guard and model routing are proven.

`--approval manual`: never click a confirmation button.

## Credit-aware long-video design

The economical production pattern is **reference-first hybrid video**, not "AI video for every second":

1. Write narration and split it into voice-timed scenes.
2. Generate a master character reference + style/location references with the no-charge Flow image model.
3. For each scene, generate an opening still and closing still.
4. Reuse scene N's closing still as scene N+1's opening frame when the story is continuous.
5. Use Gemini Omni Flash 360p for only motion-critical scenes, preferably 10 seconds where appropriate.
6. Upscale accepted clips after generation when the account supports no-cost upscaling.
7. For explanatory scenes, animate stills locally with `kenburns_plus` instead of spending Flow video credits.
8. Render all accepted clips/stills against the narration timeline, then add captions, music and SFX.

Recommended routing:
- Hook / major reveal / action / transition: Flow video
- Explanation / list / quote / static environment: free image + local motion
- Character consistency: master reference image carried across every prompt
- Continuous scene: previous closing image -> next opening image
- New location/time: keep character reference but generate a new opening image

## Current direct command defaults

Normal `flow-direct` no longer asks the Agent for "the best available Veo" by default because that may select the 100-credit Quality model. If `--model` is omitted, v3.7 uses Veo 3.1 Lite. `--economy` explicitly requests Gemini Omni Flash 360p.

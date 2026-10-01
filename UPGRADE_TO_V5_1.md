# Upgrade to v5.1 (clean install recommended)

Because earlier v5.0.x hotfixes may have been applied/reversed interactively, do not
patch that source tree again. Extract v5.1 into a new sibling directory.

## 1. Extract beside the old folder

Example Windows/WSL location:

`/mnt/c/Users/<user>/Downloads/Auto/AutoVideoAI-v5.1`

## 2. Copy only your API configuration

If your old folder contains `.env`:

```bash
cp ../AutoVideoAI-v5.0/.env ./.env
```

Do not copy old `engine/`, `tests/`, or patch files into v5.1.

## 3. Verify

```bash
cat VERSION
python3 -m compileall -q cli.py engine
python3 cli.py v3 doctor
```

Expected version: `5.1.0`.

## 4. Flow cache/reuse

v5.1 continues to use the shared Flow-project cache under the user's AutoVideoAI data
location, so compatible project media can be reused without copying an old source tree.
Pass `--flow-project-url` when you intentionally want a new AutoVideoAI job to use a
specific existing Google Flow project.

## 5. Storage safety

v5.1 warns below 5 GB free and stops media generation below 1.5 GB free by default.
You can override these with `AUTOVIDEO_WARN_FREE_GB` and `AUTOVIDEO_MIN_FREE_GB`.

Kokoro is not attempted by `--tts-provider auto` unless
`AUTOVIDEO_ENABLE_LOCAL_TTS=1`. This avoids accidental multi-GB Torch/CUDA downloads.

## Recommended v5.1 test command

```bash
python3 cli.py v3 create \
  --topic "5 habits for successful life" \
  --type faceless_youtube \
  --duration 60 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 10 \
  --video-share 0.20 \
  --stock-share 0 \
  --max-flow-scenes 1 \
  --shot-max-seconds 8 \
  --frame-source flow \
  --flow-approval once \
  --max-generation-credits 10 \
  --flow-frame-retries 3 \
  --flow-video-retries 1 \
  --network-wait-seconds 300 \
  --flow-capacity-wait-seconds 900 \
  --flow-capacity-retries 8 \
  --flow-reuse-mode topic \
  --script-provider auto \
  --script-quality high \
  --tts-provider auto \
  --caption-provider auto \
  --caption-local-model small \
  --max-tts-speedup 1.08
```

# AutoVideoAI v4.0 Quick Start

## 1. Install/update dependencies

```bash
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

## 2. Confirm the Flow browser session

```bash
python3 cli.py v3 flow-open --browser bundled
```

Your existing v3.x persistent Flow login is reused from `~/.local/share/autovideoai/flow-profile`.

## 3. Plan a 60-second Reel without spending credits

```bash
python3 cli.py v3 create \
  --topic "5 AI skills that will matter in 2027" \
  --type shorts \
  --duration 60 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 25 \
  --video-share 0.20 \
  --stock-share 0.15 \
  --frame-source auto \
  --flow-approval once \
  --max-generation-credits 10 \
  --dry-run
```

Review `outputs/<job>/economy_plan.md`. Then rerun without `--dry-run` when the plan looks right.

## 4. Long-form starting point

```bash
python3 cli.py v3 create \
  --topic "How AI agents will change work" \
  --type faceless_youtube \
  --duration 300 \
  --profile STORYBOARD_ECONOMY \
  --max-credits 50 \
  --video-share 0.18 \
  --stock-share 0.20 \
  --max-flow-scenes 6 \
  --frame-source auto \
  --flow-approval once \
  --max-generation-credits 10 \
  --dry-run
```

## 5. Stock clips without an API

Put licensed clips in `assets/stock_library/` and give them descriptive names, for example:

```text
city_traffic_night.mp4
office_team_laptop.mp4
mountain_drone_sunrise.mp4
student_classroom.mp4
```

The economy planner will use matching clips for appropriate B-roll scenes. Pexels/Pixabay API keys remain optional.

## Streamlit UI

```bash
streamlit run app.py
```

Choose `STORYBOARD_ECONOMY`. The Create page exposes AI-video share, stock share, maximum Flow scenes, frame source, approval policy and per-generation credit cap.

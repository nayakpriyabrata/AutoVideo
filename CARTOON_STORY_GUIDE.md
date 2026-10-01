# Cartoon Story workflow (v5.2)

This preset adapts the uploaded MovieFlow creator-guide principles into AutoVideoAI's existing script -> story bible -> storyboard -> Flow/video -> narration -> captions pipeline.

Use `--content-type kids_story --preset cartoon_story` for family-friendly cartoon storytelling. The story bible already locks a canonical protagonist and location, and the cartoon preset reinforces consistent character design, visual style, mood and setting across shots.

Example:

```bash
python3 cli.py v3 create \
  --topic "The little inventor who learned to never give up" \
  --type faceless_youtube \
  --content-type kids_story \
  --tone warm \
  --preset cartoon_story \
  --duration 120 \
  --profile STORYBOARD_ECONOMY \
  --flow-scenes 3 \
  --max-flow-scenes 3 \
  --max-credits 25 \
  --frame-source flow \
  --script-provider groq \
  --tts-provider auto \
  --caption-provider groq
```

`--flow-scenes` is an explicit requested count. `--max-flow-scenes` is only a cap. Credit budget safety always wins.

The uploaded MovieFlow PDF is a high-level creator guide rather than API documentation. v5.2 therefore does not automate MovieFlow itself; it applies the guide's story/character/style/setting/mood/outcome method to AutoVideoAI. A separate MovieFlow browser/API provider can be added later if a stable documented generation interface is available.

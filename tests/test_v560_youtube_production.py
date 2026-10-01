from types import SimpleNamespace
from pathlib import Path


def _shot(i, start=None, text=None):
    from engine.project.manifest import Shot
    st = float(start if start is not None else i * 6)
    return Shot(
        shot_id=f"shot_{i+1:03d}", voice_start=st, voice_end=st+6, duration_target=6,
        narration=text or f"A person works with focus on habit {i%5+1} at a desk and then walks forward.",
        coverage="broll" if i % 3 == 0 else "primary",
        visual_goal="real person working moving walking planning",
        subject="person", subject_action="working and moving", environment="office city laptop",
        motion_intensity="high" if i % 4 == 0 else "medium",
    )


def test_youtube_pro_mix_targets_ten_dynamic_clips():
    from engine.project.manifest import ProductionManifest
    from engine.planning.economy_storyboard import EconomyOptions, assign_storyboard_economy
    m = ProductionManifest(job_id="x", topic="5 habits", target_seconds=300, aspect="16:9", width=1920, height=1080,
                           profile="STORYBOARD_ECONOMY", shots=[_shot(i) for i in range(50)])
    router = SimpleNamespace(model_cost=lambda model, dur: 1.0, budgets={"RETRY_RESERVE_PCT": 0})
    r = assign_storyboard_economy(m, router, EconomyOptions(max_credits=30, flow_scenes=3,
                                                           stock_scenes=7, dynamic_video_scenes=10,
                                                           reserve_pct=0, prefer_stock=True))
    assert r["flow_scenes"] == 3
    assert r["stock_scenes"] == 7
    assert r["image_scenes"] == 40
    dyn_idx = [i for i,s in enumerate(m.shots) if s.media_strategy in {"flow_video", "stock"}]
    assert len(dyn_idx) == 10
    # The cadence algorithm should not collapse all dynamic inserts into one half.
    assert min(dyn_idx) < 10
    assert max(dyn_idx) > 40


def test_longform_default_mix_is_60_stock_20_flow_20_image():
    from engine.project.manifest import ProductionManifest
    from engine.planning.economy_storyboard import EconomyOptions, assign_storyboard_economy
    m = ProductionManifest(job_id="mix", topic="long form", target_seconds=300,
                           aspect="16:9", width=1920, height=1080,
                           profile="STORYBOARD_ECONOMY", shots=[_shot(i) for i in range(50)])
    router = SimpleNamespace(model_cost=lambda model, dur: 1.0,
                             budgets={"RETRY_RESERVE_PCT": 0})
    r = assign_storyboard_economy(
        m, router, EconomyOptions(max_credits=100, video_share=.20,
                                  stock_share=.60, reserve_pct=0, prefer_stock=True))
    assert r["flow_scenes"] == 10
    assert r["stock_scenes"] == 30
    assert r["image_scenes"] == 10


def test_graphics_plan_has_intro_chapters_keypoints_and_outro(tmp_path):
    from engine.project.manifest import ProductionManifest
    from engine.render.graphics import plan_overlays, build_overlay_assets
    texts = [
        "First, protect your first hour and decide your one priority.",
        "Use a notebook and choose the action that matters most.",
        "Second, design your environment so good habits are easy.",
        "Third, protect a deep work block from distraction.",
        "Fourth, review your day and decide tomorrow's priority.",
        "Fifth, schedule recovery and protect your energy.",
    ]
    shots=[]
    for i in range(20):
        txt = texts[i] if i < len(texts) else "Choose one small action you can repeat consistently every day."
        shots.append(_shot(i, start=i*15, text=txt))
    m = ProductionManifest(job_id="x", topic="5 habits winners build for success", target_seconds=300,
                           aspect="16:9", width=1280, height=720, shots=shots)
    ev = plan_overlays(m, {"narration":"x"}, channel_name="Test Channel")
    kinds = [e.kind for e in ev]
    assert "intro" in kinds and "outro" in kinds and "watermark" in kinds
    assert kinds.count("chapter") >= 5
    assets = build_overlay_assets(m, {}, str(tmp_path), channel_name="Test Channel")
    paths = [Path(x["path"]) for x in assets if x.get("path")]
    assert paths and all(p.exists() and p.stat().st_size > 100 for p in paths)


def test_ffmpeg_graph_accepts_editorial_png_overlays(tmp_path):
    from engine.render.ffmpeg_renderer import build_ffmpeg_cmd
    clip = tmp_path / "clip.mp4"; voice = tmp_path / "voice.mp3"; ov = tmp_path / "ov.png"
    clip.write_bytes(b"x"); voice.write_bytes(b"x"); ov.write_bytes(b"x")
    cmd, meta = build_ffmpeg_cmd(
        [{"src": str(clip), "dur": 4.0, "in": 0, "trans_out":"cut"}],
        str(voice), str(tmp_path/"out.mp4"), W=1280, H=720, encoder="libx264",
        overlays=[{"path":str(ov), "start":1.0, "end":3.0}], stereo_master=True,
    )
    fc = meta["filter_complex"]
    assert "overlay=0:0:enable='between(t,1.000,3.000)'" in fc
    assert "channel_layouts=stereo" in fc
    assert meta["overlays"] == 1
    assert "-loop" in cmd

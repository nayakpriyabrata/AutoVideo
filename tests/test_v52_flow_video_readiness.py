import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from engine.providers.flow_browser import FlowBrowserProvider
from engine.planning.economy_storyboard import EconomyOptions, assign_storyboard_economy
from engine.project.manifest import ProductionManifest, Shot
from engine.routing.credit_router import CreditRouter
from engine.render.timeline import _take_duration


def _manifest(n=6):
    shots=[]
    t=0.0
    for i in range(n):
        shots.append(Shot(
            shot_id=f"shot_{i+1:03d}", voice_start=t, voice_end=t+6.0,
            duration_target=6.0,
            narration="Person walks forward and builds a better daily habit",
            coverage="hook" if i == 0 else "primary",
            motion_intensity="high" if i < 3 else "medium",
            subject="person", environment="home office",
        ))
        t += 6.0
    return ProductionManifest(job_id="j", topic="t", target_seconds=int(t),
                              shots=shots, profile="STORYBOARD_ECONOMY")


def test_v52_exact_flow_scene_target_is_distinct_from_cap():
    m=_manifest(6)
    r=CreditRouter("STORYBOARD_ECONOMY")
    rep=assign_storyboard_economy(
        m, r, EconomyOptions(max_credits=25, video_share=.20, flow_scenes=3,
                             max_flow_scenes=3, stock_share=0, reserve_pct=15))
    assert rep["requested_flow_scenes"] == 3
    assert rep["desired_flow_scenes"] == 3
    assert rep["flow_scenes"] == 3
    assert rep["budget_limited"] is False


def test_v52_flow_scene_target_still_obeys_budget():
    m=_manifest(6)
    r=CreditRouter("STORYBOARD_ECONOMY")
    rep=assign_storyboard_economy(
        m, r, EconomyOptions(max_credits=10, video_share=.20, flow_scenes=3,
                             max_flow_scenes=3, stock_share=0, reserve_pct=15))
    assert rep["requested_flow_scenes"] == 3
    assert rep["flow_scenes"] < 3
    assert rep["budget_limited"] is True


def test_v52_jpeg_renamed_mp4_is_not_video(tmp_path):
    p=tmp_path/"poster.mp4"
    # Minimal JPEG-like bytes large enough to bypass size gate.
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"x"*10000 + b"\xff\xd9")
    assert FlowBrowserProvider._is_valid_video_file(str(p)) is False
    assert _take_duration(str(p)) is None


def test_v52_real_mp4_requires_positive_duration(tmp_path):
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    p=tmp_path/"clip.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=10",
                    "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert FlowBrowserProvider._is_valid_video_file(str(p)) is True
    d=_take_duration(str(p))
    assert d is not None and 0.5 <= d <= 2.0

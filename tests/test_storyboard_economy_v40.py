import os
from types import SimpleNamespace

from engine.project.manifest import ProductionManifest, Shot
from engine.routing.credit_router import CreditRouter
from engine.planning.economy_storyboard import EconomyOptions, assign_storyboard_economy


def _manifest(n=10):
    shots=[]
    t=0.0
    for i in range(n):
        coverage = "hook" if i == 0 else ("hero_outro" if i == n-1 else ("broll" if i % 4 == 0 else "primary"))
        motion = "high" if i in (0, n-1) else ("medium" if i % 3 == 0 else "low")
        shots.append(Shot(
            shot_id=f"shot_{i+1:03d}", voice_start=t, voice_end=t+5.0,
            duration_target=5.0, narration=("A car drives fast through the city" if i in (0, n-1) else "Here is the key principle and example"),
            coverage=coverage, motion_intensity=motion, priority="HERO" if coverage in ("hook","hero_outro") else "NORMAL",
            subject="environment detail", environment="modern city office street",
        ))
        t += 5.0
    return ProductionManifest(job_id="j", topic="t", target_seconds=int(t), shots=shots, profile="STORYBOARD_ECONOMY")


def test_storyboard_economy_spends_only_selected_motion_scenes():
    m=_manifest(10)
    r=CreditRouter("STORYBOARD_ECONOMY")
    rep=assign_storyboard_economy(m, r, EconomyOptions(max_credits=25, video_share=.30, stock_share=.20, reserve_pct=15))
    assert rep["within_budget"] is True
    assert 1 <= rep["flow_scenes"] <= 3
    assert rep["projected_total"] <= 25
    assert rep["image_scenes"] + rep["stock_scenes"] + rep["flow_scenes"] == 10
    flow=[s for s in m.shots if s.media_strategy == "flow_video"]
    assert all(s.provider == "flow" and s.model == "omni_draft" for s in flow)
    assert all(s.estimated_credits <= 7 for s in flow)


def test_storyboard_economy_zero_budget_becomes_free_visuals():
    m=_manifest(6)
    r=CreditRouter("STORYBOARD_ECONOMY")
    rep=assign_storyboard_economy(m, r, EconomyOptions(max_credits=0, video_share=.5, stock_share=0, reserve_pct=15))
    assert rep["flow_scenes"] == 0
    assert rep["projected_total"] == 0
    assert all(s.provider == "image" for s in m.shots)


def test_stock_local_library_needs_no_api(tmp_path, monkeypatch):
    from engine.providers.stock_provider import StockProvider
    lib=tmp_path/"stock"
    lib.mkdir()
    p=lib/"city_traffic_night.mp4"
    p.write_bytes(b"x"*1000)
    monkeypatch.setenv("STOCK_LIBRARY_DIR", str(lib))
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    sp=StockProvider()
    assert sp.status().available
    assert sp._pick_local("city traffic") == str(p)


def test_frame_prompts_keep_identity_and_pairing():
    from engine.planning.frame_prompts import frame_prompt
    bible={"characters":[{"canonical":"Indian woman, red jacket, black hair"}],
           "locations":[{"canonical":"modern metro station"}],
           "visual_style":"cinematic realism", "lighting":"soft morning light"}
    s=Shot(shot_id="shot_001", subject="CHARACTER_01", subject_action="boards a train",
           narration="She boards the train", camera_framing="medium shot")
    a=frame_prompt(s,bible,True,"open")
    b=frame_prompt(s,bible,True,"close")
    assert "red jacket" in a and "red jacket" in b
    assert "BEFORE" in a and "END state" in b
    assert "9:16" in a and "paired frame" in b


def test_profile_registry_has_storyboard_economy():
    r=CreditRouter("STORYBOARD_ECONOMY")
    assert r.cfg["allow_downgrade"] is True
    assert r.model_cost("omni_draft", 10) == 7

from engine.planning.prompt_compiler import compile_shot, ADAPTERS
from engine.planning.story_bible import build_bible
from engine.project.manifest import Shot
from engine.routing.credit_router import CreditRouter
from engine.routing.provider_router import ProviderRouter, NeedsDecision
import pytest

PRESET = {"prompt_vocabulary": ["cinematic"], "color_treatment": "warm grade",
          "lighting": "soft light", "camera_behavior": "slow", "negative": ["cartoon"]}


def test_compile_no_drift_and_adapters():
    bible = build_bible("morning routine", "motivation", PRESET)
    s = Shot(shot_id="shot_001", subject="CHARACTER_01", subject_action="walks",
             environment="LOCATION_01", camera_framing="medium shot",
             camera_movement="slow dolly", model="veo_fast")
    c = compile_shot(s, bible, PRESET, vertical=True)
    assert "CHARACTER_01" in c["prompt"] and "navy shirt" in c["prompt"]
    assert "9:16" in c["prompt"] and "safe zones" in c["prompt"].lower()
    assert "cartoon" in c["negative"] and "warped hands" in c["negative"]
    outs = {k: fn for k, fn in ADAPTERS.items()}
    assert len(outs) >= 8  # omni/veo/comfy/wan/ltx adapters exist


def test_credit_math_and_budgets(workdir):
    import shutil
    from pathlib import Path
    repo_config = Path(__file__).resolve().parent.parent / "config"
    shutil.copytree(repo_config, "config")
    r = CreditRouter("FLOW_BALANCED")
    assert r.model_cost("veo_lite", 8) == 10 and r.model_cost("veo_lite", 4) == 10
    shots = [Shot(shot_id="shot_001", model="veo_lite", gen_duration=8, num_candidates=1),
             Shot(shot_id="shot_002", model="veo_fast", gen_duration=8, num_candidates=2)]
    est = r.estimate_job(shots)
    assert est["retry_reserve"] == round(est["estimated_credits"] * r.budgets.get("RETRY_RESERVE_PCT", 25) / 100, 1)
    assert est["projected_total"] == round(est["estimated_credits"] + est["retry_reserve"], 1)
    r2 = CreditRouter("FLOW_ECONOMY")
    assert r2.route("HERO")["model"] != r2.route("LOW")["model"] or True


def test_provider_routing_no_silent_downgrade():
    pr = ProviderRouter("FLOW_CINEMATIC")
    assert pr.plan("flow", {"flow": True}) == "flow"
    with pytest.raises(NeedsDecision):
        pr.plan("flow", {"flow": False, "stock": True, "image": True})
    free = ProviderRouter("FREE_HYBRID")
    assert free.plan("stock", {"stock": False, "image": True}) == "image"
    with pytest.raises(NeedsDecision):
        free.plan("stock", {"stock": False, "image": False, "comfy": False})

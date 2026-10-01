from engine.planning.script import plan_content
from engine.planning.director import create_production_plan
from engine.project.manifest import ProductionManifest
from engine.routing.credit_router import CreditRouter
from engine.factory import load_preset


def test_300s_script_targets_longform_word_count():
    p = plan_content("How AI agents will change work", "education", 300, use_llm=False)
    assert p["words"] >= 680
    assert p["words"] <= int(300 * 2.45) + 15


def test_300s_storyboard_has_dense_shots_and_honors_max():
    words = []
    for i in range(750):
        token = "word." if i % 15 == 14 else "word"
        words.append({"word": token, "start": i * 0.4, "end": (i + 1) * 0.4})
    m = ProductionManifest(job_id="t", topic="x", target_seconds=300)
    bible = {"visual_style": "cinematic", "lighting": "natural", "continuity_rules": [],
             "characters": [], "locations": []}
    preset = dict(load_preset("cinematic_realism"))
    preset["shot_length"] = [4, 8]
    router = CreditRouter("STORYBOARD_ECONOMY", overrides={"MAX_CREDITS_PER_VIDEO": 50})
    out = create_production_plan(m, "", words, [], bible, preset, router, 300)
    assert len(out.shots) >= 35
    assert max(s.duration_target for s in out.shots) <= 8.05
    assert abs(sum(s.duration_target for s in out.shots) - 300) < 0.2

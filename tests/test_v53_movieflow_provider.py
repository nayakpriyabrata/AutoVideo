from types import SimpleNamespace

from engine.factory import Factory
from engine.project.manifest import ProductionManifest
from engine.providers.movieflow_browser import MovieFlowBrowser
from engine.routing.provider_router import ProviderRouter


def test_movieflow_url_normalization():
    assert MovieFlowBrowser.normalize_project_url("https://studio.movieflow.ai/project/abc#x") == "https://studio.movieflow.ai/project/abc"
    assert MovieFlowBrowser.normalize_project_url("https://movieflow.ai/home") == "https://movieflow.ai/home"
    assert MovieFlowBrowser.normalize_project_url("https://example.com/x") == ""


def test_router_accepts_movieflow_scene():
    r = ProviderRouter("STORYBOARD_ECONOMY")
    assert r.plan("movieflow", {"movieflow": True, "image": True, "flow": True}) == "movieflow"


def test_full_story_flag_and_single_movieflow_shot(tmp_path):
    f = Factory(outputs=str(tmp_path / "outputs"), db_path=str(tmp_path / "jobs.db"))
    m = ProductionManifest(job_id="j", topic="The brave little fox", content_type="kids_story",
                           target_seconds=60, aspect="16:9", profile="STORYBOARD_ECONOMY")
    settings = {"cartoon_provider": "movieflow", "movieflow_mode": "full_story"}
    assert f._movieflow_full_story_enabled(m, settings)
    plan = {"narration": "A little fox learns to be brave and helps a friend."}
    bible = {"characters": [{"name": "Fia", "look": "orange fox, blue scarf"}],
             "locations": [{"name": "forest village"}], "visual_style": "2D storybook cartoon"}
    out = f._prepare_movieflow_full_story(m, plan, bible, {}, 58.5)
    assert len(out.shots) == 1
    s = out.shots[0]
    assert s.provider == "movieflow"
    assert s.model == "movieflow_story"
    assert s.media_strategy == "movieflow_full_story"
    assert "SAME main character identity" in s.compiled_prompt
    assert "Fia" in s.compiled_prompt
    assert "forest village" in s.compiled_prompt
    assert "58 seconds" in s.compiled_prompt

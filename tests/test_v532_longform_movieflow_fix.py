import inspect

from engine.factory import Factory


def test_movieflow_full_story_skips_generic_scene_images():
    src = inspect.getsource(Factory.run_job)
    assert "and not movieflow_full" in src
    assert "Strict Flow frame mode: skipping Pollinations storyboard previews" in src


def test_provider_is_resolved_before_movieflow_compiled_payload():
    src = inspect.getsource(Factory._generate_all)
    assign = src.index("current_prov = use_prov")
    payload = src.index('"movieflow_story_prompt": s.compiled_prompt if current_prov == "movieflow" else ""')
    assert assign < payload


def test_longform_single_frame_optimization_is_enabled_for_strict_flow():
    src = inspect.getsource(Factory._generate_economy_frames)
    assert 'float(getattr(m, "target_seconds", 0) or 0) >= 180' in src
    assert 'skipped-longform-single-frame' in src

"""Scene-image workflow tests: scoring, budget math, settings merge, script md (no browser)."""
import json
import os

import cv2
import numpy as np

from engine.qc.video_qc import score_image


def _img(path, kind):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if kind == "textured":
        img = np.random.default_rng(7).integers(40, 220, (320, 180, 3), np.uint8)
    elif kind == "flat":
        img = np.full((320, 180, 3), 128, np.uint8)
    cv2.imwrite(path, img)
    return path


def test_score_image_ordering(tmp_path):
    good = _img(str(tmp_path / "a.jpg"), "textured")
    flat = _img(str(tmp_path / "b.jpg"), "flat")
    g, f = score_image(good), score_image(flat)
    assert 0 <= g["overall"] <= 100 and 0 <= f["overall"] <= 100
    assert g["overall"] > f["overall"]  # texture/exposure beats flat gray
    assert g["sharpness"] > f["sharpness"]


def test_score_image_missing_is_zero():
    r = score_image("/nonexistent/x.jpg")
    assert r["overall"] == 0 and r["ok"] is False


def test_imagen_flow_config_has_image_cost():
    import yaml
    reg = yaml.safe_load(open("config/flow_models.yaml", encoding="utf-8"))
    assert "imagen_flow" in reg["models"]
    assert reg["models"]["imagen_flow"]["kind"] == "image"
    assert "credits_per_image" in reg["models"]["imagen_flow"]


def test_image_tab_selectors_present():
    import yaml
    ui = yaml.safe_load(open("config/flow_ui.yaml", encoding="utf-8"))
    assert "image_tab" in ui["actions"]
    assert "image_generating_indicator" in ui["actions"]


def test_settings_merge_images_per_shot(workdir):
    from engine.factory import Factory
    f = Factory()
    job = f.create_job("t", "shorts", 20, "9:16", profile="FLOW_ECONOMY", images_per_shot=3)
    assert f._settings(job)["images_per_shot"] == 3
    job2 = f.create_job("t", "shorts", 20, "9:16", profile="FLOW_ECONOMY")
    assert f._settings(job2)["images_per_shot"] == 2  # default


def test_budget_includes_image_line():
    from engine.routing.credit_router import CreditRouter
    from engine.project.manifest import Shot
    r = CreditRouter(profile="FLOW_ECONOMY")
    shots = [Shot(shot_id="shot_001", model="veo_lite", provider="flow", gen_duration=8)]
    est = r.estimate_job(shots)
    import yaml
    unit = float(yaml.safe_load(open("config/flow_models.yaml", encoding="utf-8"))
                 ["models"]["imagen_flow"]["credits_per_image"])
    img = unit * 2 * len(shots)
    est["image_credits"] = round(img, 1)
    est["projected_total"] = round(est["projected_total"] + est["image_credits"], 1)
    assert "projected_total" in est and est["image_credits"] == round(img, 1)


def test_script_md_writer(workdir):
    from engine.factory import Factory
    from engine.project.manifest import ProductionManifest
    m = ProductionManifest(job_id="job9", topic="Test topic")
    plan = {"angle": "a", "audience": "b", "hook": "H",
            "beats": [{"name": "Intro", "text": "hello world"}],
            "narration": "hello world", "words": 2, "cta": "subscribe", "source": "planner"}
    p = os.path.join(str(workdir), "script.md")
    Factory._write_script_md(m, plan, p)
    txt = open(p, encoding="utf-8").read()
    assert "# Test topic" in txt and "## 🎙️ Narration" in txt and "hello world" in txt


def test_manual_approval_checks_each_shot():
    from engine.project.manifest import Shot
    shots = [Shot(shot_id="shot_001", status="approved"), Shot(shot_id="shot_002", status="planned")]
    assert any(s.status == "planned" for s in shots)
    shots[1].status = "approved"
    assert not any(s.status == "planned" for s in shots)


def test_flow_profiles_defined():
    """Regression: run_job references FLOW_PROFILES - must exist (NameError = every real run crashes)."""
    from engine import factory
    assert set(factory.FLOW_PROFILES) == {"FLOW_CINEMATIC", "FLOW_BALANCED",
                                          "FLOW_ECONOMY", "STORYBOARD_ECONOMY",
                                          "MANUAL_DIRECTOR"}


def test_generate_image_signatures():
    import inspect
    from engine.providers.flow_browser import FlowBrowserProvider
    from engine.providers.image_provider import ImageProvider
    assert "dry_run" in inspect.signature(FlowBrowserProvider.generate_image).parameters
    assert "dry_run" in inspect.signature(ImageProvider.generate_image).parameters


def _stub_providers(monkeypatch, factory, flow_impl, free_impl):
    class StubFlow:
        def generate_image(self, shot, comp, out, vertical, dry_run=False):
            return flow_impl(out)

        def close(self):
            pass

    class StubFree:
        def generate_image(self, shot, comp, out, vertical, dry_run=False):
            return free_impl(out)

    monkeypatch.setattr(factory, "_providers",
                        lambda: {"flow": StubFlow(), "image": StubFree()})


def _job_with_shot(factory):
    from engine.project.manifest import Shot
    job = factory.create_job("t", "shorts", 20, "9:16", profile="FLOW_ECONOMY",
                             images_per_shot=2)
    m = factory.pm.load_manifest(job)
    m.shots = [Shot(shot_id="shot_001", status="planned", compiled_prompt="a cat",
                    narration="hello there friend")]
    factory.pm.save_manifest(m)
    return job


def test_scene_images_flow_path_best_first(workdir, monkeypatch):
    import types
    from engine.factory import Factory
    f = Factory()
    job = _job_with_shot(f)

    def flow_impl(out):
        _img(out, "textured")
        return {"path": out, "provider": "flow", "model": "imagen_flow"}

    def free_impl(out):
        raise AssertionError("free fallback should not run when Flow succeeds")

    _stub_providers(monkeypatch, f, flow_impl, free_impl)
    refs = types.SimpleNamespace(add=lambda *a: None)
    m = f.pm.load_manifest(job)
    f._generate_scene_images(m, f.pm.dirs(job), refs, True, 2, lambda *a: None)

    m2 = f.pm.load_manifest(job)
    s = m2.shots[0]
    assert len(s.reference_assets) == 2
    assert all(os.path.exists(p) for p in s.reference_assets)
    frame = os.path.join(f.pm.dirs(job)["storyboard"], "shot_001.jpg")
    assert os.path.exists(frame)  # best still overwrote storyboard frame


def test_scene_images_free_fallback_on_flow_failure(workdir, monkeypatch):
    import types
    from engine.factory import Factory
    f = Factory()
    job = _job_with_shot(f)

    def flow_impl(out):
        raise RuntimeError("Flow UI changed")

    def free_impl(out):
        _img(out, "flat")
        return {"path": out, "provider": "image", "model": "free"}

    _stub_providers(monkeypatch, f, flow_impl, free_impl)
    refs = types.SimpleNamespace(add=lambda *a: None)
    m = f.pm.load_manifest(job)
    f._generate_scene_images(m, f.pm.dirs(job), refs, True, 2, lambda *a: None)

    m2 = f.pm.load_manifest(job)
    assert len(m2.shots[0].reference_assets) == 2  # fallback still delivered

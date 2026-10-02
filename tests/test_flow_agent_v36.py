import re
from pathlib import Path

from engine.providers.flow_browser import FlowBrowser


def _ui():
    return str(Path(__file__).resolve().parent.parent / "config" / "flow_ui.yaml")


class _Loc:
    def __init__(self, visible=True):
        self.visible = visible
        self.clicked = 0
        self.filled = None
    def click(self):
        self.clicked += 1
    def fill(self, t):
        self.filled = t
    def is_visible(self, timeout=0):
        return self.visible
    def get_attribute(self, name):
        return "false"


def test_agent_instruction_forces_video_and_portrait():
    s = FlowBrowser._agent_video_instruction("city at sunrise", "9:16", "Veo 3.1 - Fast", 8, 1)
    assert "VIDEO" in s
    assert "Do not create a still image" in s
    assert "portrait" in s and "9:16" in s
    assert "Veo 3.1 - Fast" in s
    assert "8 seconds" in s
    assert "city at sunrise" in s


def test_detect_editor_mode_prefers_standard_over_agent():
    b = FlowBrowser.__new__(FlowBrowser)
    def fake_try(action, timeout_ms=1500):
        if action in {"migrated_settings_trigger", "agent_prompt_box"}:
            return _Loc()
        return None
    b._try_resolve = fake_try
    assert b.detect_editor_mode() == "standard"


def test_prepare_agent_selects_video_type_without_touching_legacy_controls():
    b = FlowBrowser.__new__(FlowBrowser)
    b.detect_editor_mode = lambda: "agent"
    b.configure_migrated_text_video = lambda *a, **k: (_ for _ in ()).throw(AssertionError("standard should not run"))
    b.select_video_mode = lambda *a, **k: (_ for _ in ()).throw(AssertionError("legacy should not run"))
    selected = []
    b.select_agent_generation_type = lambda kind: selected.append(kind)
    assert b.prepare_text_video("9:16", "Veo 3.1 - Fast", 8, 1) == "agent"
    assert selected == ["video"]


def test_prepare_standard_uses_migrated_configurator():
    b = FlowBrowser.__new__(FlowBrowser)
    b.detect_editor_mode = lambda: "standard"
    seen = {}
    b.configure_migrated_text_video = lambda aspect, model, duration, count: seen.update(
        aspect=aspect, model=model, duration=duration, count=count
    )
    assert b.prepare_text_video("16:9", "Veo 3.1 - Lite", 6, 2) == "standard"
    assert seen == {"aspect": "16:9", "model": "Veo 3.1 - Lite", "duration": 6, "count": 2}


def test_config_contains_migrated_and_agent_selectors():
    import yaml
    ui = yaml.safe_load(open(_ui(), encoding="utf-8"))
    actions = ui["actions"]
    assert actions["migrated_settings_trigger"][0]["selector"] == ".settings-trigger-button"
    assert "arrow_forward" in actions["migrated_submit_button"][0]["selector"]
    assert actions["agent_prompt_box"]
    assert "Approve" in actions["agent_confirmation_buttons"]
    assert "Generate" not in actions["agent_confirmation_buttons"]

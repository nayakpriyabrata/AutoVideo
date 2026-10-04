"""Real Streamlit forms, with a temporary local Factory and no providers."""
from pathlib import Path

from streamlit.testing.v1 import AppTest
from engine.factory import Factory


PAGE_GROUPS = {
    "STUDIO": "Create", "MINI REELS": "Create", "CREATE": "Create",
    "STORYBOARD": "Review & Render", "DIRECTOR REVIEW": "Review & Render",
    "PRODUCTION QC": "Review & Render", "ASSETS": "Review & Render", "RENDER": "Review & Render",
    "QUEUE": "Jobs & Recovery", "HISTORY": "Jobs & Recovery", "FLOW SESSION": "Jobs & Recovery",
    "CLIP STUDIO": "Content & Delivery", "CONTENT INBOX": "Content & Delivery",
    "CHARACTER LIBRARY": "Content & Delivery", "AI RECREATE": "Content & Delivery",
    "PUBLISHING DESK": "Content & Delivery", "SETTINGS": "Setup & Legacy", "Quick (v2)": "Setup & Legacy",
}


def navigate(app, page):
    group = PAGE_GROUPS[page]
    next(w for w in app.sidebar.selectbox if w.label == "Workspace").set_value(group).run()
    next(r for r in app.sidebar.radio if r.label == "Page").set_value(page).run()
    assert not app.exception, [e.message for e in app.exception]


def dashboard(tmp_path, monkeypatch):
    import engine.factory as module
    f = Factory(str(tmp_path/'outputs'), str(tmp_path/'db.sqlite'))
    monkeypatch.setattr(module, 'Factory', lambda *args, **kwargs: f)
    import engine.project.database as database
    monkeypatch.setattr(database, 'JobDB', lambda *args, **kwargs: f.db)
    return f, AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=30).run()


def test_dashboard_uses_streamlit_width_argument_instead_of_deprecated_flag():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "use_container_width=" not in source


def test_sidebar_navigation_groups_pages_into_workspaces(tmp_path, monkeypatch):
    _, app = dashboard(tmp_path, monkeypatch)
    workspace = next(w for w in app.sidebar.selectbox if w.label == "Workspace")
    assert workspace.value == "Create"
    page = next(r for r in app.sidebar.radio if r.label == "Page")
    assert len(page.options) == 3

    navigate(app, "RENDER")
    workspace = next(w for w in app.sidebar.selectbox if w.label == "Workspace")
    assert workspace.value == "Review & Render"
    page = next(r for r in app.sidebar.radio if r.label == "Page")
    assert set(page.options) == {"Storyboard", "Director Review", "Production QC", "Assets", "Render & B-roll"}


def test_studio_music_only_plan_persists_independent_switches(tmp_path, monkeypatch):
    f, app = dashboard(tmp_path, monkeypatch)
    next(r for r in app.radio if r.label == 'Audio mode').set_value('Music only').run()
    assert not app.exception
    assert next(x for x in app.selectbox if x.label == 'TTS').disabled
    assert next(x for x in app.selectbox if x.label == 'Speech captions').disabled
    next(x for x in app.text_input if x.label == 'Topic / idea').set_value('A rabbit shares a carrot')
    next(x for x in app.selectbox if x.label == 'Theme').set_value('kids_cartoon')
    next(x for x in app.checkbox if x.label == 'Include text cards').uncheck()
    next(x for x in app.checkbox if x.label == 'Create plan only (run later with Resume)').check()
    next(x for x in app.button if x.label == '🚀 Create production').click().run()
    assert not app.exception
    job = app.session_state['job_id']
    saved = f._settings(job)
    assert saved['voiceover_enabled'] is False and saved['text_cards_enabled'] is False
    assert saved['caption_display'] == 'none'
    assert saved['sound_effects_enabled'] is False and saved['ambience_enabled'] is False
    assert saved['background_music'] == 'auto'
    assert not list(Path(f.pm.job_dir(job)).rglob('*.flow-request.json'))


def test_silent_mode_disables_music_control(tmp_path, monkeypatch):
    _, app = dashboard(tmp_path, monkeypatch)
    next(r for r in app.radio if r.label == 'Audio mode').set_value('Silent').run()
    assert not app.exception
    assert next(x for x in app.selectbox if x.label == 'Background music').disabled


def test_existing_job_editor_does_not_run_or_mutate_visuals(tmp_path, monkeypatch):
    f = Factory(str(tmp_path/'outputs'), str(tmp_path/'db.sqlite'))
    job = f.create_job('Keep this saved job', voiceover_enabled=True, text_cards_enabled=True)
    import engine.factory as module
    monkeypatch.setattr(module, 'Factory', lambda *args, **kwargs: f)
    import engine.project.database as database
    monkeypatch.setattr(database, 'JobDB', lambda *args, **kwargs: f.db)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=30).run()
    next(x for x in app.selectbox if x.label == 'Active job').set_value(job).run()
    navigate(app, 'QUEUE')
    assert not app.exception
    next(r for r in app.radio if r.label == 'Output audio mode').set_value('Music only').run()
    next(x for x in app.checkbox if x.label == 'Include text cards').uncheck()
    next(x for x in app.button if x.label == 'Save audio & text choices').click().run()
    assert not app.exception
    saved = f._settings(job)
    assert not saved['voiceover_enabled'] and not saved['text_cards_enabled']
    assert saved['sound_effects_enabled'] is False and saved['ambience_enabled'] is False
    assert saved['music_volume'] == .55
    assert f.pm.load_manifest(job).status == 'created'

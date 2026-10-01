import json
from types import SimpleNamespace as NS
import pytest
from engine.factory import Factory
from engine.providers.gemini_web import GeminiWebBrowser
from engine.studio_config import DEFAULTS


def test_resume_policy_update_preserves_other_settings(tmp_path):
    path = tmp_path/'settings.json'
    path.write_text(json.dumps({'gemini_chat_cleanup':'keep','flow_project_url':'saved-project'}))
    f = object.__new__(Factory)
    f.pm = NS(load_manifest=lambda job: {}, job_dir=lambda job:str(tmp_path))
    f.set_gemini_cleanup('job', 'delete-after-read')
    data = json.loads(path.read_text())
    assert data['gemini_chat_cleanup']=='delete-after-read'
    assert f._settings('job')['gemini_chat_cleanup']=='delete-after-read'
    assert data['flow_project_url']=='saved-project'
    with pytest.raises(ValueError): f.set_gemini_cleanup('job','delete-all')


def test_visible_composer_after_hidden_editor(monkeypatch):
    hidden = NS(is_visible=lambda **kw:False)
    visible = NS(is_visible=lambda **kw:True, is_editable=lambda **kw:True)
    b=object.__new__(GeminiWebBrowser)
    b._page=NS(locator=lambda selector:NS(count=lambda:2,nth=lambda i:[hidden,visible][i]))
    monkeypatch.setattr(b,'_resolve',lambda *a,**k:pytest.fail('should find visible composer'))
    assert b._prompt_box() is visible


def test_new_studio_jobs_enable_cleanup():
    assert DEFAULTS['gemini_chat_cleanup']=='delete-after-read'


def test_cleanup_policy_explicit_keep_still_supported(monkeypatch):
    b=object.__new__(GeminiWebBrowser)
    monkeypatch.setenv('AUTOVIDEO_GEMINI_CHAT_CLEANUP','keep')
    assert not b._cleanup_requested()
    monkeypatch.setenv('AUTOVIDEO_GEMINI_CHAT_CLEANUP','delete-after-read')
    assert b._cleanup_requested()


def test_global_cleanup_defaults_and_job_precedence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'config').mkdir()
    (tmp_path/'config/user_settings.yaml').write_text('gemini_chat_cleanup: delete-after-read\nflow_image_workers: 3\n')
    f = object.__new__(Factory)
    f.pm = NS(job_dir=lambda job:str(tmp_path))
    assert f._settings('job')['gemini_chat_cleanup'] == 'delete-after-read'
    assert f._settings('job')['flow_image_workers'] == 3
    (tmp_path/'settings.json').write_text(json.dumps({'gemini_chat_cleanup':'keep','flow_image_workers':1}))
    assert f._settings('job')['gemini_chat_cleanup'] == 'keep'
    assert f._settings('job')['flow_image_workers'] == 1

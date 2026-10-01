import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from playwright._impl._impl_to_api_mapping import ImplToApiMapping
from engine.providers.flow_browser import FlowBrowser
from engine.planning import script_engine as se
from engine.factory import Factory


@pytest.mark.parametrize('click_fails', [False, True])
def test_download_callback_uses_real_playwright_mapping(tmp_path, click_fails):
    mapping = ImplToApiMapping()
    events = {}
    def on(event, callback):
        events[event] = mapping.wrap_handler(callback)
    def remove(event, callback):
        assert events.pop(event) is mapping.wrap_handler(callback)
    download = NS(save_as=lambda path: Path(path).write_bytes(b'asset'))
    def click(**kw):
        if click_fails:
            raise RuntimeError('click failed')
        events['download'](download)
    browser = object.__new__(FlowBrowser)
    browser._page = NS(on=on, remove_listener=remove, wait_for_timeout=lambda ms: None)
    output = str(tmp_path/'asset.jpg')
    if click_fails:
        with pytest.raises(RuntimeError, match='click failed'):
            browser._download_from_tile_button(NS(click=click), output)
    else:
        assert browser._download_from_tile_button(NS(click=click), output) == output
        assert Path(output).read_bytes() == b'asset'
    assert not events


@pytest.mark.parametrize('result', ['unchanged', 'unavailable'])
def test_length_repair_keeps_draft_and_stops_without_progress(monkeypatch, result):
    plan = {'narration': ' '.join(['word']*220), 'cta': 'Continue'}
    calls = []
    def call(*args):
        calls.append(args)
        if result == 'unavailable':
            raise RuntimeError('composer unavailable')
        return json.dumps(plan)
    monkeypatch.setattr(se, '_call_provider', call)
    monkeypatch.setattr(se, '_normalize_plan', lambda obj,*args: obj)
    repaired = se._repair_length_same_provider(plan,'gemini-web','auto','topic','education',180,'calm','en',300)
    assert repaired['narration'] == plan['narration']
    assert len(calls) == 1


def test_new_pause_actions_do_not_require_manual_download(tmp_path):
    factory = object.__new__(Factory)
    factory.pm = NS(load_manifest=lambda job:NS(accepted_count=lambda:0,shots=[]),
                    job_dir=lambda job:str(tmp_path), log=lambda *a:None)
    state = factory._write_pause_state('job','shot_001','pending image',project_url='https://flow.google.com/project/test')
    assert [a['command'] for a in state['actions']] == ['python3 cli.py v3 resume job']

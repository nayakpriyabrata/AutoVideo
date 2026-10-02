from types import SimpleNamespace as NS
from pathlib import Path
import hashlib
import json
import time
import pytest
from engine.providers.flow_browser import FlowBrowser, FlowBrowserProvider, FlowRequestPending


def test_animated_download_control():
    calls = []
    def click(**kw):
        calls.append(kw)
        if not kw.get('force'):
            raise RuntimeError('element is not stable')
    FlowBrowser._click_download_control(NS(click=click, is_visible=lambda: True, is_enabled=lambda: True))
    assert calls == [{'timeout': 3000}, {'timeout': 3000, 'force': True}]


def test_unrelated_click_error_not_forced():
    def click(**kw):
        assert not kw.get('force')
        raise RuntimeError('closed')
    with pytest.raises(RuntimeError):
        FlowBrowser._click_download_control(NS(click=click))


def test_download_retry_without_submission(tmp_path):
    p = object.__new__(FlowBrowserProvider)
    out = str(tmp_path/'image.jpg')
    p._save_request(out, {'project_url':'https://flow.google.com/project/test'})
    calls = []
    def once(*args):
        calls.append(1)
        if len(calls) < 3:
            raise FlowRequestPending('download failed')
        return {'path':out}
    p._guarded_generation_once = once
    p.recover_browser = lambda *a, **k: True
    assert p.generate_image(NS(), {}, out, False)['path'] == out
    assert len(calls) == 3


@pytest.mark.parametrize('visible,recent,expected', [(True,False,0),(False,True,0),(False,False,1)])
def test_replacement_is_bounded_and_only_missing(tmp_path, visible, recent, expected):
    p = object.__new__(FlowBrowserProvider)
    out = str(tmp_path/'image.jpg')
    shot = NS(shot_id='s1')
    compiled = {'prompt':'a tree'}
    url = 'https://flow.google.com/project/test'
    key = hashlib.sha256(json.dumps(['image','s1','a tree',False],sort_keys=True).encode()).hexdigest()
    p._save_request(out, dict(kind='image', request_hash=key, signature='target', baseline=['old'],
                              project_url=url, submitted_at=time.time()-(0 if recent else 500)))
    calls = []
    def once(*args):
        if not Path(out+'.flow-request.json').exists():
            calls.append('regenerate')
            p._save_request(out, {'project_url':url})
        raise FlowRequestPending('failed')
    p._guarded_generation_once = once
    p.recover_browser = lambda *a, **k: True
    p._ensure = lambda: NS(ensure_project=lambda *a,**k: None, current_project_url=lambda:url,
        media_assets=lambda: [{'sig':'old'}]+([{'sig':'target'}] if visible else []),
        _page=NS(wait_for_timeout=lambda ms:None, locator=lambda s:NS(inner_text=lambda **k:'ready')))
    for _ in range(2):
        with pytest.raises(FlowRequestPending):
            p.generate_image(shot, compiled, out, False)
    assert len(calls) == expected


def test_crash_reservation_blocks_new_submission(tmp_path):
    p = object.__new__(FlowBrowserProvider)
    out = str(tmp_path/'image.jpg')
    Path(out+'.flow-request.before-regeneration.json').write_text('{}')
    with pytest.raises(FlowRequestPending, match='reserved'):
        p.generate_image(NS(), {}, out, False)

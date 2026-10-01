import ast
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from engine.providers.flow_browser import media_signature_matches


def sig(url='https://media.example/asset.jpg', width=500, alt='prompt', kind='image'):
    return f'IMG|{url}|{alt}|{kind}|{width}|280'


def test_resize_and_label_change_preserve_asset_identity():
    assert media_signature_matches(sig(), sig(width=700, alt='new accessibility label'))


def test_different_assets_and_media_types_do_not_match():
    assert not media_signature_matches(sig(), sig('https://media.example/other.jpg'))
    assert not media_signature_matches(sig(), sig(kind='video'))
    assert not media_signature_matches('broken', sig())


def test_signed_url_change_requires_independent_asset_id():
    assert media_signature_matches(sig('https://media.example/get?id=abc&Expires=1&Signature=old'),
                                   sig('https://media.example/get?id=abc&Expires=2&Signature=new'))
    assert not media_signature_matches(sig('https://media.example/get?token=one'),
                                       sig('https://media.example/get?token=two'))
    assert not media_signature_matches(sig('https://media.example/get?id=abc&Signature=old'),
                                       sig('https://media.example/get?id=other&Signature=new'))


def pause_function(st):
    tree = ast.parse(Path('app.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'pause_panel')
    ctx = {'st':st, '_pause_panels':set(), 'json':json, 'build_support_report':lambda root:{},
           'F':NS(pause_state=lambda j:{'shot_id':'shot_001','kind':'flow_download_or_ui'},
                  pm=NS(job_dir=lambda job:'outputs/'+job))}
    exec(compile(ast.Module(body=[fn],type_ignores=[]), 'app.py', 'exec'), ctx)
    return ctx['pause_panel']


def test_same_job_pause_panel_is_not_rendered_twice():
    buttons=[]
    downloads=[]
    st=NS(info=lambda *a:None, warning=lambda *a:None, write=lambda *a:None,
          caption=lambda *a:None, button=lambda *a, **k:buttons.append(k['key']) or False,
          expander=lambda *a, **k:nullcontext(), code=lambda *a, **k:None,
          download_button=lambda *a, **k:downloads.append(k['key']) or False)
    fn=pause_function(st); fn('job'); fn('job')
    assert buttons == ['resume-paused-job']
    assert downloads == ['support-report-job']


def test_resume_is_queued_not_recursive():
    class Rerun(Exception): pass
    state=NS()
    st=NS(info=lambda *a:None, warning=lambda *a:None, write=lambda *a:None,
          button=lambda *a, **k:True, session_state=state,
          rerun=lambda:(_ for _ in ()).throw(Rerun()))
    with pytest.raises(Rerun): pause_function(st)('job')
    assert state.pending_resume_job == 'job'


def test_manual_assistance_panel_removed_and_crop_default():
    import inspect
    from engine.clipping import create_highlight_clips
    assert inspect.signature(create_highlight_clips).parameters['framing'].default == 'face-crop'
    assert 'Check folder & associate newest download' not in Path('app.py').read_text()

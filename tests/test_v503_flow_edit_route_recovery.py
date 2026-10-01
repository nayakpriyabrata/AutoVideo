from types import SimpleNamespace

from engine.providers.flow_browser import FlowBrowser


class _Loc:
    def __init__(self):
        self.clicked = 0
        self.filled = None
    def click(self, **kwargs):
        self.clicked += 1
    def fill(self, value):
        self.filled = value


def _browser(url):
    b = FlowBrowser.__new__(FlowBrowser)
    b._page = SimpleNamespace(url=url)
    b._ctx = None
    b._project_ready = None
    b._project_url = FlowBrowser.normalize_project_url(url)
    return b


def test_v503_edit_route_is_never_considered_project_composer():
    b = _browser('https://flow.google.com/project/abc/edit/media123')
    b._try_resolve = lambda action, timeout_ms=0: _Loc()
    assert b._composer_visible(10) is False


def test_v503_ensure_project_leaves_edit_route_before_reuse():
    b = _browser('https://flow.google.com/project/abc/edit/media123')
    b._project_ready = 'P'
    calls = []

    def leave(timeout_ms=0):
        calls.append('leave')
        b._page.url = 'https://flow.google.com/project/abc'
        b._project_ready = None
        return True

    b.return_to_project = leave
    b._composer_visible = lambda timeout_ms=0: '/edit/' not in b._page.url
    b.dismiss_onboarding = lambda rounds=3: 0
    b.enter_flow_app = lambda: False
    b.open_project = lambda name: (_ for _ in ()).throw(AssertionError('must not look up project'))
    b.create_project = lambda name: (_ for _ in ()).throw(AssertionError('must not create project'))
    b.ensure_project('P', project_url='https://flow.google.com/project/abc')
    assert calls == ['leave']
    assert b._page.url == 'https://flow.google.com/project/abc'


def test_v503_detect_editor_mode_normalizes_edit_page_first():
    b = _browser('https://flow.google.com/project/abc/edit/media123')
    calls = []

    def leave(timeout_ms=0):
        calls.append('leave')
        b._page.url = 'https://flow.google.com/project/abc'
        return True

    b.return_to_project = leave
    b.recover_project_page = lambda *a, **k: False
    b._try_resolve = lambda action, timeout_ms=0: _Loc() if action == 'agent_prompt_box' else None
    assert b.detect_editor_mode() == 'agent'
    assert calls == ['leave']


def test_v503_submit_image_prompt_recovers_if_still_on_edit_page():
    b = _browser('https://flow.google.com/project/abc/edit/media123')
    calls = []
    box = _Loc()
    generate = _Loc()

    def recover(url, timeout_ms=0):
        calls.append(url)
        b._page.url = 'https://flow.google.com/project/abc'
        return True

    b.recover_project_page = recover
    b._set = lambda state: None
    b._resolve = lambda action, timeout_ms=8000, fmt=None: box if action == 'prompt_box' else generate
    b.submit_image_prompt('hello')
    assert calls == ['https://flow.google.com/project/abc']
    assert box.filled == 'hello'
    assert generate.clicked == 1

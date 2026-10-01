from types import SimpleNamespace

from engine.providers.flow_browser import FlowBrowserProvider


class _Page:
    def __init__(self, url='https://flow.google.com/project/abc'):
        self.url = url
        self.front = 0
        self.waits = 0
    def is_closed(self):
        return False
    def bring_to_front(self):
        self.front += 1
    def wait_for_timeout(self, ms):
        self.waits += 1


class _Ctx:
    def __init__(self, page):
        self.pages = [page]


class _Bridge:
    def __init__(self, assets):
        self._page = _Page()
        self._ctx = _Ctx(self._page)
        self.assets = assets
        self.download_calls = []
    def ensure_project(self, project, project_url=None):
        self._page.url = project_url or self._page.url
    def media_assets(self):
        return list(self.assets)
    def download_latest_asset(self, out_path, preferred_signature=None, before_signatures=None):
        self.download_calls.append(preferred_signature)
        return out_path


def test_recovery_does_not_open_poster_candidates(tmp_path, monkeypatch):
    p = FlowBrowserProvider(headless=True)
    bridge = _Bridge([{'sig':'poster-new','kind':'image'}])
    p.bridge = bridge
    monkeypatch.setattr(p, '_is_valid_video_file', lambda path: False)
    # Zero/near-zero window: method may poll once but must never click/download image poster.
    r = p.rescue_recent_project_video('job', str(tmp_path/'x.mp4'),
                                      project_url='https://flow.google.com/project/abc',
                                      wait_s=1, baseline_signatures={'old'})
    assert r is None
    assert bridge.download_calls == []


def test_recovery_requires_live_project_and_brings_it_front(monkeypatch):
    p = FlowBrowserProvider(headless=False)
    bridge = _Bridge([])
    p.bridge = bridge
    got = p._ensure_live_recovery_project('job', 'https://flow.google.com/project/abc')
    assert got is bridge
    assert bridge._page.front == 1

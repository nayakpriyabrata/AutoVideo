from engine.providers.flow_browser import FlowBrowser


def test_normalize_project_url():
    raw = 'https://flow.google.com/project/8d993ec2-65c4-4395-81da-7aac95f82871?foo=1'
    assert FlowBrowser.normalize_project_url(raw) == 'https://flow.google.com/project/8d993ec2-65c4-4395-81da-7aac95f82871'
    assert FlowBrowser.normalize_project_url('https://flow.google.com/') == ''


def test_wait_for_agent_generation_requires_new_signature():
    b = object.__new__(FlowBrowser)
    b.ui = {'timeouts': {'generation': 2, 'poll_interval': 0.01}, 'actions': {}}
    b.state_cb = None
    b.detect_service_busy = lambda: None
    b.detect_failure = lambda: None
    b._set = lambda s: None

    class P:
        def inner_text(self, *_):
            return 'creating image' if len(states) == 3 else 'done'
        def wait_for_timeout(self, *_):
            return None
    b._page = P()
    states = [
        [{'sig': 'old'}],
        [{'sig': 'old'}],
        [{'sig': 'old'}, {'sig': 'new'}],
    ]
    def assets():
        return states.pop(0) if len(states) > 1 else states[0]
    b.media_assets = assets
    assert b.wait_for_agent_generation(before_assets={'old'}, timeout_s=1)
    assert b.last_generated_asset_signature == 'new'


def test_current_project_url_safe_for_legacy_mock():
    b = object.__new__(FlowBrowser)
    b._page = type('P', (), {'url': 'https://flow.google.com/project/abc-123'})()
    assert b.current_project_url() == 'https://flow.google.com/project/abc-123'

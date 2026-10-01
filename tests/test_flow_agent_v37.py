import re
from types import SimpleNamespace
from engine.providers.flow_browser import FlowBrowser
from engine.routing.credit_router import CreditRouter

class FakeButton:
    def __init__(self, name): self.name=name; self.clicked=0
    def is_visible(self, timeout=0): return True
    def click(self): self.clicked += 1

class FakeRole:
    def __init__(self, page, pattern): self.page=page; self.pattern=pattern; self.first=self
    def is_visible(self, timeout=0):
        return any(self.pattern.search(n) for n in self.page.buttons)
    def click(self):
        for n,b in self.page.buttons.items():
            if self.pattern.search(n): b.clicked += 1; return

class FakePage:
    def __init__(self, body, buttons):
        self.body=body; self.buttons={n:FakeButton(n) for n in buttons}
    def inner_text(self, sel): return self.body
    def get_by_role(self, role, name=None): return FakeRole(self, name)
    def wait_for_timeout(self, ms): pass

def browser_with(page):
    b=FlowBrowser.__new__(FlowBrowser)
    b._page=page
    b.ui={"actions":{"agent_confirmation_buttons":["Approve","Always approve","Generate"]}}
    return b

def test_once_approval_clicks_approve_not_always():
    p=FakePage("Would you like me to kick off this 1 video generation, costing 7 credits?", ["Approve","Always approve","Reject"])
    b=browser_with(p)
    assert b.confirm_agent_generation(timeout_s=1, approval="once", max_credits=10)
    assert p.buttons["Approve"].clicked == 1
    assert p.buttons["Always approve"].clicked == 0
    assert b.last_agent_confirmation["cost"] == 7

def test_credit_guard_blocks_100_credit_quality():
    p=FakePage("Would you like me to kick off this 1 video generation, costing 100 credits?", ["Approve","Always approve","Reject"])
    b=browser_with(p)
    assert not b.confirm_agent_generation(timeout_s=1, approval="once", max_credits=10)
    assert p.buttons["Approve"].clicked == 0
    assert b.last_agent_confirmation["blocked"] is True
    assert b.last_agent_confirmation["cost"] == 100

def test_always_is_only_clicked_when_explicit():
    p=FakePage("costing 7 credits", ["Approve","Always approve"])
    b=browser_with(p)
    assert b.confirm_agent_generation(timeout_s=1, approval="always", max_credits=10)
    assert p.buttons["Always approve"].clicked == 1

def test_official_duration_cost_tables_are_not_linear():
    r=CreditRouter("FLOW_ECONOMY")
    assert r.model_cost("omni_draft", 4) == 4
    assert r.model_cost("omni_draft", 10) == 7
    assert r.model_cost("veo_lite", 4) == 10
    assert r.model_cost("veo_lite", 8) == 10

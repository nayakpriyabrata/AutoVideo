"""Offline locator contracts: chat deletion must never use a response menu."""
from types import SimpleNamespace as NS
import pytest
from engine.providers.gemini_web import GeminiWebBrowser


@pytest.mark.parametrize("ambiguous", [False, True])
def test_deletion_scopes_exact_sidebar_chat_and_dialog(ambiguous):
    actions = []
    page = NS(url="https://gemini.google.com/app/owned")

    class Node:
        def __init__(self, kind): self.kind = kind
        @property
        def first(self): return self
        def count(self): return 2 if ambiguous and self.kind == "links" else 1
        def is_visible(self): return True
        def scroll_into_view_if_needed(self, **kw): pass
        def hover(self, **kw): actions.append("hover:" + self.kind)
        def wait_for(self, **kw): actions.append("wait:" + self.kind + ":" + kw["state"])
        def filter(self, **kw):
            assert self.kind == "dialog" and "Delete chat" in kw["has_text"].pattern
            return self
        def locator(self, selector):
            if self.kind == "links":
                assert selector.startswith("xpath=ancestor-or-self")
                return Node("row")
            assert self.kind == "row" and selector == 'a[href*="/app/"]'
            return Node("row-links")
        def get_by_role(self, role, **kw):
            expected = {"row": ("button", "chat-menu"),
                        "menu": ("menuitem", "delete-item"),
                        "dialog": ("button", "confirm")}
            assert role == expected[self.kind][0]
            return Node(expected[self.kind][1])
        def click(self, **kw):
            actions.append("click:" + self.kind)
            if self.kind == "confirm": page.url = "https://gemini.google.com/app"

    def locator(selector):
        assert '/app/owned"' in selector
        return Node("links")

    def role(name, **kw):
        # No global button lookup: that would click the response ellipsis.
        assert name in ("menu", "dialog")
        return Node(name)

    page.locator = locator
    page.get_by_role = role
    page.keyboard = NS(press=lambda key: actions.append(key))
    browser = object.__new__(GeminiWebBrowser)
    browser._page = page
    browser._submitted_chat_id = "owned"
    assert browser.delete_current_chat() is (not ambiguous)
    if ambiguous:
        assert not any(x.startswith("click:") for x in actions)
    else:
        assert [a for a in actions if a.startswith("click:")] == [
            "click:chat-menu", "click:delete-item", "click:confirm"]
        assert "wait:links:detached" in actions

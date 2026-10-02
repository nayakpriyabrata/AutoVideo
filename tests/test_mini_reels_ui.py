"""Streamlit UI regression for article-feed idea selection in Mini Reels."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from engine.factory import Factory


def test_article_feed_idea_is_selected_into_mini_reels_topic(tmp_path, monkeypatch):
    import engine.factory as factory_module
    import engine.mini_reels as mini_reels
    import engine.project.database as database

    factory = Factory(str(tmp_path / "outputs"), str(tmp_path / "jobs.sqlite"))
    monkeypatch.setattr(factory_module, "Factory", lambda *args, **kwargs: factory)
    monkeypatch.setattr(database, "JobDB", lambda *args, **kwargs: factory.db)

    article = {
        "id": "article-idea-001",
        "source_id": "technivella",
        "source_name": "TechniVella",
        "title": "How tiny AI videos are made",
        "link": "https://technivella.com/ai-mini-reels/",
        "published": "Thu, 01 Oct 2026 10:00:00 +0000",
        "summary": "An excerpt about original AI video ideas.",
    }
    feed_calls = []

    def fake_fetch(source_id, count=10):
        feed_calls.append((source_id, count))
        return [article]

    monkeypatch.setattr(mini_reels, "fetch_content_ideas", fake_fetch)
    monkeypatch.setattr(mini_reels, "list_pending_reels", lambda *args, **kwargs: [])

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    app.sidebar.radio[0].set_value("MINI REELS").run()
    assert not app.exception

    next(widget for widget in app.radio if widget.label == "Choose where to start").set_value("articles").run()
    assert not app.exception
    assert feed_calls == []  # Feed access is explicitly user-triggered.

    next(widget for widget in app.button if widget.label == "↻ Refresh articles").click().run()
    assert not app.exception
    assert feed_calls == [("technivella", 12)]

    next(widget for widget in app.selectbox if widget.label == "Article idea (optional)").set_value(article["id"]).run()
    assert not app.exception
    topic = next(widget for widget in app.text_input if widget.label == "Starting idea")
    assert topic.value == article["title"]

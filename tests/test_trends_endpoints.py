"""Google Trends endpoint regressions for the legacy helper and Mini Reels."""
import sys
from types import SimpleNamespace

from engine import automation
from engine import mini_reels


def test_legacy_trend_helper_uses_current_trending_rss_routes(monkeypatch):
    seen = []

    def parse(url):
        seen.append(url)
        geo = url.rsplit("=", 1)[-1]
        return SimpleNamespace(entries=[{"title": f"topic {geo}"}])

    monkeypatch.setitem(sys.modules, "feedparser", SimpleNamespace(parse=parse))
    assert automation.fetch_trending_topics(count=2) == ["topic IN", "topic US"]
    assert seen == [
        "https://trends.google.com/trending/rss?geo=IN",
        "https://trends.google.com/trending/rss?geo=US",
    ]


def test_mini_reels_trend_route_uses_validated_google_region():
    assert mini_reels.TREND_RSS_URL.format(geo="IN") == "https://trends.google.com/trending/rss?geo=IN"

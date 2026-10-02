# v6.0.10 — Mini Reels article ideas and Google Trends RSS repair

## Mini Reels idea discovery

The Mini Reels page now offers three explicit starting points: manual text, Google Trends, and article websites. Article ideas are fetched on demand from curated public RSS feeds:

- **TechniVella** — AI, technology, and creator topics (`https://technivella.com/feed/`)
- **The Fact Site** — facts about animals, food, films, games, history, and more (`https://www.thefactsite.com/feed/`)
- **Interesting Facts** — science and everyday curiosities (`https://interestingfacts.com/feed/`)
- **ScienceDaily** — recent science discoveries (`https://www.sciencedaily.com/rss/all.xml`)

`factzone.com` currently resolves to a parked, for-sale page, so it is not presented as a working feed. The Fact Site and Interesting Facts provide currently usable fact/curiosity alternatives.

Only allowlisted HTTPS publisher feeds are requested. Redirects must remain on that publisher's host; XML size is capped at 1 MB, DTD/entities are rejected, and article links are restricted to the selected publisher. AutoVideoAI reads RSS only—it does not crawl article pages or download article media. The selector previews an article title/excerpt and can place that article into the editable idea field.

When an article is selected, its title and bounded excerpt are passed to the **visible Gemini Web session** as untrusted creative inspiration, not as instructions or verified evidence. Gemini is asked to make an original concept rather than copy article wording. The selected article remains visible as attribution, and the generated final Flow prompt remains reviewable/editable.

## Google Trends refresh repair

Replaced the retired `https://trends.google.com/trends/trendingsearches/daily/rss?geo=…` URL with Google's current `https://trends.google.com/trending/rss?geo=…` route in Mini Reels and the legacy trend helper. The existing bounded Mini Reels RSS parser, supported region choices, no-placeholder behavior, and manual-input fallback remain in place.

## Safety and scope

- No Gemini API fallback, API Veo, or separate TTS was introduced.
- Native Flow audio remains an optional prompt mode.
- Article or trend selection only drafts a prompt. The user must still review it and explicitly approve the one Flow generation; uncertain requests are not automatically resubmitted.
- No live Gemini session or credit-bearing Flow generation was used for verification.

## Verification

- Regression tests cover the new Trends URLs, RSS parsing/size/DTD limits, curated-feed selection, safe article-link handling, source-context prompt construction, and visible Gemini Web use. A Streamlit `AppTest` confirms that article feeds are fetched only on explicit refresh and the selected title populates the idea field.
- Full suite: **530 passed, 5 skipped, 12 existing deprecation warnings**.
- No live Gemini or Flow generation was used. The environment's direct `requests` calls are blocked by TLS connection resets, so feed/network behavior was validated with mocked HTTP responses; the new Trends RSS endpoint itself was independently confirmed accessible via the web fetch tool.

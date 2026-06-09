"""
sources.py
==========

Responsible for fetching the RSS feeds listed in config.SOURCES and turning
each entry into a small, uniform dictionary the rest of the bot understands:

    {
        "title":   "...",
        "summary": "...",
        "link":    "https://...",
        "source":  "CNBC Top News",
        "authority": 1,
    }

We use `feedparser`, which handles the many small differences between feed
formats (RSS, Atom, and various quirks) so we do not have to.
"""

import logging

import feedparser

import config

log = logging.getLogger("sources")


def _clean(value) -> str:
    """feedparser sometimes returns None or odd types; coerce to a clean str."""
    if not value:
        return ""
    return str(value).strip()


def fetch_source(source: dict) -> list:
    """
    Fetch a single feed and return a list of normalised article dicts.

    Network or parse errors are caught and logged so one broken feed never
    stops the whole bot. We just return an empty list and move on.
    """
    articles = []
    try:
        # feedparser accepts a custom User-Agent via the agent argument.
        feed = feedparser.parse(source["url"], agent=config.USER_AGENT)

        for entry in feed.entries:
            articles.append(
                {
                    "title": _clean(getattr(entry, "title", "")),
                    # Different feeds use summary, description, or neither.
                    "summary": _clean(
                        getattr(entry, "summary", "")
                        or getattr(entry, "description", "")
                    ),
                    "link": _clean(getattr(entry, "link", "")),
                    "source": source["name"],
                    "authority": source.get("authority", 0),
                    "market": source.get("market", "US"),
                }
            )
    except Exception as exc:  # noqa: BLE001 - we want to swallow any feed error
        log.warning("Could not fetch %s: %s", source["name"], exc)

    return articles


def fetch_all() -> list:
    """Fetch every configured source and return one combined list."""
    all_articles = []
    for source in config.SOURCES:
        items = fetch_source(source)
        log.info("Fetched %d items from %s", len(items), source["name"])
        all_articles.extend(items)
    return all_articles

"""
sources.py
==========

Fetches the RSS feeds in config.SOURCES and turns each entry into a small,
uniform dictionary the rest of the bot understands:

    {
        "title": "...", "summary": "...", "link": "https://...",
        "source": "CNBC Top News", "authority": 1, "market": "US",
        "published_ts": 1718000000.0 or None,
    }

It also drops anything older than config.MAX_ARTICLE_AGE_HOURS, so stale items
sitting in a feed are not alerted on. We use feedparser, which smooths over the
many differences between feed formats.
"""

import calendar
import logging
import time

import feedparser

import config

log = logging.getLogger("sources")


def _clean(value) -> str:
    if not value:
        return ""
    return str(value).strip()


def _entry_timestamp(entry):
    """
    Best-effort publish time as a unix timestamp (UTC), or None if the feed
    gives no usable date. feedparser exposes parsed dates as time.struct_time.
    """
    for attr in ("published_parsed", "updated_parsed"):
        st = getattr(entry, attr, None)
        if st:
            try:
                return calendar.timegm(st)  # struct_time is UTC here
            except Exception:  # noqa: BLE001
                pass
    return None


def fetch_source(source: dict, cutoff_ts: float) -> list:
    """
    Fetch a single feed and return normalised, recent article dicts. Anything
    older than cutoff_ts is skipped. Errors are logged, never raised, so one
    broken feed cannot stop the scan.
    """
    articles = []
    skipped_old = 0
    try:
        feed = feedparser.parse(source["url"], agent=config.USER_AGENT)

        for entry in feed.entries:
            ts = _entry_timestamp(entry)
            # Drop items we can date and that are too old. Keep undated items.
            if ts is not None and ts < cutoff_ts:
                skipped_old += 1
                continue

            articles.append({
                "title": _clean(getattr(entry, "title", "")),
                "summary": _clean(
                    getattr(entry, "summary", "") or getattr(entry, "description", "")
                ),
                "link": _clean(getattr(entry, "link", "")),
                "source": source["name"],
                "authority": source.get("authority", 0),
                "market": source.get("market", "US"),
                "published_ts": ts,
            })
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not fetch %s: %s", source["name"], exc)

    if skipped_old:
        log.info("Skipped %d stale items from %s", skipped_old, source["name"])
    return articles


def fetch_all() -> list:
    """Fetch every configured source and return one combined, recent list."""
    cutoff_ts = time.time() - (config.MAX_ARTICLE_AGE_HOURS * 3600)
    all_articles = []
    for source in config.SOURCES:
        items = fetch_source(source, cutoff_ts)
        log.info("Fetched %d recent items from %s", len(items), source["name"])
        all_articles.extend(items)
    return all_articles

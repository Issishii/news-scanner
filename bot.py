"""
bot.py
======

Main entry point for the market event scanner. Run with:

    python bot.py

Per cycle, for every source:
  1. Fetch articles and skip ones already seen (dedup).
  2. Analyse each new article: named tickers, events, themes, and a directness
     label for every relevant ticker.
  3. For each meaningfully linked ticker (named, direct beneficiary, or
     sympathy), pull live price/volume, apply liquidity filters, and compute
     the seven scores plus a watch-only label.
  4. Log every such ticker to the signals table (for later backtesting).
  5. Alert on the ones that clear the score threshold and carry an actionable
     watch label. The scanner never says buy or sell.

Press Ctrl+C to stop.
"""

import logging
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import config
import storage
import sources
import alerts
import filters
import scoring
import marketdata
from classifier import analyze

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")

# Directness buckets we actually score and log. sector_watch / ignore are noise.
SCORED_DIRECTNESS = ("direct_named", "direct_beneficiary", "sympathy_beneficiary")
# Labels that are worth an alert (the rest are logged but stay quiet).
ALERTABLE_LABELS = ("High priority watch", "Direct beneficiary", "Sympathy watch")
# Safety cap on how many tickers we score per article (a broad theme story can
# otherwise anchor dozens of sympathy names).
MAX_TICKERS_PER_ARTICLE = 15

# Rank directness so we score the strongest links first when capping.
_RANK = {"direct_named": 0, "direct_beneficiary": 1, "sympathy_beneficiary": 2}


def process_article(article):
    """Analyse one article. Returns the list of ticker results to alert on."""
    result = analyze(
        title=article["title"],
        summary=article["summary"],
        source_authority=article["authority"],
    )
    if not result.is_relevant:
        return None, result

    # Pick and prioritise the tickers worth scoring.
    candidates = [c for c in result.classifications if c.directness in SCORED_DIRECTNESS]
    candidates.sort(key=lambda c: (_RANK.get(c.directness, 9), c.ticker not in config.WATCHLIST))
    candidates = candidates[:MAX_TICKERS_PER_ARTICLE]

    to_alert = []
    for c in candidates:
        md = marketdata.get_market_data(c.ticker)
        micro = filters.is_microcap(md)
        ok, filter_reasons = filters.passes_filters(md)

        scores = scoring.score_ticker(result, c.directness, md, micro)

        # If liquidity filters fail and microcaps are off, force the cautious
        # label so a filtered name can never present as a clean watch.
        if not ok and not config.ALLOW_MICROCAPS:
            scores["watch_label"] = "Too speculative"

        # Log every scored ticker for backtesting, regardless of label.
        storage.log_signal(
            ticker=c.ticker, market=c.market, directness=c.directness,
            scores=scores, price_at_signal=(md.price if md.ok else None),
            article_title=article["title"], article_link=article.get("link", ""),
            source=article["source"],
        )

        # Decide whether to surface it.
        if (scores["watch_label"] in ALERTABLE_LABELS
                and scores["overall_watch_score"] >= config.MIN_WATCH_SCORE_TO_ALERT):
            to_alert.append({"ticker": c.ticker, "directness": c.directness, **scores})

    to_alert.sort(key=lambda r: r["overall_watch_score"], reverse=True)
    return to_alert, result


def process_once():
    articles = sources.fetch_all()
    log.info("Total articles fetched this cycle: %d", len(articles))

    new_count = alert_count = 0
    for article in articles:
        article_id = storage.make_article_id(article["link"], article["title"])
        if storage.is_seen(article_id):
            continue
        new_count += 1

        to_alert, result = process_article(article)

        if to_alert:
            message = alerts.format_alert(
                {
                    "title": article["title"], "link": article.get("link", ""),
                    "source": article["source"], "market": article.get("market", "?"),
                    "events": result.events, "themes": result.themes,
                    "reasons": result.reasons,
                },
                to_alert,
            )
            alerts.send_alert(message)
            alert_count += 1

        storage.mark_seen(article_id, article["title"], article.get("link", ""), article["source"])

    log.info("Cycle complete: %d new, %d alerts.", new_count, alert_count)


def main():
    log.info("Starting market EVENT SCANNER (watch-only, never buy/sell).")
    log.info("Poll interval: %ds | min watch score to alert: %d | microcaps: %s | price confirm: %s",
             config.POLL_INTERVAL_SECONDS, config.MIN_WATCH_SCORE_TO_ALERT,
             config.ALLOW_MICROCAPS, config.ENABLE_PRICE_CONFIRMATION)

    storage.init_db()

    if not ((config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID) or config.DISCORD_WEBHOOK_URL):
        log.warning("No Telegram/Discord credentials. Alerts print to console only.")

    cycle = 0
    try:
        while True:
            cycle += 1
            log.info("----- Cycle %d -----", cycle)
            process_once()
            if cycle % 30 == 0:
                storage.prune_old(days=14)
                log.info("Pruned old dedup records.")
            time.sleep(config.POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log.info("Stopped by user. Goodbye.")


if __name__ == "__main__":
    main()

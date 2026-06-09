"""
alerts.py
=========

Formats and sends scanner alerts to Telegram and/or Discord (console fallback
if neither is configured).

Hard rule from the brief: the scanner NEVER says buy or sell. It speaks only
in watch-only labels. assert_no_trade_language() enforces this at the last
moment before anything is sent, so even a future editing mistake cannot leak
a trade instruction.
"""

import logging
import re

import requests

import config

log = logging.getLogger("alerts")

# Words the scanner must never emit as instructions.
_FORBIDDEN = re.compile(r"\b(buy|sell|short|long the|go long|go short)\b", re.IGNORECASE)


def assert_no_trade_language(message: str):
    """Raise if a trade instruction slipped into the message."""
    if _FORBIDDEN.search(message):
        raise ValueError(
            "Refusing to send: message contains buy/sell language. "
            "This scanner is watch-only."
        )


def format_alert(article, ticker_results) -> str:
    """
    article: dict with title, link, source, market, plus scan-level fields
             (events, themes, reasons).
    ticker_results: list of dicts, each a per-ticker score bundle plus 'ticker'
                    and 'directness'. Already filtered and sorted by caller.
    """
    title = article["title"]
    source = article["source"]
    link = article.get("link", "")
    events = ", ".join(e.replace("_", " ") for e in article.get("events", [])) or "none"
    themes = ", ".join(t.replace("_", " ") for t in article.get("themes", [])) or "none"

    lines = [
        "*MARKET EVENT SCANNER*  (watch-only, not advice)",
        "",
        f"*Headline:* {title}",
        f"*Source:* {source}  |  *Market:* {article.get('market', '?')}",
        f"*Event type:* {events}",
        f"*Themes:* {themes}",
        "",
        "*Tickers to watch:*",
    ]

    for r in ticker_results:
        meter = _meter(r["overall_watch_score"])
        lines.append(
            f"  {r['ticker']}  [{r['watch_label']}]  score {r['overall_watch_score']}/100 {meter}"
        )
        lines.append(
            "      directness {d} | news {n} | theme {t} | liq {l} | "
            "reaction {p} | chase-risk {c}".format(
                d=r["directness"].replace("_", " "),
                n=r["news_urgency_score"], t=r["theme_relevance_score"],
                l=r["liquidity_score"], p=r["price_reaction_score"],
                c=r["chase_risk_score"],
            )
        )

    if article.get("reasons"):
        lines.append("")
        lines.append("*Why it may matter:*")
        for reason in article["reasons"]:
            lines.append(f"  - {reason}")

    if link:
        lines.append("")
        lines.append(f"*Link:* {link}")

    lines.append("")
    lines.append("_Watch-only signal. Confirm against the primary source. Not financial advice._")

    return "\n".join(lines)


def _meter(score_100):
    filled = round(score_100 / 10)
    return "[" + "#" * filled + "." * (10 - filled) + "]"


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------
def send_telegram(message: str) -> bool:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={
            "chat_id": config.TELEGRAM_CHAT_ID, "text": message,
            "parse_mode": "Markdown", "disable_web_page_preview": False,
        }, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("Telegram send failed: %s", exc)
        return False


def send_discord(message: str) -> bool:
    if not config.DISCORD_WEBHOOK_URL:
        return False
    if len(message) > 1900:
        message = message[:1900] + "\n... (truncated)"
    try:
        resp = requests.post(config.DISCORD_WEBHOOK_URL, json={"content": message}, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("Discord send failed: %s", exc)
        return False


def send_alert(message: str):
    """Guard the message, then dispatch to every configured channel."""
    assert_no_trade_language(message)

    sent = False
    if send_telegram(message):
        sent = True
        log.info("Alert sent to Telegram.")
    if send_discord(message):
        sent = True
        log.info("Alert sent to Discord.")
    if not sent:
        print("\n" + "=" * 64)
        print(message)
        print("=" * 64 + "\n")

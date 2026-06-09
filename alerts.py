"""
alerts.py
=========

Formats and sends scanner alerts. For Discord it now builds clean "embed"
cards (coloured bar by label, headline as a clickable title, tickers laid out
in tidy columns, scores in a compact block). Telegram and console get a plain
text version as a fallback.

Hard rule: the scanner never gives a trade instruction. It speaks only in the
fixed watch-only labels. assert_no_trade_language() polices the scanner's OWN
wording and ignores the quoted headline and source name, because real
headlines often contain words like "sell off".
"""

import logging
import re

import requests

import config

log = logging.getLogger("alerts")

_FORBIDDEN = re.compile(r"\b(buy|sell|short|long the|go long|go short)\b", re.IGNORECASE)

# Colour down the side of each Discord embed, chosen by the strongest label.
LABEL_COLORS = {
    "High priority watch": 0x2ECC71,  # green
    "Direct beneficiary":  0x3498DB,  # blue
    "Sympathy watch":      0x9B59B6,  # purple
    "Too speculative":     0xE67E22,  # orange
    "Ignore":              0x7F8C8D,  # grey
}
HOTLIST_COLOR = 0xF1C40F             # gold
FOOTER = "Watch-only signal. Confirm against the source. Not financial advice."
MAX_FIELDS = 6                        # tickers shown per card


def assert_no_trade_language(message: str, exempt=()):
    checked = message
    for piece in exempt:
        if piece:
            checked = checked.replace(piece, " ")
    if _FORBIDDEN.search(checked):
        raise ValueError(
            "Refusing to send: the scanner's own wording contains buy/sell "
            "language. This scanner is watch-only."
        )


def _short(text, limit):
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# Discord embeds (the nice version)
# ---------------------------------------------------------------------------
def build_discord_embeds(article, ticker_results):
    """Return a list with one embed card for this article."""
    title = article["title"]
    source = article["source"]
    link = article.get("link", "")
    events = ", ".join(e.replace("_", " ") for e in article.get("events", [])) or "none"
    themes = ", ".join(t.replace("_", " ") for t in article.get("themes", [])) or "none"

    top_label = ticker_results[0]["watch_label"] if ticker_results else "Ignore"

    desc = f"**Event:** {events}\n**Themes:** {themes}  ·  **Market:** {article.get('market', '?')}"
    if article.get("reasons"):
        desc += "\n\n" + " ".join(article["reasons"][:2])
    desc = _short(desc, 4000)

    fields = []
    for r in ticker_results[:MAX_FIELDS]:
        fields.append({
            "name": f"{r['ticker']}  |  {r['watch_label']}",
            "value": (
                f"**{r['overall_watch_score']}/100**\n"
                f"news {r['news_urgency_score']} · theme {r['theme_relevance_score']} · "
                f"direct {r['directness_score']}\n"
                f"liq {r['liquidity_score']} · react {r['price_reaction_score']} · "
                f"chase {r['chase_risk_score']}"
            ),
            "inline": True,
        })
    extra = len(ticker_results) - MAX_FIELDS
    if extra > 0:
        fields.append({"name": "More", "value": f"+{extra} other tickers below the top {MAX_FIELDS}", "inline": False})

    # Police the scanner's own words (labels, scores, reasons), never the headline.
    guard_text = desc + " " + " ".join(f["name"] + " " + f["value"] for f in fields)
    assert_no_trade_language(guard_text, exempt=[title, source])

    embed = {
        "title": _short(title, 250),
        "description": desc,
        "color": LABEL_COLORS.get(top_label, 0x7F8C8D),
        "fields": fields,
        "footer": {"text": FOOTER},
    }
    if link:
        embed["url"] = link
    return [embed]


def build_hotlist_embed(hot, scanned_count):
    """One digest card listing the hottest tickers across the whole scan."""
    best = {}
    for h in hot:
        if h["ticker"] not in best or h["score"] > best[h["ticker"]]["score"]:
            best[h["ticker"]] = h
    ranked = sorted(best.values(), key=lambda x: x["score"], reverse=True)[:10]

    if ranked:
        lines = [f"`{h['score']:>3}`  **{h['ticker']}**  ·  {h['label']}" for h in ranked]
        desc = "\n".join(lines)
    else:
        desc = "Nothing cleared the threshold this scan."

    return {
        "title": "Hot list (this scan)",
        "description": _short(desc, 4000),
        "color": HOTLIST_COLOR,
        "footer": {"text": f"{scanned_count} alerting stories this scan  ·  {FOOTER}"},
    }


# ---------------------------------------------------------------------------
# Plain text version (Telegram / console fallback)
# ---------------------------------------------------------------------------
def format_alert(article, ticker_results) -> str:
    title = article["title"]
    source = article["source"]
    link = article.get("link", "")
    events = ", ".join(e.replace("_", " ") for e in article.get("events", [])) or "none"
    themes = ", ".join(t.replace("_", " ") for t in article.get("themes", [])) or "none"

    lines = [
        "MARKET EVENT SCANNER (watch-only, not advice)",
        "",
        f"Headline: {title}",
        f"Source: {source} | Market: {article.get('market', '?')}",
        f"Event type: {events}",
        f"Themes: {themes}",
        "",
        "Tickers to watch:",
    ]
    for r in ticker_results:
        lines.append(f"  {r['ticker']}  [{r['watch_label']}]  score {r['overall_watch_score']}/100")
        lines.append(
            f"      direct {r['directness_score']} | news {r['news_urgency_score']} | "
            f"theme {r['theme_relevance_score']} | liq {r['liquidity_score']} | "
            f"react {r['price_reaction_score']} | chase {r['chase_risk_score']}"
        )
    if article.get("reasons"):
        lines.append("")
        lines.append("Why it may matter:")
        for reason in article["reasons"]:
            lines.append(f"  - {reason}")
    if link:
        lines.append("")
        lines.append(f"Link: {link}")
    lines.append("")
    lines.append(FOOTER)

    message = "\n".join(lines)
    assert_no_trade_language(message, exempt=[title, source])
    return message


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------
def send_telegram(message: str) -> bool:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": config.TELEGRAM_CHAT_ID, "text": message}, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("Telegram send failed: %s", exc)
        return False


def send_discord_text(message: str) -> bool:
    if not config.DISCORD_WEBHOOK_URL:
        return False
    if len(message) > 1900:
        message = message[:1900] + "\n... (truncated)"
    try:
        resp = requests.post(config.DISCORD_WEBHOOK_URL, json={"content": message}, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("Discord text send failed: %s", exc)
        return False


def send_discord_embeds(embeds) -> bool:
    if not config.DISCORD_WEBHOOK_URL:
        return False
    try:
        resp = requests.post(config.DISCORD_WEBHOOK_URL, json={"embeds": embeds[:10]}, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("Discord embed send failed: %s", exc)
        return False


def send_alert(text_message: str, embeds=None):
    """Prefer a Discord embed when available, else text, else console."""
    sent = False
    if embeds and config.DISCORD_WEBHOOK_URL:
        sent = send_discord_embeds(embeds)
    elif config.DISCORD_WEBHOOK_URL:
        sent = send_discord_text(text_message)
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        sent = send_telegram(text_message) or sent
    if not sent:
        print("\n" + "=" * 64)
        print(text_message)
        print("=" * 64 + "\n")

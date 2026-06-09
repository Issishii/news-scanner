"""
storage.py
==========

Two jobs, both backed by one local SQLite file (DATABASE_PATH in config):

  1. Deduplication: remember which articles we have already processed so we
     never alert twice (table: seen_articles).
  2. Signal log for backtesting: every time the scanner surfaces a ticker it
     records a row with the timestamp, the linked ticker, every score, and the
     reference price (table: signals). backtest.py reads these later.

SQLite ships with Python, so there is nothing to install.
"""

import hashlib
import sqlite3
import time

import config


def _connect():
    return sqlite3.connect(config.DATABASE_PATH)


def make_article_id(link: str, title: str) -> str:
    basis = (link or title or "").strip().lower()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def init_db():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_articles (
            id      TEXT PRIMARY KEY,
            title   TEXT,
            link    TEXT,
            source  TEXT,
            seen_at REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            ts                     REAL,      -- unix time the signal fired
            ticker                 TEXT,
            market                 TEXT,      -- US or ASX
            directness             TEXT,
            watch_label            TEXT,
            news_urgency_score     INTEGER,
            theme_relevance_score  INTEGER,
            directness_score       INTEGER,
            liquidity_score        INTEGER,
            price_reaction_score   INTEGER,
            chase_risk_score       INTEGER,
            overall_watch_score    INTEGER,
            price_at_signal        REAL,      -- reference price for return math
            article_title          TEXT,
            article_link           TEXT,
            source                 TEXT
        )
        """
    )
    conn.commit()
    conn.close()


# ----------------------------- dedup ---------------------------------------
def is_seen(article_id: str) -> bool:
    conn = _connect()
    seen = conn.execute(
        "SELECT 1 FROM seen_articles WHERE id = ? LIMIT 1", (article_id,)
    ).fetchone() is not None
    conn.close()
    return seen


def mark_seen(article_id, title, link, source):
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO seen_articles (id, title, link, source, seen_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (article_id, title, link, source, time.time()),
    )
    conn.commit()
    conn.close()


# ----------------------------- signals -------------------------------------
def log_signal(ticker, market, directness, scores, price_at_signal,
               article_title, article_link, source):
    """Persist one surfaced ticker for later backtesting."""
    conn = _connect()
    conn.execute(
        """
        INSERT INTO signals (
            ts, ticker, market, directness, watch_label,
            news_urgency_score, theme_relevance_score, directness_score,
            liquidity_score, price_reaction_score, chase_risk_score,
            overall_watch_score, price_at_signal,
            article_title, article_link, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            time.time(), ticker, market, directness, scores["watch_label"],
            scores["news_urgency_score"], scores["theme_relevance_score"],
            scores["directness_score"], scores["liquidity_score"],
            scores["price_reaction_score"], scores["chase_risk_score"],
            scores["overall_watch_score"], price_at_signal,
            article_title, article_link, source,
        ),
    )
    conn.commit()
    conn.close()


def fetch_signals(min_age_days=0.0):
    """
    Return signals at least min_age_days old, as a list of dict rows. Used by
    the backtester so it only evaluates signals that have had time to play out.
    """
    cutoff = time.time() - (min_age_days * 86400)
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM signals WHERE ts <= ? ORDER BY ts ASC", (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def prune_old(days: int = 14):
    cutoff = time.time() - (days * 86400)
    conn = _connect()
    conn.execute("DELETE FROM seen_articles WHERE seen_at < ?", (cutoff,))
    conn.commit()
    conn.close()

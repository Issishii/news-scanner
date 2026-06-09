"""
scoring.py
==========

Turns the news analysis plus market data into the seven scores in the brief
and a single watch-only label. Nothing here ever says buy or sell.

Sub-scores (each 0 to 10):
  news_urgency_score   - from the classifier (how market-moving the news is)
  theme_relevance_score- from the classifier (how on-theme the news is)
  directness_score     - from the directness bucket
  liquidity_score      - how liquid / large the name is
  price_reaction_score - is the market actually reacting (move + volume)?
  chase_risk_score     - how dangerous it would be to chase an already-run move

overall_watch_score (0 to 100):
  a weighted blend of the positive sub-scores, minus a chase-risk penalty.

watch_label: exactly one of config.WATCH_LABELS.
"""

import math
import config


# ---------------------------------------------------------------------------
# Individual sub-scores
# ---------------------------------------------------------------------------
def directness_score(directness: str) -> int:
    return config.DIRECTNESS_SCORES.get(directness, 0)


def liquidity_score(md) -> int:
    """
    0 to 10 from average dollar-ish liquidity. We use a log scale on average
    volume and market cap because these span many orders of magnitude.
    Unknown data returns a neutral 5 so news-only mode is not penalised hard.
    """
    if not md.ok or (md.avg_volume is None and md.market_cap_usd is None):
        return 5

    vol_score = 0
    if md.avg_volume:
        # 100k -> ~5, 1M -> ~6.7, 10M -> ~8.3, 100M -> 10
        vol_score = max(0, min(10, (math.log10(md.avg_volume) - 3) * 2.5 + 2.5))

    cap_score = 0
    if md.market_cap_usd:
        # 100M -> ~5, 1B -> ~6.7, 10B -> ~8.3, 1T -> ~11 (clamped to 10)
        cap_score = max(0, min(10, (math.log10(md.market_cap_usd) - 8) * 1.7 + 5))

    if md.avg_volume and md.market_cap_usd:
        return round((vol_score + cap_score) / 2)
    return round(vol_score or cap_score)


def price_reaction_score(md) -> int:
    """
    0 to 10. Rewards a real, confirmed reaction: a meaningful price move backed
    by above-average volume. No data -> 0 (no confirmation available).
    """
    if not md.ok or md.change_pct is None:
        return 0

    move = abs(md.change_pct)
    # Map move size to 0..7: 1% -> ~1.4, 3% -> ~4.2, 5%+ -> 7.
    move_score = min(7.0, move * 1.4)

    # Volume confirmation adds up to 3 points.
    vol_bonus = 0.0
    if md.volume_ratio:
        vol_bonus = min(3.0, (md.volume_ratio - 1.0) * 2.0) if md.volume_ratio > 1 else 0.0

    return round(min(10, move_score + vol_bonus))


def chase_risk_score(md, directness: str) -> int:
    """
    0 to 10 RISK (higher is worse). High when the price has already run a long
    way on the news, so acting now means chasing. Sympathy and low-liquidity
    names get an extra bump because they tend to spike and fade.
    """
    if not md.ok or md.change_pct is None:
        return 0

    move = abs(md.change_pct)
    # Moves beyond ~4% start to look like a chase; 10%+ is a hard chase.
    risk = min(8.0, max(0.0, (move - 4.0)) * 1.3)

    # A huge volume spike on a small name is classic chase-and-fade territory.
    if md.volume_ratio and md.volume_ratio > 3:
        risk += 1.5

    if directness == "sympathy_beneficiary":
        risk += 1.0

    if md.market_cap_usd is not None and md.market_cap_usd < config.FILTERS["microcap_market_cap_usd"]:
        risk += 1.5

    return round(min(10, risk))


# ---------------------------------------------------------------------------
# Overall score and label
# ---------------------------------------------------------------------------
def overall_watch_score(subs: dict) -> int:
    """
    Weighted blend of positive sub-scores scaled to 0..100, minus a chase-risk
    penalty. `subs` must contain the five positive sub-scores plus chase_risk.
    """
    w = config.SCORE_WEIGHTS
    weighted = (
        subs["news_urgency"]    * w["news_urgency"]
        + subs["theme_relevance"] * w["theme_relevance"]
        + subs["directness"]      * w["directness"]
        + subs["liquidity"]       * w["liquidity"]
        + subs["price_reaction"]  * w["price_reaction"]
    )  # this is on a 0..10 scale because weights sum to 1.0
    score_100 = weighted * 10.0
    score_100 -= subs["chase_risk"] * config.CHASE_RISK_PENALTY_PER_POINT
    return int(max(0, min(100, round(score_100))))


def watch_label(directness, overall, chase_risk, liquidity, is_microcap) -> str:
    """
    Map the numbers onto one of the five allowed watch-only labels.
    Precedence is deliberate and conservative.
    """
    L = config.LABELS

    if directness == "ignore":
        return "Ignore"

    # Speculative gates first: protect against chasing and illiquidity.
    if is_microcap and not config.ALLOW_MICROCAPS:
        return "Too speculative"
    if chase_risk >= L["chase_risk_too_high"]:
        return "Too speculative"
    if liquidity <= L["liquidity_too_low"]:
        return "Too speculative"

    if directness in ("direct_named", "direct_beneficiary"):
        if overall >= L["high_priority_min_score"]:
            return "High priority watch"
        return "Direct beneficiary"

    if directness == "sympathy_beneficiary":
        return "Sympathy watch"

    # sector_watch and anything else: low actionability.
    return "Ignore"


# ---------------------------------------------------------------------------
# Convenience: score one classified ticker end to end
# ---------------------------------------------------------------------------
def score_ticker(scan_result, directness, md, is_microcap):
    """
    Build the full set of seven scores plus the label for a single ticker.
    Returns a plain dict so it is easy to log and to put in alerts.
    """
    subs = {
        "news_urgency":    scan_result.news_urgency_score,
        "theme_relevance": scan_result.theme_relevance_score,
        "directness":      directness_score(directness),
        "liquidity":       liquidity_score(md),
        "price_reaction":  price_reaction_score(md),
        "chase_risk":      chase_risk_score(md, directness),
    }
    overall = overall_watch_score(subs)
    label = watch_label(directness, overall, subs["chase_risk"], subs["liquidity"], is_microcap)

    return {
        "news_urgency_score":   subs["news_urgency"],
        "theme_relevance_score": subs["theme_relevance"],
        "directness_score":     subs["directness"],
        "liquidity_score":      subs["liquidity"],
        "price_reaction_score": subs["price_reaction"],
        "chase_risk_score":     subs["chase_risk"],
        "overall_watch_score":  overall,
        "watch_label":          label,
    }

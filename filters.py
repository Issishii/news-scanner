"""
filters.py
==========

Liquidity and tradeability filters. These decide whether a ticker is worth
surfacing at all, independent of how exciting the news is. The point is to
stop the scanner from screaming about a name you could never sensibly act on
(illiquid microcaps, untradeable spreads).

All functions take a MarketData snapshot and the FILTERS dict from config.
They degrade gracefully: if a field is unknown (None), that particular check
is skipped rather than failing the ticker.
"""

import config


def is_microcap(md, filters=None) -> bool:
    """True if market cap is known and below the microcap threshold."""
    filters = filters or config.FILTERS
    if md.market_cap_usd is None:
        return False  # unknown cap is not treated as microcap
    return md.market_cap_usd < filters["microcap_market_cap_usd"]


def passes_filters(md, filters=None, allow_microcaps=None):
    """
    Return (ok: bool, reasons: list[str]).

    ok is False if any hard liquidity check fails. reasons explains why, which
    is useful for logging and for the "Too speculative" label.
    """
    filters = filters or config.FILTERS
    if allow_microcaps is None:
        allow_microcaps = config.ALLOW_MICROCAPS

    reasons = []

    # If we have no market data at all, we cannot filter on liquidity. Let it
    # through so news-only scoring still works, but note the gap.
    if not md.ok:
        return True, ["no market data (news-only scoring)"]

    # Market cap floor.
    if md.market_cap_usd is not None and md.market_cap_usd < filters["min_market_cap_usd"]:
        if not allow_microcaps:
            reasons.append(
                f"market cap ${md.market_cap_usd/1e6:.0f}M below "
                f"${filters['min_market_cap_usd']/1e6:.0f}M floor"
            )

    # Average volume floor.
    if md.avg_volume is not None and md.avg_volume < filters["min_avg_volume"]:
        if not allow_microcaps:
            reasons.append(
                f"avg volume {md.avg_volume:,.0f} below {filters['min_avg_volume']:,.0f}"
            )

    # Spread ceiling (only when we actually have a spread).
    if md.spread_pct is not None and md.spread_pct > filters["max_spread_pct"]:
        reasons.append(
            f"spread {md.spread_pct:.2f}% above {filters['max_spread_pct']:.2f}% ceiling"
        )

    ok = len(reasons) == 0
    if ok:
        reasons.append("liquidity filters passed")
    return ok, reasons

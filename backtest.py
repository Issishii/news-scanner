"""
backtest.py
===========

Evaluates how the scanner's signals actually played out. Run it on demand:

    python backtest.py

For every logged signal that is old enough, it measures the ticker's forward
return at 1, 3, and 5 trading days from the signal price, then compares that
to the relevant benchmarks (SPY/QQQ/SOXX for US names, ^AXJO/STW.AX/VAS.AX for
ASX names) over the same window. The difference is the "excess" return, which
tells you whether reacting to the signal would have beaten simply holding the
index.

This is measurement only. It does not place trades and it does not tell you
to. It is here so you can see, with real numbers, which signal types (by label
and directness) are worth your attention and which are noise.

The return MATH is split into pure functions at the top so it can be unit
tested without any network (see test_classifier.py).
"""

import logging
from collections import defaultdict

import config
import storage

log = logging.getLogger("backtest")


# ---------------------------------------------------------------------------
# Pure return math (no network) - easy to test
# ---------------------------------------------------------------------------
def forward_return_pct(base_price, future_price):
    """Percent change from base to future. None-safe."""
    if base_price in (None, 0) or future_price is None:
        return None
    return (future_price - base_price) / base_price * 100.0


def excess_return(asset_return, benchmark_return):
    """Asset return minus benchmark return (both in percent)."""
    if asset_return is None or benchmark_return is None:
        return None
    return asset_return - benchmark_return


def summarise(values):
    """Mean of the non-None values, or None if there are none."""
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


# ---------------------------------------------------------------------------
# Price history lookup (network, via the same provider stack)
# ---------------------------------------------------------------------------
def _close_prices_after(ticker, since_ts, horizons):
    """
    Return {horizon_days: close_price} using daily closes on/after the signal
    timestamp. Uses yfinance directly here for the historical pull. Returns an
    empty dict if data is unavailable.
    """
    try:
        import datetime as dt
        import yfinance as yf

        start = dt.datetime.utcfromtimestamp(since_ts).date()
        end = start + dt.timedelta(days=max(horizons) + 7)  # padding for weekends
        hist = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(), interval="1d")
        if hist is None or hist.empty:
            return {}

        closes = list(hist["Close"])
        out = {}
        # closes[0] is the signal-day close (the base for benchmarks too).
        for h in horizons:
            if len(closes) > h:
                out[h] = float(closes[h])
        out["base"] = float(closes[0])
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("History lookup failed for %s: %s", ticker, exc)
        return {}


def run_backtest(min_age_days=5.0):
    storage.init_db()
    signals = storage.fetch_signals(min_age_days=min_age_days)
    if not signals:
        print("No signals are old enough to evaluate yet. Let the scanner run, "
              "then come back in a few days.")
        return

    horizons = config.BACKTEST_HORIZONS
    # Aggregate excess returns grouped by watch_label, per horizon.
    by_label = defaultdict(lambda: {h: [] for h in horizons})
    # Cache benchmark histories so we fetch each once per signal date bucket.
    bench_cache = {}

    print(f"Evaluating {len(signals)} signals (>= {min_age_days} days old)...\n")

    for sig in signals:
        ticker = sig["ticker"]
        market = sig["market"]
        base = sig["price_at_signal"]

        asset = _close_prices_after(ticker, sig["ts"], horizons)
        if not asset:
            continue
        base_price = base or asset.get("base")

        benchmarks = config.BENCHMARKS.get(market, config.BENCHMARKS["US"])
        for h in horizons:
            asset_ret = forward_return_pct(base_price, asset.get(h))

            # Average excess vs the basket of benchmarks for this market.
            excesses = []
            for b in benchmarks:
                key = (b, round(sig["ts"]))
                if key not in bench_cache:
                    bench_cache[key] = _close_prices_after(b, sig["ts"], horizons)
                bh = bench_cache[key]
                bench_ret = forward_return_pct(bh.get("base"), bh.get(h))
                excesses.append(excess_return(asset_ret, bench_ret))

            avg_excess = summarise(excesses)
            if avg_excess is not None:
                by_label[sig["watch_label"]][h].append(avg_excess)

    # ----- report -----
    print(f"{'Watch label':<22}{'n':>5}  " + "  ".join(f"{h}d excess" for h in horizons))
    print("-" * 60)
    for label in config.WATCH_LABELS:
        buckets = by_label.get(label)
        if not buckets:
            continue
        n = max(len(buckets[h]) for h in horizons)
        cells = []
        for h in horizons:
            avg = summarise(buckets[h])
            cells.append("   n/a   " if avg is None else f"{avg:+7.2f}%")
        print(f"{label:<22}{n:>5}  " + "  ".join(cells))

    print("\nExcess return = signal ticker return minus its market benchmark "
          "average over the same window. Positive means the signal moved more "
          "than the index. This is analysis, not a recommendation.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_backtest()

"""
marketdata.py
=============

Live price and volume confirmation, behind a small provider interface so you
can swap yfinance for a paid data API later without touching the rest of the
scanner.

Design:
  - MarketData              : a simple, provider-agnostic snapshot dataclass.
  - MarketDataProvider      : abstract base class. Implement get_snapshot().
  - YFinanceProvider        : the free default, using the yfinance package.
  - PaidApiProvider         : a stub showing where a paid feed plugs in.
  - get_market_data(ticker) : module-level helper with a short TTL cache so we
                              do not hammer the data source every poll cycle.

If price confirmation is disabled in config, or the provider fails, callers
receive a MarketData with ok=False and simply score on news alone.
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional

import config

log = logging.getLogger("marketdata")


@dataclass
class MarketData:
    ticker: str
    ok: bool = False
    price: Optional[float] = None
    prev_close: Optional[float] = None
    change_pct: Optional[float] = None       # percent move vs previous close
    last_volume: Optional[float] = None
    avg_volume: Optional[float] = None        # ~20 day average daily volume
    volume_ratio: Optional[float] = None      # last_volume / avg_volume
    market_cap_usd: Optional[float] = None     # converted to USD for comparison
    spread_pct: Optional[float] = None         # bid-ask spread percent if known
    currency: Optional[str] = None


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------
class MarketDataProvider:
    """Implement get_snapshot(ticker) -> MarketData in a subclass."""
    def get_snapshot(self, ticker: str) -> MarketData:
        raise NotImplementedError


class YFinanceProvider(MarketDataProvider):
    """Free default provider using yfinance. Imported lazily so the rest of
    the scanner still runs if yfinance is not installed."""

    def get_snapshot(self, ticker: str) -> MarketData:
        try:
            import yfinance as yf
        except ImportError:
            log.warning("yfinance not installed; price confirmation disabled.")
            return MarketData(ticker=ticker, ok=False)

        meta = config.TICKER_META.get(ticker, {})
        currency = meta.get("currency", "USD")

        try:
            tk = yf.Ticker(ticker)

            # fast_info is the cheap, reliable path for price/volume/cap.
            fi = getattr(tk, "fast_info", {}) or {}
            price = _safe(fi, "last_price")
            prev_close = _safe(fi, "previous_close")
            last_volume = _safe(fi, "last_volume")
            market_cap = _safe(fi, "market_cap")

            # 20-day average volume from a short history pull.
            avg_volume = None
            try:
                hist = tk.history(period="1mo", interval="1d")
                if hist is not None and not hist.empty:
                    avg_volume = float(hist["Volume"].tail(20).mean())
                    if price is None:
                        price = float(hist["Close"].iloc[-1])
                    if prev_close is None and len(hist) >= 2:
                        prev_close = float(hist["Close"].iloc[-2])
            except Exception as exc:  # noqa: BLE001
                log.debug("History pull failed for %s: %s", ticker, exc)

            change_pct = None
            if price is not None and prev_close not in (None, 0):
                change_pct = (price - prev_close) / prev_close * 100.0

            volume_ratio = None
            if last_volume and avg_volume:
                volume_ratio = last_volume / avg_volume

            # Bid-ask spread is often unavailable for free; compute if present.
            spread_pct = None
            bid, ask = _safe(fi, "bid"), _safe(fi, "ask")
            if bid and ask and ask > 0:
                spread_pct = (ask - bid) / ask * 100.0

            market_cap_usd = _to_usd(market_cap, currency)

            return MarketData(
                ticker=ticker, ok=True, price=price, prev_close=prev_close,
                change_pct=change_pct, last_volume=last_volume,
                avg_volume=avg_volume, volume_ratio=volume_ratio,
                market_cap_usd=market_cap_usd, spread_pct=spread_pct,
                currency=currency,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("yfinance lookup failed for %s: %s", ticker, exc)
            return MarketData(ticker=ticker, ok=False, currency=currency)


class PaidApiProvider(MarketDataProvider):
    """Stub for a future paid provider (Polygon, Finnhub, EODHD, a broker
    API, and so on). Fill in get_snapshot to map their response onto the
    MarketData fields, then point ACTIVE_PROVIDER at this class."""
    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_snapshot(self, ticker: str) -> MarketData:
        raise NotImplementedError("Implement your paid provider here.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe(obj, key):
    """Read a key from fast_info whether it behaves like a dict or an object."""
    try:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)
    except Exception:  # noqa: BLE001
        return None


def _to_usd(value, currency):
    if value is None:
        return None
    if currency == "AUD":
        return value * config.AUD_TO_USD
    return value


# ---------------------------------------------------------------------------
# Active provider + small TTL cache
# ---------------------------------------------------------------------------
ACTIVE_PROVIDER: MarketDataProvider = YFinanceProvider()

_CACHE = {}            # ticker -> (timestamp, MarketData)
_CACHE_TTL_SECONDS = 90


def get_market_data(ticker: str) -> MarketData:
    """Return a cached or fresh snapshot. Honours the config master switch."""
    if not config.ENABLE_PRICE_CONFIRMATION:
        return MarketData(ticker=ticker, ok=False)

    now = time.time()
    cached = _CACHE.get(ticker)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    snapshot = ACTIVE_PROVIDER.get_snapshot(ticker)
    _CACHE[ticker] = (now, snapshot)
    return snapshot

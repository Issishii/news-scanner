"""
test_scanner.py
===============

Offline checks for the whole scanner. No network required. Run with:

    python test_scanner.py

It exercises: directness classification, the seven scores + watch labels using
synthetic market data, liquidity filters, the no-buy/sell guard, signal
logging, and the backtest return math.
"""

import os
import tempfile

# Configure BEFORE importing anything that reads config.
os.environ["DATABASE_PATH"] = os.path.join(tempfile.gettempdir(), "scanner_test.db")
os.environ["ENABLE_PRICE_CONFIRMATION"] = "0"   # full pipeline offline (news-only)

import config
import storage
import scoring
import filters
import alerts
import backtest
from classifier import analyze
from marketdata import MarketData

PASS = "PASS"


def check(name, condition):
    print(f"[{PASS if condition else 'FAIL'}] {name}")
    assert condition, name


# ---------------------------------------------------------------------------
print("\n=== 1. DIRECTNESS CLASSIFICATION ===\n")

SAMPLES = [
    ("US imposes export controls on advanced AI chips to China",
     "New license requirements hit shipments of H100 and H200 accelerators.", 1),
    ("Trump to take equity stake in Intel under chips deal",
     "The White House will convert CHIPS Act grants into a government stake in Intel.", 2),
    ("Pentagon awards quantum computing contract to IonQ",
     "Defense funding for quantum research; Rigetti also bidding.", 1),
    ("Australia unveils rare earths stockpile and offtake deals",
     "Critical minerals plan aims to break Chinese magnet supply dominance.", 1),
    ("RBA holds the cash rate steady",
     "The Reserve Bank of Australia left interest rates unchanged.", 1),
]

for title, summ, auth in SAMPLES:
    r = analyze(title, summ, source_authority=auth)
    labels = {c.ticker: c.directness for c in r.classifications}
    print(f"HEADLINE: {title}")
    print(f"  events : {r.events}")
    print(f"  themes : {r.themes}")
    print(f"  urgency {r.news_urgency_score}/10 | theme-rel {r.theme_relevance_score}/10")
    # Show a few of the most direct classifications.
    direct = {t: l for t, l in labels.items() if l in ('direct_named', 'direct_beneficiary')}
    symp = [t for t, l in labels.items() if l == 'sympathy_beneficiary']
    print(f"  direct : {direct}")
    print(f"  sympathy: {symp[:6]}")
    print("-" * 68)

# Targeted assertions on the export-controls case.
r = analyze(SAMPLES[0][0], SAMPLES[0][1], 1)
labels = {c.ticker: c.directness for c in r.classifications}
check("NVDA is direct beneficiary of export controls (unnamed)", labels.get("NVDA") == "direct_beneficiary")
check("AMD is direct beneficiary of export controls (unnamed)", labels.get("AMD") == "direct_beneficiary")
check("MU classified as a peer (sympathy or direct)", labels.get("MU") in ("direct_beneficiary", "sympathy_beneficiary"))

# Intel case: explicitly named -> direct_named.
r = analyze(SAMPLES[1][0], SAMPLES[1][1], 2)
labels = {c.ticker: c.directness for c in r.classifications}
check("INTC is direct_named when Intel is in the text", labels.get("INTC") == "direct_named")

# Rare earths -> MP and Lynas are direct beneficiaries via critical_minerals.
r = analyze(SAMPLES[3][0], SAMPLES[3][1], 1)
labels = {c.ticker: c.directness for c in r.classifications}
check("MP Materials is direct beneficiary of critical minerals policy", labels.get("MP") == "direct_beneficiary")
check("LYC.AX (Lynas) is direct beneficiary of critical minerals policy", labels.get("LYC.AX") == "direct_beneficiary")


# ---------------------------------------------------------------------------
print("\n=== 2. SCORING + WATCH LABELS (synthetic market data) ===\n")

r = analyze("US imposes export controls on AI chips to China",
            "License requirements on H100 shipments.", 1)

# A liquid mega-cap reacting moderately -> should be a strong watch.
big_liquid = MarketData(ticker="NVDA", ok=True, price=102.0, prev_close=100.0,
                        change_pct=2.0, last_volume=60e6, avg_volume=40e6,
                        volume_ratio=1.5, market_cap_usd=2.5e12, spread_pct=0.02,
                        currency="USD")
s = scoring.score_ticker(r, "direct_beneficiary", big_liquid, is_microcap=False)
print("NVDA (liquid, +2%, vol 1.5x):", s)
check("Liquid direct beneficiary is an actionable watch label",
      s["watch_label"] in ("High priority watch", "Direct beneficiary"))
check("All seven scores are present",
      all(k in s for k in ["news_urgency_score", "theme_relevance_score", "directness_score",
                           "liquidity_score", "price_reaction_score", "chase_risk_score",
                           "overall_watch_score"]))

# A name that has already gapped +18% on huge volume -> chase risk should label
# it Too speculative even though the news is real.
ran_hard = MarketData(ticker="QUBT", ok=True, price=11.8, prev_close=10.0,
                      change_pct=18.0, last_volume=50e6, avg_volume=5e6,
                      volume_ratio=10.0, market_cap_usd=1.5e9, spread_pct=0.1,
                      currency="USD")
s = scoring.score_ticker(r, "sympathy_beneficiary", ran_hard, is_microcap=False)
print("QUBT (already +18%, vol 10x):", s)
check("A name that already ran hard is flagged Too speculative", s["watch_label"] == "Too speculative")
check("Chase risk score is high for the run-up name", s["chase_risk_score"] >= 7)

# An illiquid microcap with microcaps disabled -> Too speculative.
micro = MarketData(ticker="AXE.AX", ok=True, price=0.30, prev_close=0.29,
                   change_pct=3.4, last_volume=50_000, avg_volume=40_000,
                   volume_ratio=1.25, market_cap_usd=80e6, spread_pct=0.5,
                   currency="AUD")
s = scoring.score_ticker(r, "sympathy_beneficiary", micro, is_microcap=True)
print("AXE.AX (microcap):", s)
check("Microcap is flagged Too speculative when microcaps disabled", s["watch_label"] == "Too speculative")


# ---------------------------------------------------------------------------
print("\n=== 3. LIQUIDITY FILTERS ===\n")
ok, reasons = filters.passes_filters(micro, allow_microcaps=False)
print("microcap passes_filters (microcaps off):", ok, reasons)
check("Microcap fails the liquidity filters when disabled", ok is False)

ok2, reasons2 = filters.passes_filters(big_liquid, allow_microcaps=False)
print("mega-cap passes_filters:", ok2, reasons2)
check("Mega-cap passes the liquidity filters", ok2 is True)


# ---------------------------------------------------------------------------
print("\n=== 4. NO BUY/SELL GUARD ===\n")
try:
    alerts.assert_no_trade_language("This is a clean watch-only message.")
    check("Clean watch-only message is allowed", True)
except ValueError:
    check("Clean watch-only message is allowed", False)

raised = False
try:
    alerts.assert_no_trade_language("You should buy NVDA now.")
except ValueError:
    raised = True
check("A message containing 'buy' is blocked", raised)


# ---------------------------------------------------------------------------
print("\n=== 5. SIGNAL LOGGING + FETCH ===\n")
storage.init_db()
storage.log_signal(
    ticker="NVDA", market="US", directness="direct_beneficiary",
    scores=scoring.score_ticker(r, "direct_beneficiary", big_liquid, False),
    price_at_signal=102.0, article_title="t", article_link="l", source="src",
)
rows = storage.fetch_signals(min_age_days=0)
print(f"signals stored: {len(rows)}; first ticker: {rows[0]['ticker']}")
check("Signal was logged and is retrievable", len(rows) >= 1 and rows[0]["ticker"] == "NVDA")


# ---------------------------------------------------------------------------
print("\n=== 6. BACKTEST RETURN MATH ===\n")
check("forward_return_pct(100 -> 110) == 10%", abs(backtest.forward_return_pct(100, 110) - 10.0) < 1e-9)
check("forward_return_pct handles missing data", backtest.forward_return_pct(None, 110) is None)
check("excess_return(8% asset, 3% bench) == 5%", abs(backtest.excess_return(8.0, 3.0) - 5.0) < 1e-9)
check("summarise averages correctly", abs(backtest.summarise([2.0, 4.0, None]) - 3.0) < 1e-9)

print("\nAll checks finished.\n")

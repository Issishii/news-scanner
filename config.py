"""
config.py
=========

Central configuration for the market-news EVENT SCANNER.

This is a research and monitoring tool. It surfaces and ranks news for your
own attention. It is NOT a trading bot: it never tells you to buy or sell.
The strongest thing it ever says is "High priority watch".

Sections:
  1. Secrets and runtime settings (from environment variables)
  2. Fixed watchlist (your original tickers)
  3. Ticker registry (names, market, currency) used for text matching
  4. THEME_UNIVERSE (theme -> tickers) and theme keywords
  5. Event rules (policy event typing) and impact notes
  6. Directness: which tickers benefit directly from which events
  7. Scoring weights and label thresholds
  8. Liquidity / market-cap / spread filters
  9. Benchmarks for backtesting
 10. News sources (US + ASX)
"""

import os

# ---------------------------------------------------------------------------
# 1. Secrets and runtime settings
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "120"))

# Only surface a ticker as an alert when its overall watch score clears this
# floor (0 to 100). Raise it to make the scanner quieter.
MIN_WATCH_SCORE_TO_ALERT = int(os.getenv("MIN_WATCH_SCORE_TO_ALERT", "45"))

DATABASE_PATH = os.getenv("DATABASE_PATH", "scanner.db")
USER_AGENT = "market-event-scanner/2.0 (+personal research use)"

# Master switch: should the scanner look at illiquid microcaps at all?
# Default False, as required by the brief. Override with ALLOW_MICROCAPS=1.
ALLOW_MICROCAPS = os.getenv("ALLOW_MICROCAPS", "0") in ("1", "true", "True")

# Turn live price/volume confirmation on or off. If off (or yfinance is not
# installed), the scanner still runs on news + theme + directness alone.
ENABLE_PRICE_CONFIRMATION = os.getenv("ENABLE_PRICE_CONFIRMATION", "1") in ("1", "true", "True")


# ---------------------------------------------------------------------------
# 2. Fixed watchlist (your original tickers, always treated as first class)
# ---------------------------------------------------------------------------
WATCHLIST = [
    "INTC", "AMD", "NVDA", "IBM", "IONQ",
    "RGTI", "QBTS", "QUBT", "TSM", "AVGO", "MU",
]


# ---------------------------------------------------------------------------
# 3. Ticker registry
# ---------------------------------------------------------------------------
# ticker -> {names, market, currency}
#   names:    aliases used to detect the company in news text
#   market:   "US" or "ASX" (drives which benchmarks and rules apply)
#   currency: rough currency for market-cap comparisons (USD or AUD)
#
# IMPORTANT: listed companies get acquired, delisted, or change tickers.
# Verify this list periodically. Example: Altium (ALU.AX) was delisted in
# August 2024 after Renesas acquired it, so it is deliberately NOT here.
# ASX tickers use the ".AX" suffix that Yahoo Finance / yfinance expects.

TICKER_META = {
    # --- US watchlist ---
    "INTC": {"names": ["Intel"], "market": "US", "currency": "USD"},
    "AMD":  {"names": ["AMD", "Advanced Micro Devices"], "market": "US", "currency": "USD"},
    "NVDA": {"names": ["Nvidia", "NVIDIA"], "market": "US", "currency": "USD"},
    "IBM":  {"names": ["IBM", "International Business Machines"], "market": "US", "currency": "USD"},
    "IONQ": {"names": ["IonQ"], "market": "US", "currency": "USD"},
    "RGTI": {"names": ["Rigetti"], "market": "US", "currency": "USD"},
    "QBTS": {"names": ["D-Wave", "D Wave", "DWave"], "market": "US", "currency": "USD"},
    "QUBT": {"names": ["Quantum Computing Inc", "QCI"], "market": "US", "currency": "USD"},
    "TSM":  {"names": ["TSMC", "Taiwan Semiconductor"], "market": "US", "currency": "USD"},
    "AVGO": {"names": ["Broadcom"], "market": "US", "currency": "USD"},
    "MU":   {"names": ["Micron"], "market": "US", "currency": "USD"},

    # --- US thematic extensions ---
    "SMCI": {"names": ["Super Micro", "Supermicro"], "market": "US", "currency": "USD"},
    "VRT":  {"names": ["Vertiv"], "market": "US", "currency": "USD"},
    "ANET": {"names": ["Arista"], "market": "US", "currency": "USD"},
    "DELL": {"names": ["Dell"], "market": "US", "currency": "USD"},
    "LMT":  {"names": ["Lockheed Martin", "Lockheed"], "market": "US", "currency": "USD"},
    "RTX":  {"names": ["Raytheon", "RTX"], "market": "US", "currency": "USD"},
    "NOC":  {"names": ["Northrop Grumman", "Northrop"], "market": "US", "currency": "USD"},
    "GD":   {"names": ["General Dynamics"], "market": "US", "currency": "USD"},
    "PLTR": {"names": ["Palantir"], "market": "US", "currency": "USD"},
    "MP":   {"names": ["MP Materials"], "market": "US", "currency": "USD"},
    "CCJ":  {"names": ["Cameco"], "market": "US", "currency": "USD"},
    "UEC":  {"names": ["Uranium Energy"], "market": "US", "currency": "USD"},
    "OKLO": {"names": ["Oklo"], "market": "US", "currency": "USD"},
    "SMR":  {"names": ["NuScale"], "market": "US", "currency": "USD"},
    "LEU":  {"names": ["Centrus"], "market": "US", "currency": "USD"},
    "ALB":  {"names": ["Albemarle"], "market": "US", "currency": "USD"},
    "LAC":  {"names": ["Lithium Americas"], "market": "US", "currency": "USD"},
    "SQM":  {"names": ["SQM", "Sociedad Quimica"], "market": "US", "currency": "USD"},

    # --- ASX thematic (.AX suffix) ---
    "AXE.AX": {"names": ["Archer Materials", "Archer"], "market": "ASX", "currency": "AUD"},
    "BRN.AX": {"names": ["BrainChip", "Brainchip"], "market": "ASX", "currency": "AUD"},
    "WBT.AX": {"names": ["Weebit Nano", "Weebit"], "market": "ASX", "currency": "AUD"},
    "NXT.AX": {"names": ["NextDC", "Next DC"], "market": "ASX", "currency": "AUD"},
    "MP1.AX": {"names": ["Megaport"], "market": "ASX", "currency": "AUD"},
    "DRO.AX": {"names": ["DroneShield"], "market": "ASX", "currency": "AUD"},
    "EOS.AX": {"names": ["Electro Optic Systems"], "market": "ASX", "currency": "AUD"},
    "LYC.AX": {"names": ["Lynas"], "market": "ASX", "currency": "AUD"},
    "ILU.AX": {"names": ["Iluka"], "market": "ASX", "currency": "AUD"},
    "ARU.AX": {"names": ["Arafura"], "market": "ASX", "currency": "AUD"},
    "PDN.AX": {"names": ["Paladin Energy", "Paladin"], "market": "ASX", "currency": "AUD"},
    "BOE.AX": {"names": ["Boss Energy"], "market": "ASX", "currency": "AUD"},
    "DYL.AX": {"names": ["Deep Yellow"], "market": "ASX", "currency": "AUD"},
    "PLS.AX": {"names": ["Pilbara Minerals", "Pilbara"], "market": "ASX", "currency": "AUD"},
    "IGO.AX": {"names": ["IGO"], "market": "ASX", "currency": "AUD"},
    "MIN.AX": {"names": ["Mineral Resources"], "market": "ASX", "currency": "AUD"},
    "LTR.AX": {"names": ["Liontown"], "market": "ASX", "currency": "AUD"},
    "CBA.AX": {"names": ["Commonwealth Bank", "CommBank"], "market": "ASX", "currency": "AUD"},
    "NAB.AX": {"names": ["National Australia Bank", "NAB"], "market": "ASX", "currency": "AUD"},
    "WBC.AX": {"names": ["Westpac"], "market": "ASX", "currency": "AUD"},
    "ANZ.AX": {"names": ["ANZ"], "market": "ASX", "currency": "AUD"},
    "MQG.AX": {"names": ["Macquarie"], "market": "ASX", "currency": "AUD"},
    "BHP.AX": {"names": ["BHP"], "market": "ASX", "currency": "AUD"},
    "RIO.AX": {"names": ["Rio Tinto"], "market": "ASX", "currency": "AUD"},
    "FMG.AX": {"names": ["Fortescue"], "market": "ASX", "currency": "AUD"},
    "S32.AX": {"names": ["South32"], "market": "ASX", "currency": "AUD"},
    "WDS.AX": {"names": ["Woodside"], "market": "ASX", "currency": "AUD"},
    "STO.AX": {"names": ["Santos"], "market": "ASX", "currency": "AUD"},
    "XRO.AX": {"names": ["Xero"], "market": "ASX", "currency": "AUD"},
    "WTC.AX": {"names": ["WiseTech"], "market": "ASX", "currency": "AUD"},
    "TNE.AX": {"names": ["TechnologyOne", "Technology One"], "market": "ASX", "currency": "AUD"},
}


# ---------------------------------------------------------------------------
# 4. THEME_UNIVERSE and theme keywords
# ---------------------------------------------------------------------------
# theme -> list of tickers that belong to it. A ticker may sit in several
# themes. Peers within a theme are used for "sympathy" classification.
THEME_UNIVERSE = {
    "quantum":              ["IONQ", "RGTI", "QBTS", "QUBT", "IBM", "AXE.AX"],
    "semiconductors":       ["INTC", "AMD", "NVDA", "TSM", "AVGO", "MU", "BRN.AX", "WBT.AX"],
    "ai_infrastructure":    ["NVDA", "AVGO", "SMCI", "VRT", "ANET", "DELL", "NXT.AX", "MP1.AX"],
    "defence":              ["LMT", "RTX", "NOC", "GD", "PLTR", "DRO.AX", "EOS.AX"],
    "rare_earths":          ["MP", "LYC.AX", "ILU.AX", "ARU.AX"],
    "uranium_nuclear":      ["CCJ", "UEC", "OKLO", "SMR", "LEU", "PDN.AX", "BOE.AX", "DYL.AX"],
    "lithium_battery":      ["ALB", "LAC", "SQM", "PLS.AX", "IGO.AX", "MIN.AX", "LTR.AX"],
    "asx_banks_rates":      ["CBA.AX", "NAB.AX", "WBC.AX", "ANZ.AX", "MQG.AX"],
    "asx_mining_resources": ["BHP.AX", "RIO.AX", "FMG.AX", "S32.AX", "WDS.AX", "STO.AX"],
    "asx_tech":             ["XRO.AX", "WTC.AX", "TNE.AX", "NXT.AX", "MP1.AX"],
}

# Keywords that signal a theme is in play even when no specific company is named.
THEME_KEYWORDS = {
    "quantum": ["quantum computing", "quantum computer", "qubit", "quantum advantage"],
    "semiconductors": ["semiconductor", "chipmaker", "chip maker", "foundry", "wafer",
                       "fab ", "lithography", "advanced chips"],
    "ai_infrastructure": ["data center", "datacenter", "ai infrastructure", "gpu cluster",
                          "hyperscaler", "ai accelerator", "liquid cooling"],
    "defence": ["defense", "defence", "pentagon", "military", "missile", "munitions",
                "drone", "darpa", "national security"],
    "rare_earths": ["rare earth", "rare earths", "neodymium", "permanent magnet", "magnet supply"],
    "uranium_nuclear": ["uranium", "nuclear power", "nuclear reactor", "enrichment",
                        "small modular reactor", "smr"],
    "lithium_battery": ["lithium", "battery metals", "spodumene", "cathode", "ev battery",
                        "nickel", "cobalt"],
    "asx_banks_rates": ["reserve bank of australia", "rba", "cash rate", "australian interest rate",
                        "australian bank", "mortgage rate"],
    "asx_mining_resources": ["iron ore", "lng", "coal price", "commodity price", "australian miner"],
    "asx_tech": ["australian tech", "asx tech"],
}


# ---------------------------------------------------------------------------
# 5. Event rules (policy event typing) and impact notes
# ---------------------------------------------------------------------------
EVENT_RULES = {
    "government_investment": {"weight": 4, "terms": [
        "government stake", "equity stake", "federal investment", "golden share",
        "nationalize", "nationalise", "bailout", "taxpayer stake", "treasury stake"]},
    "tariff": {"weight": 3, "terms": [
        "tariff", "tariffs", "import duty", "import duties", "section 301",
        "section 232", "levy", "trade penalty"]},
    "export_controls": {"weight": 4, "terms": [
        "export control", "export controls", "export restriction", "export ban",
        "entity list", "license requirement", "licence requirement",
        "bureau of industry and security"]},
    "china_policy": {"weight": 2, "terms": [
        "china", "beijing", "huawei", "smic", "decoupling", "de-risking",
        "chinese military"]},
    "defence_funding": {"weight": 2, "terms": [
        "defense", "defence", "pentagon", "department of defense", "darpa",
        "military contract", "national security"]},
    "ai_chips": {"weight": 2, "terms": [
        "ai chip", "ai chips", "ai accelerator", "h100", "h200", "blackwell",
        "advanced chips", "advanced semiconductors"]},
    "quantum_computing": {"weight": 2, "terms": [
        "quantum computing", "quantum computer", "qubit", "quantum advantage"]},
    "semiconductor_funding": {"weight": 3, "terms": [
        "chips act", "chips and science act", "semiconductor subsidy",
        "semiconductor subsidies", "fab funding", "foundry subsidy", "semiconductor grant"]},
    "critical_minerals": {"weight": 3, "terms": [
        "critical minerals", "rare earth", "rare earths", "magnet supply",
        "lithium supply", "stockpile", "offtake agreement"]},
    "nuclear_policy": {"weight": 2, "terms": [
        "nuclear power", "uranium enrichment", "small modular reactor",
        "nuclear funding", "reactor approval"]},
    "rates_policy": {"weight": 2, "terms": [
        "rate cut", "rate hike", "interest rate decision", "cash rate",
        "monetary policy", "reserve bank"]},
}

EVENT_IMPACT_NOTES = {
    "government_investment": "Government equity or funding can prop up a company or dilute holders, and signals strategic intent.",
    "tariff": "Tariffs raise input and product costs, squeeze margins, and can trigger retaliation across supply chains.",
    "export_controls": "Export curbs can cut off a large slice of revenue (especially China sales) for chipmakers and suppliers.",
    "china_policy": "China is a major end market and manufacturing hub, so policy shifts move demand and supply for these names.",
    "defence_funding": "Defence and national-security spending can create new, sticky revenue for chip, drone, and quantum firms.",
    "ai_chips": "AI chip demand and limits on advanced chips drive the revenue outlook for GPU and accelerator makers.",
    "quantum_computing": "Quantum names are highly sensitive to government interest, funding, and contracts given their early stage.",
    "semiconductor_funding": "Subsidies and grants improve project economics and shift where fabs get built, helping recipients.",
    "critical_minerals": "Supply-security policy and offtake deals can re-rate rare earth and lithium producers quickly.",
    "nuclear_policy": "Pro-nuclear policy and funding support uranium miners and reactor developers.",
    "rates_policy": "Rate decisions move bank margins and rate-sensitive sectors, especially in the ASX banking complex.",
}

# Action and administration language (bumps news urgency).
ACTION_TERMS = ["announce", "announces", "announced", "sign", "signs", "signed",
    "impose", "imposes", "imposed", "ban", "bans", "banned", "restrict", "restricts",
    "restricted", "invest", "invests", "invested", "award", "awards", "awarded",
    "approve", "approves", "approved", "block", "blocks", "blocked", "order", "orders", "ordered"]
ADMIN_TERMS = ["trump", "white house", "president", "administration", "commerce secretary",
    "treasury secretary", "executive order", "rba", "reserve bank"]


# ---------------------------------------------------------------------------
# 6. Directness: which tickers benefit directly from which events
# ---------------------------------------------------------------------------
# When one of these events fires, these tickers are "direct beneficiaries"
# even if they are not named in the text, because they are the primary
# subjects of that policy. Everything else in the matched theme(s) becomes a
# "sympathy" play.
EVENT_PRIMARY_TICKERS = {
    "export_controls": ["NVDA", "AMD", "TSM", "MU"],
    "ai_chips": ["NVDA", "AMD", "AVGO", "TSM"],
    "semiconductor_funding": ["INTC", "TSM", "MU"],
    "government_investment": ["INTC"],
    "tariff": ["TSM"],
    "china_policy": ["NVDA", "AMD", "TSM", "MU"],
    "defence_funding": ["LMT", "RTX", "NOC", "GD", "PLTR", "DRO.AX", "EOS.AX"],
    "quantum_computing": ["IONQ", "RGTI", "QBTS", "QUBT", "IBM"],
    "critical_minerals": ["MP", "LYC.AX", "ILU.AX", "ARU.AX", "PLS.AX"],
    "nuclear_policy": ["CCJ", "UEC", "OKLO", "SMR", "PDN.AX", "BOE.AX"],
    "rates_policy": ["CBA.AX", "NAB.AX", "WBC.AX", "ANZ.AX", "MQG.AX"],
}

# The five directness buckets and the score each contributes (0 to 10).
DIRECTNESS_SCORES = {
    "direct_named": 10,
    "direct_beneficiary": 7,
    "sympathy_beneficiary": 4,
    "sector_watch": 2,
    "ignore": 0,
}


# ---------------------------------------------------------------------------
# 7. Scoring weights and label thresholds
# ---------------------------------------------------------------------------
# Sub-scores are each 0 to 10. The weighted blend below is scaled to 0 to 100
# to give overall_watch_score. chase_risk is handled as a separate penalty.
SCORE_WEIGHTS = {
    "news_urgency":    0.25,
    "theme_relevance": 0.15,
    "directness":      0.30,
    "liquidity":       0.10,
    "price_reaction":  0.20,
}
# How hard a high chase-risk drags the overall score down (points per risk point).
CHASE_RISK_PENALTY_PER_POINT = 3.0

# Thresholds used when turning numbers into the watch-only labels.
LABELS = {
    "high_priority_min_score": 70,   # overall score for "High priority watch"
    "chase_risk_too_high": 7,        # chase risk at/above this -> "Too speculative"
    "liquidity_too_low": 3,          # liquidity at/below this -> "Too speculative"
}

# The only labels the scanner is allowed to emit. No "buy" or "sell" anywhere.
WATCH_LABELS = [
    "High priority watch",
    "Direct beneficiary",
    "Sympathy watch",
    "Too speculative",
    "Ignore",
]


# ---------------------------------------------------------------------------
# 8. Liquidity / market-cap / spread filters
# ---------------------------------------------------------------------------
# Market caps are compared in USD. ASX (AUD) caps are converted with a rough
# static rate; refine it or pull a live rate if you need precision.
AUD_TO_USD = float(os.getenv("AUD_TO_USD", "0.66"))

FILTERS = {
    "min_market_cap_usd": 300_000_000,   # below this is "microcap"
    "min_avg_volume": 200_000,           # shares per day (20-day average)
    "max_spread_pct": 1.5,               # max bid-ask spread percent, if known
    "microcap_market_cap_usd": 300_000_000,
}


# ---------------------------------------------------------------------------
# 9. Benchmarks for backtesting
# ---------------------------------------------------------------------------
# Forward returns of each signalled ticker are compared against these.
# yfinance uses "^AXJO" for the S&P/ASX 200 index; STW.AX and VAS.AX are ETFs.
BENCHMARKS = {
    "US":  ["SPY", "QQQ", "SOXX"],
    "ASX": ["^AXJO", "STW.AX", "VAS.AX"],
}
# Forward windows (trading days) measured in the backtest.
BACKTEST_HORIZONS = [1, 3, 5]


# ---------------------------------------------------------------------------
# 10. News sources (US + ASX)
# ---------------------------------------------------------------------------
# Each source: name, url, authority (2 official, 1 newswire), market tag.
#
# HONEST NOTES on ASX sources:
#   - The ASX company-announcements platform and trading-halt notices do not
#     offer a clean, stable public RSS feed. The entries below use Google News
#     queries scoped to asx.com.au plus Australian financial press, which is
#     the reliable free approximation. If you obtain a paid ASX announcements
#     feed (for example via Market Index, Sharesight, or a broker API), add it
#     here and it will flow through the rest of the scanner unchanged.
#   - Company investor-relations pages are mostly HTML, not RSS. Add any that
#     DO publish a feed; otherwise treat IR monitoring as a paid-data upgrade.
SOURCES = [
    # --- US / global ---
    {"name": "White House", "url": "https://www.whitehouse.gov/feed/", "authority": 2, "market": "US"},
    {"name": "CNBC Top News", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "authority": 1, "market": "US"},
    {"name": "CNBC Technology", "url": "https://www.cnbc.com/id/19854910/device/rss/rss.html", "authority": 1, "market": "US"},
    {"name": "WSJ Markets", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "authority": 1, "market": "US"},
    {"name": "Reuters (via Google News)", "url": "https://news.google.com/rss/search?q=when:1d+(semiconductor+OR+tariff+OR+export+controls+OR+rare+earth)+site:reuters.com&hl=en-US&gl=US&ceid=US:en", "authority": 1, "market": "US"},
    {"name": "Trump market comments (via Google News)", "url": "https://news.google.com/rss/search?q=when:1d+Trump+(chips+OR+tariff+OR+semiconductor+OR+Nvidia+OR+export+OR+rare+earth)&hl=en-US&gl=US&ceid=US:en", "authority": 1, "market": "US"},

    # --- ASX / Australia ---
    {"name": "ASX announcements (via Google News)", "url": "https://news.google.com/rss/search?q=when:1d+site:asx.com.au+announcement&hl=en-AU&gl=AU&ceid=AU:en", "authority": 1, "market": "ASX"},
    {"name": "ASX trading halts (via Google News)", "url": "https://news.google.com/rss/search?q=when:1d+ASX+%22trading+halt%22&hl=en-AU&gl=AU&ceid=AU:en", "authority": 1, "market": "ASX"},
    {"name": "AFR / ASX markets (via Google News)", "url": "https://news.google.com/rss/search?q=when:1d+(ASX+OR+%22Reserve+Bank%22+OR+lithium+OR+uranium+OR+%22iron+ore%22)+(Australia+OR+ASX)&hl=en-AU&gl=AU&ceid=AU:en", "authority": 1, "market": "ASX"},
    {"name": "ABC Business (Australia)", "url": "https://www.abc.net.au/news/feed/51120/rss.xml", "authority": 1, "market": "ASX"},
]

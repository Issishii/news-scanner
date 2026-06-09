# Market Event Scanner (US + ASX aware)

A Python scanner that watches US and Australian market news for politically and
policy driven, market moving events, then ranks which tickers deserve your
attention and why. It confirms with live price and volume, filters out names
you could not sensibly act on, and logs every signal so you can backtest how
its calls actually played out.

This is a research and monitoring tool. It is deliberately NOT a trading bot.
It never says buy or sell. The strongest thing it ever says is "High priority
watch". Every alert ends with a reminder to confirm against the primary source.

## What changed from the original news bot

1. Your original fixed watchlist is kept and always treated as first class.
2. A THEME_UNIVERSE maps ten themes to tickers: quantum, semiconductors, AI
   infrastructure, defence, rare earths, uranium and nuclear, lithium and
   battery metals, ASX banks and rates, ASX mining and resources, and ASX tech.
3. ASX tickers are included using the ".AX" format that yfinance expects.
4. Every relevant ticker gets a directness label: direct named, direct
   beneficiary, sympathy beneficiary, sector watch, or ignore.
5. Live price and volume confirmation via yfinance, behind a provider
   interface so you can drop in a paid data API later.
6. Liquidity filters: minimum market cap, minimum average volume, maximum
   spread when known, and microcaps are ignored unless you explicitly enable
   them.
7. Seven scores per ticker: news urgency, theme relevance, directness,
   liquidity, price reaction, chase risk, and a blended overall watch score.
8. Watch only labels. The bot can never emit a buy or sell instruction; this is
   enforced by a guard that runs on every outgoing message.
9. ASX sources added (announcements, trading halts, Australian financial news).
10. A backtester that stores every signal and later compares 1, 3, and 5 day
    forward returns against benchmarks (SPY, QQQ, SOXX for US; the ASX 200
    index plus STW.AX and VAS.AX for ASX names).

## Project layout

1. `bot.py` is the main loop: fetch, dedup, analyse, score, log, alert.
2. `config.py` holds all data and settings: watchlist, ticker registry,
   THEME_UNIVERSE, theme keywords, event rules, directness mappings, scoring
   weights, filters, benchmarks, and sources.
3. `classifier.py` is the analytical core: named tickers, event types, themes,
   directness classification, and the two text based scores.
4. `marketdata.py` is the price and volume layer with a provider interface
   (YFinanceProvider now, a PaidApiProvider stub for later).
5. `filters.py` applies the liquidity, market cap, and spread filters.
6. `scoring.py` computes the seven scores and maps them to a watch label.
7. `storage.py` is the SQLite store: article dedup plus the signal log.
8. `alerts.py` formats messages and sends to Telegram and Discord, with the
   no buy or sell guard.
9. `sources.py` fetches and normalises the RSS feeds.
10. `backtest.py` evaluates logged signals against benchmarks.
11. `test_scanner.py` is an offline test suite that needs no network.

## Setup

You need Python 3.9 or newer.

    cd news_bot
    python -m venv venv
    source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    cp .env.example .env               # then edit .env

Telegram and Discord setup steps are in `.env.example`. You can run with no
credentials at all; alerts then print to the console, which is the easiest way
to watch it work before wiring up a channel.

## Running

    python test_scanner.py     # offline sanity check, no network needed
    python bot.py              # start the scanner
    python backtest.py         # evaluate signals once some are a few days old

Press Ctrl+C to stop the scanner cleanly.

## The seven scores

Each sub score is 0 to 10.

1. news_urgency_score: how market moving the news itself is (event severity,
   source authority, action language such as "imposes" or "signs", and any
   reference to the administration or central bank).
2. theme_relevance_score: how strongly the news maps onto the tracked themes.
3. directness_score: from the directness label (direct named is highest, sector
   watch lowest).
4. liquidity_score: from average volume and market cap on a log scale.
5. price_reaction_score: is the market actually reacting, measured by the price
   move backed by above average volume.
6. chase_risk_score: a risk score, higher is worse. It rises when a name has
   already run a long way on the news, with extra weight for sympathy plays and
   microcaps, because those tend to spike and fade.

overall_watch_score (0 to 100) is a weighted blend of the five positive sub
scores minus a chase risk penalty. The weights live in `SCORE_WEIGHTS` in
config.

## The five labels

The scanner only ever emits one of these:

1. High priority watch: a direct name or direct beneficiary with a high overall
   score and acceptable chase risk.
2. Direct beneficiary: a direct link, but not strong enough for high priority.
3. Sympathy watch: a peer likely to move in sympathy with a direct name.
4. Too speculative: the move has already run (high chase risk), or the name is
   an illiquid microcap, or liquidity is too thin to act on sensibly.
5. Ignore: only a broad sector touch with no concrete anchor, or not relevant.

## Directness, explained

1. direct_named: the company name or ticker is in the text.
2. direct_beneficiary: the company is not named, but it is the primary subject
   of the policy. Example: an export controls headline makes Nvidia and AMD
   direct beneficiaries even when unnamed, because they are the primary AI chip
   exporters. This mapping lives in `EVENT_PRIMARY_TICKERS`.
3. sympathy_beneficiary: a peer in the same theme as a direct name. Example:
   when Intel is named in a chips funding story, other semiconductor names
   become sympathy watches.
4. sector_watch: only broad theme keywords matched, with no concrete anchor.
5. ignore: nothing relevant.

## Filters

Set in `FILTERS` in config. Defaults: minimum market cap 300 million USD,
minimum average daily volume 200,000 shares, maximum spread 1.5 percent when
known. ASX market caps are converted to USD using `AUD_TO_USD` for comparison.
Microcaps below the cap floor are ignored unless `ALLOW_MICROCAPS=1`. If a data
field is unknown the relevant check is skipped rather than failing the ticker,
so the scanner still works in news only mode.

## Backtesting

Every scored ticker is written to the `signals` table with a timestamp, the
linked ticker, all scores, and the reference price. Once signals are a few days
old, `python backtest.py` measures each ticker's 1, 3, and 5 day forward return
from the signal price and compares it to the relevant benchmark basket. It
reports average excess return grouped by watch label, so you can see which
label and directness types are worth your attention. This is measurement only.
It does not place trades and it does not recommend any.

## Environment variables

| Variable                 | Default     | Purpose                                  |
|--------------------------|-------------|------------------------------------------|
| TELEGRAM_BOT_TOKEN       |             | Telegram bot token                       |
| TELEGRAM_CHAT_ID         |             | Telegram chat or channel id              |
| DISCORD_WEBHOOK_URL      |             | Discord channel webhook                  |
| POLL_INTERVAL_SECONDS    | 120         | Seconds between polls (60 to 300)        |
| MIN_WATCH_SCORE_TO_ALERT | 45          | Lowest overall score that alerts         |
| ENABLE_PRICE_CONFIRMATION| 1           | Live price/volume on (1) or off (0)      |
| ALLOW_MICROCAPS          | 0           | Include illiquid microcaps if 1          |
| AUD_TO_USD               | 0.66        | Rough rate for ASX market cap comparison |
| DATABASE_PATH            | scanner.db  | SQLite file for dedup and signals        |

## Tuning the noise level

1. To get fewer alerts, raise `MIN_WATCH_SCORE_TO_ALERT`.
2. To surface fewer sympathy names per story, lower `MAX_TICKERS_PER_ARTICLE`
   in `bot.py` or reduce the directness weight in `SCORE_WEIGHTS`.
3. To change which names count as direct beneficiaries of a policy, edit
   `EVENT_PRIMARY_TICKERS` in config.

## Upgrading to a paid data API

`marketdata.py` defines `MarketDataProvider` with a single `get_snapshot`
method. `YFinanceProvider` is the free default. To use a paid feed (for example
Polygon, Finnhub, EODHD, or a broker API), implement
`PaidApiProvider.get_snapshot` to map their response onto the `MarketData`
fields, then set `ACTIVE_PROVIDER` to your provider. Nothing else needs to
change.

## Honest limitations

1. yfinance is free but unofficial and rate limited. It is fine for this use
   case but a paid feed is steadier for heavy or intraday use.
2. Reuters retired most free public RSS, so a Google News query scoped to
   reuters.com is used as a stand in. Swap in a paid feed if you have one.
3. The ASX announcements and trading halt platforms do not offer a clean public
   RSS feed. The ASX sources use Google News queries scoped to asx.com.au and
   Australian financial press, which is the reliable free approximation. A paid
   ASX announcements feed or broker API plugs straight into `SOURCES`.
4. Company investor relations pages are mostly HTML, not RSS. Add any that do
   publish a feed; otherwise treat IR monitoring as a paid data upgrade.
5. Listed companies get acquired or delisted. The thematic ticker lists are a
   starting point to verify, not gospel. Altium (ALU.AX), for instance, was
   removed after its 2024 acquisition and is deliberately excluded.
6. This tool surfaces and ranks news for your own research. It is not financial
   advice, it does not place trades, and it never tells you to buy or sell.
   Always confirm an alert against the primary source before acting.

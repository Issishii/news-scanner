"""
classifier.py
=============

The analytical core. Given a news headline plus summary it works out:

  1. Which tracked companies are explicitly NAMED.
  2. Which policy EVENT types apply.
  3. Which THEMES are in play.
  4. A DIRECTNESS label for every relevant ticker:
        direct_named         - the company is named in the text
        direct_beneficiary   - not named, but the primary subject of the policy
        sympathy_beneficiary - a peer that tends to move with a direct name
        sector_watch         - only broad theme keywords, no concrete anchor
        ignore               - not relevant
  5. A news_urgency_score (1 to 10) and a theme_relevance_score (0 to 10).

This module is pure standard library, so it runs and tests with no network.
Live price/volume confirmation and the rest of the scoring live in
marketdata.py and scoring.py.
"""

import re
from dataclasses import dataclass, field

import config


# ---------------------------------------------------------------------------
# Build a reverse index: ticker -> set of themes it belongs to.
# ---------------------------------------------------------------------------
TICKER_THEMES = {}
for _theme, _members in config.THEME_UNIVERSE.items():
    for _m in _members:
        TICKER_THEMES.setdefault(_m, set()).add(_theme)


@dataclass
class TickerClassification:
    ticker: str
    directness: str        # one of the five buckets above
    market: str            # "US" or "ASX"


@dataclass
class ScanResult:
    named_tickers: list = field(default_factory=list)
    events: list = field(default_factory=list)
    themes: list = field(default_factory=list)
    classifications: list = field(default_factory=list)  # TickerClassification
    news_urgency_score: int = 0
    theme_relevance_score: int = 0
    reasons: list = field(default_factory=list)

    @property
    def is_relevant(self) -> bool:
        # Relevant if we have at least one ticker that is more than a passive
        # sector watch, OR a clearly named ticker.
        return any(
            c.directness in ("direct_named", "direct_beneficiary", "sympathy_beneficiary")
            for c in self.classifications
        )


# ---------------------------------------------------------------------------
# Text matching helpers
# ---------------------------------------------------------------------------
def _contains_phrase(text_lower: str, phrase: str) -> bool:
    phrase = phrase.lower()
    if " " in phrase:
        return phrase in text_lower
    return re.search(r"\b" + re.escape(phrase) + r"\b", text_lower) is not None


def _any_phrase(text_lower: str, phrases) -> bool:
    return any(_contains_phrase(text_lower, p) for p in phrases)


# ---------------------------------------------------------------------------
# Step 1: detect explicitly named companies
# ---------------------------------------------------------------------------
def detect_companies(text: str) -> list:
    """
    Return tickers whose company NAME or ticker symbol appears in the text.
    Name matches are reliable. Bare ticker matches require the uppercase form
    (cashtag $XXX or an isolated uppercase token) to avoid false positives on
    short symbols like MU or GD.
    """
    found = set()
    text_lower = text.lower()

    for ticker, meta in config.TICKER_META.items():
        base = ticker.split(".")[0]  # "BHP.AX" -> "BHP"

        if _any_phrase(text_lower, meta["names"]):
            found.add(ticker)
            continue
        if re.search(r"\$" + re.escape(base) + r"\b", text, re.IGNORECASE):
            found.add(ticker)
            continue
        # Isolated uppercase token in the ORIGINAL text (case sensitive).
        if re.search(r"\b" + re.escape(base) + r"\b", text):
            found.add(ticker)

    return sorted(found)


# ---------------------------------------------------------------------------
# Step 2: classify policy event types
# ---------------------------------------------------------------------------
def classify_events(text: str) -> list:
    text_lower = text.lower()
    return [ev for ev, rule in config.EVENT_RULES.items()
            if _any_phrase(text_lower, rule["terms"])]


# ---------------------------------------------------------------------------
# Step 3: detect themes (keywords + themes of any concrete ticker)
# ---------------------------------------------------------------------------
def detect_themes(text: str, concrete_tickers) -> set:
    text_lower = text.lower()
    themes = set()
    for theme, kws in config.THEME_KEYWORDS.items():
        if _any_phrase(text_lower, kws):
            themes.add(theme)
    for t in concrete_tickers:
        themes |= TICKER_THEMES.get(t, set())
    return themes


# ---------------------------------------------------------------------------
# Step 4: directness classification (the heart of the upgrade)
# ---------------------------------------------------------------------------
def classify_directness(named, events, text):
    """
    Return a dict {ticker: directness_label} and the set of themes in play.

    Order of precedence (a ticker keeps its strongest label):
      direct_named > direct_beneficiary > sympathy_beneficiary > sector_watch
    """
    classifications = {}

    # direct_named: explicitly in the text.
    for t in named:
        classifications[t] = "direct_named"

    # direct_beneficiary: primary subject of a matched policy event.
    for ev in events:
        for t in config.EVENT_PRIMARY_TICKERS.get(ev, []):
            classifications.setdefault(t, "direct_beneficiary")

    # Themes are driven by keywords plus the themes of any concrete ticker.
    concrete = list(classifications.keys())
    themes = detect_themes(text, concrete)

    # A theme is "anchored" if it contains a direct (named or beneficiary) name.
    anchored = set()
    for theme, members in config.THEME_UNIVERSE.items():
        if theme in themes and any(
            classifications.get(m) in ("direct_named", "direct_beneficiary")
            for m in members
        ):
            anchored.add(theme)

    # sympathy_beneficiary: peers inside an anchored theme.
    for theme in anchored:
        for m in config.THEME_UNIVERSE[theme]:
            classifications.setdefault(m, "sympathy_beneficiary")

    # sector_watch: members of a detected-but-unanchored theme.
    for theme in themes - anchored:
        for m in config.THEME_UNIVERSE[theme]:
            classifications.setdefault(m, "sector_watch")

    return classifications, themes


# ---------------------------------------------------------------------------
# Step 5: scores that need only text
# ---------------------------------------------------------------------------
def score_news_urgency(text, named, events, source_authority=0) -> int:
    text_lower = text.lower()
    score = sum(config.EVENT_RULES[ev]["weight"] for ev in events)
    score += source_authority
    if _any_phrase(text_lower, config.ACTION_TERMS):
        score += 1
    if _any_phrase(text_lower, config.ADMIN_TERMS):
        score += 1
    if len(named) >= 2:
        score += 1
    return max(1, min(10, score))


def score_theme_relevance(themes, classifications) -> int:
    if not themes:
        return 0
    anchored = sum(
        1 for theme in themes
        if any(classifications.get(m) in ("direct_named", "direct_beneficiary")
               for m in config.THEME_UNIVERSE[theme])
    )
    score = 2 * len(themes) + 2 * anchored
    if any(v == "direct_named" for v in classifications.values()):
        score += 2
    return max(1, min(10, score))


# ---------------------------------------------------------------------------
# Step 6: explanations
# ---------------------------------------------------------------------------
def explain(events, themes, classifications) -> list:
    reasons = []
    for ev in events:
        note = config.EVENT_IMPACT_NOTES.get(ev)
        if note:
            reasons.append(f"{ev.replace('_', ' ').title()}: {note}")
    if themes:
        reasons.append("Themes in play: " + ", ".join(sorted(t.replace('_', ' ') for t in themes)) + ".")
    return reasons


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def analyze(title: str, summary: str = "", source_authority: int = 0) -> ScanResult:
    # Repeat the title once so headline keywords carry slightly more weight.
    text = f"{title}. {title}. {summary}".strip()

    named = detect_companies(text)
    events = classify_events(text)
    classifications, themes = classify_directness(named, events, text)

    urgency = score_news_urgency(text, named, events, source_authority)
    theme_rel = score_theme_relevance(themes, classifications)

    classification_objs = [
        TickerClassification(
            ticker=t,
            directness=label,
            market=config.TICKER_META.get(t, {}).get("market", "US"),
        )
        for t, label in classifications.items()
    ]

    return ScanResult(
        named_tickers=named,
        events=events,
        themes=sorted(themes),
        classifications=classification_objs,
        news_urgency_score=urgency,
        theme_relevance_score=theme_rel,
        reasons=explain(events, themes, classifications),
    )

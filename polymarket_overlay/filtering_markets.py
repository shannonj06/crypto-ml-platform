# ---------------------------------------------------------------------------
# Fit markets to the pricing algo
# ---------------------------------------------------------------------------
# The Monte Carlo engine (Models/monte_carlo.price_question) can only quote a
# market it can express as a question_spec: a known asset (btc/eth/sol), a
# supported type (terminal/touch above/below, or a range), an absolute strike,
# and a horizon in days. Everything below turns a raw Polymarket market into
# exactly that — or drops it. When in doubt we DROP: a market we can't parse
# cleanly is a mispricing waiting to happen, not an opportunity.

# Canonical asset per keyword. Whole-word matched (see _CRYPTO_RE) so "sol"/"eth"
# don't fire on substrings.
import datetime
import json
import re

import pandas as pd
import requests

from polymarket_overlay.poly_data import _CRYPTO_RE, find_crypto_events, get_midpoint, get_yes_token_id, iter_tradeable_markets, parse_field


_ASSET_CANON = {
    "bitcoin": "btc", "btc": "btc",
    "ethereum": "eth", "eth": "eth",
    "solana": "sol", "sol": "sol",
}

# Downside barrier verbs. Each says two things at once: the direction is DOWN,
# and the price only has to trade through the level to resolve YES. They belong
# in both lists below, so they live in one tuple — the original bug was exactly
# these two lists drifting apart, with "dip" listed as a direction but not as a
# barrier, which priced every "will X dip to $Y" market as a settlement
# question and understated it by roughly half (a path can dip and recover).
_DOWN_BARRIER_WORDS = ("dip", "drop", "fall", "sink", "plunge", "crash", "slide",
                       "as low as", "decline to")

# Words that pin down the shape of the question.
_BELOW_WORDS = ("below", "under", "less than", "beneath", "<") + _DOWN_BARRIER_WORDS

# Barrier words — the event happens if the price EVER trades through the level,
# not just where it finishes.
_TOUCH_WORDS = ("reach", "hit", "touch", "surpass", "top", "climb to", "get to",
                "all-time high", "ath", "as high as", "anytime") + _DOWN_BARRIER_WORDS

# Phrases that pin the question to the SETTLEMENT price, which beats a barrier
# word: "close below $60k", "be above $1,900 on Aug 15".
_TERMINAL_WORDS = ("close", "closes", "closing", "settle", "end of", "at the end")
_ON_DATE_RE = re.compile(
    r"\bon\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}/\d{1,2}|the\s+\d{1,2})"
)

# ...unless the question says outright that any moment counts.
_ANYTIME_WORDS = ("anytime", "any time", "any point", "ever", "at any")

# A strike must carry a money marker: a leading $ or a k/m suffix. Bare numbers
# are rejected so day-of-month ("by July 31"), years ("in 2026"), and ranks
# don't get read as prices.
_PRICE_RE = re.compile(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmM])?")


def detect_asset(text):
    """Canonical asset ('btc'/'eth'/'sol') for a question, or None if it isn't
    one the engine models."""
    m = _CRYPTO_RE.search(text.lower())
    return _ASSET_CANON.get(m.group(1)) if m else None


def _extract_prices(text):
    """Pull dollar strikes out of free text. A token counts only if it carries a
    money marker ($ immediately before, or a k/m magnitude suffix)."""
    prices = []
    for m in _PRICE_RE.finditer(text):
        raw, suffix = m.group(1), m.group(2)
        has_dollar = text[: m.start(1)].rstrip().endswith("$")
        val = float(raw.replace(",", ""))
        if suffix in ("k", "K"):
            val *= 1_000
        elif suffix in ("m", "M"):
            val *= 1_000_000
        elif not has_dollar:
            continue  # bare number (day, year, rank) — not a strike
        prices.append(val)
    return prices


def classify_question(question):
    """
    Turn a market question into a monte_carlo question_spec, or None if it can't
    be priced. The returned dict is ready to hand straight to price_question().

    Examples
    --------
    "Will Bitcoin be above $150,000 on July 31?" -> terminal_above @ 150000
    "Will Ethereum reach $5,000 by August?"      -> touch_above   @ 5000
    "Will Solana dip below $120 this month?"     -> touch_below   @ 120
    "Will Bitcoin close below $60,000 on Aug 31?"-> terminal_below @ 60000
    "Will BTC finish between $90k and $110k?"    -> range 90000..110000

    Barrier vs settlement is decided in that order: an explicit "anytime" wins,
    then a settlement marker ("close", "on <date>"), then a barrier verb.
    """
    text = question.lower()
    prices = _extract_prices(text)
    is_below = any(w in text for w in _BELOW_WORDS)

    is_anytime = any(w in text for w in _ANYTIME_WORDS)
    is_terminal = any(w in text for w in _TERMINAL_WORDS) or bool(_ON_DATE_RE.search(text))
    is_barrier = is_anytime or (
        any(w in text for w in _TOUCH_WORDS) and not is_terminal
    )

    if "between" in text and len(prices) >= 2:
        lo, hi = sorted(prices)[:2]
        return {"type": "range", "low": lo, "high": hi}

    # A single, unambiguous strike is required for the directional types.
    distinct = sorted(set(prices))
    if len(distinct) != 1:
        return None  # zero strikes, or several — too ambiguous to price safely
    strike = distinct[0]

    if is_below:
        return {"type": "touch_below" if is_barrier else "terminal_below", "strike": strike}
    return {"type": "touch_above" if is_barrier else "terminal_above", "strike": strike}


def horizon_days(market, now=None):
    """
    Days until the market resolves, from its end date. None if missing or
    already past.

    Rounds to the nearest whole day rather than truncating. `timedelta.days`
    floors, so a market resolving in 3 days 23 hours came back as 3 — shaving
    real time off every horizon and quietly narrowing the simulated
    distribution. The Monte Carlo steps in whole days, so a round is the
    closest honest answer.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    end_raw = market.get("endDate") or market.get("endDateIso")
    if not end_raw:
        return None
    end = pd.to_datetime(end_raw, utc=True, errors="coerce")
    if pd.isna(end):
        return None
    exact = (end.to_pydatetime() - now).total_seconds() / 86_400.0
    if exact <= 0:
        return None
    return max(1, int(round(exact)))


def is_binary_yes_no(market):
    """The engine prices a single YES/NO event. Multi-outcome markets don't map."""
    try:
        outcomes = [o.lower() for o in parse_field(market["outcomes"])]
    except (KeyError, TypeError, json.JSONDecodeError):
        return False
    return sorted(outcomes) == ["no", "yes"]


def _num(market, *keys):
    """First present numeric field among keys (volume/liquidity live under
    varying names across the feed)."""
    for k in keys:
        v = market.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return 0.0


def filter_markets_for_algo(
    events,
    min_horizon=1,
    max_horizon=30,
    price_band=(0.02, 0.98),
    # A book with no depth has no price. Empty Polymarket books sit near a 0.50
    # midpoint, which reads as a coin flip and manufactures an enormous edge
    # against any confident model number. Floor it. Pass 0.0 to see everything.
    min_liquidity=500.0,
    spot=None,
    now=None,
    with_rejects=False,
):
    """
    Reduce raw Polymarket events to the subset the pricing algo can actually
    trade, normalized into one row per market.

    A market is kept only if ALL of these hold:
      * order-book live and accepting orders (is_tradeable)
      * binary YES/NO (is_binary_yes_no)
      * about btc / eth / sol (detect_asset)
      * question parses to a supported spec (classify_question)
      * resolves in [min_horizon, max_horizon] days
      * has a live YES midpoint inside `price_band` (a 0.00/1.00 book is dead
        or already decided; extremes also can't clear costs)
      * liquidity >= min_liquidity
      * (optional) strike within 0.1x..10x of `spot[asset]` — drops absurd parses

    Parameters
    ----------
    spot : optional {asset: price} for a strike sanity check (e.g. from
           monte_carlo._current_price). Skipped if None.
    with_rejects : also return a DataFrame of dropped markets + reasons.

    Returns
    -------
    DataFrame with columns ready for the pipeline:
        asset, q_type, strike, low, high, horizon, market_prob, spec,
        yes_token_id, question, event, end_date, liquidity, volume
    `market_prob` is the column trading_signals expects; `spec` is the dict to
    pass to monte_carlo.price_question(asset, spec, horizon).
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    lo_band, hi_band = price_band
    rows, rejects = [], []

    def drop(event, market, reason):
        if with_rejects:
            rejects.append({
                "event": event.get("title", ""),
                "question": market.get("question", ""),
                "reason": reason,
            })

    for event, market in iter_tradeable_markets(events):
        q = market.get("question", "") or ""

        if not is_binary_yes_no(market):
            drop(event, market, "not binary yes/no")
            continue

        asset = detect_asset(q + " " + str(event.get("title", "")))
        if asset is None:
            drop(event, market, "no modelled asset")
            continue

        spec = classify_question(q)
        if spec is None:
            drop(event, market, "unparseable question / ambiguous strike")
            continue

        h = horizon_days(market, now)
        if h is None or not (min_horizon <= h <= max_horizon):
            drop(event, market, f"horizon out of range ({h})")
            continue

        if spot is not None and asset in spot:
            strike = spec.get("strike", spec.get("high"))
            if strike is not None and not (0.1 * spot[asset] <= strike <= 10 * spot[asset]):
                drop(event, market, f"strike {strike:g} implausible vs spot {spot[asset]:g}")
                continue

        liq = _num(market, "liquidityNum", "liquidity", "liquidityClob")
        if liq < min_liquidity:
            drop(event, market, f"liquidity {liq:g} < {min_liquidity:g}")
            continue

        try:
            token_id = get_yes_token_id(market)
            mid = get_midpoint(token_id)
        except (ValueError, requests.RequestException):
            drop(event, market, "no YES token / midpoint fetch failed")
            continue
        if mid is None or not (lo_band <= mid <= hi_band):
            drop(event, market, f"midpoint {mid} outside band {price_band}")
            continue

        rows.append({
            "asset":        asset,
            "q_type":       spec["type"],
            "strike":       spec.get("strike"),
            "low":          spec.get("low"),
            "high":         spec.get("high"),
            "horizon":      h,
            "market_prob":  mid,
            "spec":         spec,
            "yes_token_id": token_id,
            "question":     q,
            "event":        event.get("title", ""),
            "end_date":     market.get("endDate") or market.get("endDateIso"),
            "liquidity":    liq,
            "volume":       _num(market, "volumeNum", "volume", "volume24hr"),
        })

    kept = pd.DataFrame(rows)
    if with_rejects:
        return kept, pd.DataFrame(rejects)
    return kept


if __name__ == "__main__":
    crypto_events = find_crypto_events()

    kept, rejects = filter_markets_for_algo(crypto_events, with_rejects=True)

    if kept.empty:
        print("No algo-ready crypto markets found.")
    else:
        cols = ["asset", "q_type", "strike", "horizon", "market_prob",
                "liquidity", "question"]
        print("=== Algo-ready markets (fit for monte_carlo.price_question) ===\n")
        print(kept[cols].to_string(index=False))

    if not rejects.empty:
        print(f"\n=== Dropped {len(rejects)} markets (reason counts) ===")
        print(rejects["reason"].value_counts().to_string())
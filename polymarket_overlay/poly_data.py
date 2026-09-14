import requests
import pandas as pd
import json
import re
from datetime import datetime, timezone

def fetch_active_events(limit=100, offset=0):
    url = "https://gamma-api.polymarket.com/events"
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        "offset": offset,
        "order": "volume24hr",
        "ascending": "false",
    }

    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()

CRYPTO_KEYWORDS = ["bitcoin", "btc", "ethereum", "eth", "solana", "sol"]
# Whole-word match so short tickers ("sol", "eth") don't hit substrings like
# "dis-SOL-ved" or "wh-ETH-er". \b treats the slug's hyphens as boundaries too.
_CRYPTO_RE = re.compile(r"\b(" + "|".join(CRYPTO_KEYWORDS) + r")\b")

def iter_all_events(page_size=100, max_events=2000):
    """Page through the events feed (ordered by 24h volume) instead of only
    seeing the top page — crypto markets often sit well below the top 100."""
    offset = 0
    while offset < max_events:
        batch = fetch_active_events(limit=page_size, offset=offset)
        if not batch:
            break
        yield from batch
        offset += page_size

def find_crypto_events(max_events=2000):
    matches = []

    for event in iter_all_events(max_events=max_events):
        text = (
            str(event.get("title", "")) + " " +
            str(event.get("slug", ""))
        ).lower()

        if _CRYPTO_RE.search(text):
            matches.append(event)

    return matches
#you need the token id to perform any calculations
def parse_field(val):
    '''val is the market["outcome"]'''
    if isinstance(val, str):
        return json.loads(val) #converts to a list
    return val #otherwise

def get_yes_token_id(market):
    outcomes = parse_field(market["outcomes"])
    token_ids = parse_field(market["clobTokenIds"])
    for outcome, token_id in zip(outcomes, token_ids):
        if outcome.lower() == 'yes':
            return token_id
    raise ValueError("No YES token id found")

def is_tradeable(market):
    """A market only has a CLOB orderbook (and thus a midpoint) when it is
    order-book enabled, still accepting orders, and not closed/resolved.
    Note: the Gamma `active` flag means 'not deactivated', NOT 'trading'."""
    return (
        market.get("enableOrderBook")
        and market.get("acceptingOrders")
        and not market.get("closed")
    )

def iter_tradeable_markets(events):
    """Yield (event, market) for every market with a live orderbook."""
    for event in events:
        for market in event.get("markets", []):
            if is_tradeable(market):
                yield event, market

def get_midpoint(token_id):
    url = "https://clob.polymarket.com/midpoint"
    params = {"token_id": token_id}

    response = requests.get(url, params=params)
    if response.status_code == 404:
        # No orderbook for this token (closed/resolved or not CLOB-listed).
        return None
    response.raise_for_status()

    data = response.json()
    return float(data["mid"])


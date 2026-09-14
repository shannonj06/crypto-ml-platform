"""
Pins the market classifier's behaviour.

The bug these tests exist to prevent: "dip"/"drop"/"fall" were treated as
settlement questions instead of barrier questions, so every "will X dip to $Y"
market was priced at roughly half its true probability. The docstring said
touch_below; the code returned terminal_below. Nothing caught it.
"""
import datetime

import pytest

from polymarket_overlay.filtering_markets import classify_question, horizon_days


def _type(question):
    spec = classify_question(question)
    return spec["type"] if spec else None


# --- barrier questions: the price only has to trade through the level --------
@pytest.mark.parametrize(
    "question, expected",
    [
        ("Will Bitcoin dip to $62,500 in August?", "touch_below"),
        ("Will Solana dip to $50 August 10-16?", "touch_below"),
        ("Will Ethereum dip to $1,800 in August?", "touch_below"),
        ("Will Solana dip below $120 this month?", "touch_below"),
        ("Will Bitcoin drop to $60k this week?", "touch_below"),
        ("Will Ethereum fall to $1,500 in September?", "touch_below"),
        ("Will Bitcoin crash to $40,000 this year?", "touch_below"),
        ("Will Ethereum reach $2,000 in August?", "touch_above"),
        ("Will Bitcoin hit $100k by December?", "touch_above"),
        ("Will Solana climb to $200 this quarter?", "touch_above"),
    ],
)
def test_barrier_questions(question, expected):
    assert _type(question) == expected


# --- settlement questions: only where the price finishes counts --------------
@pytest.mark.parametrize(
    "question, expected",
    [
        ("Will Bitcoin be above $150,000 on July 31?", "terminal_above"),
        ("Will Ethereum be above $1,900 on August 15?", "terminal_above"),
        ("Will Bitcoin be below $60,000 on Aug 31?", "terminal_below"),
        ("Will Bitcoin close below $60,000 this month?", "terminal_below"),
        ("Will Ethereum close above $2,000 in August?", "terminal_above"),
        ("Will Solana settle below $70 on Sep 1?", "terminal_below"),
    ],
)
def test_settlement_questions(question, expected):
    assert _type(question) == expected


def test_settlement_marker_beats_barrier_verb():
    """'close below' is a settlement question even though 'below' is a barrier verb."""
    assert _type("Will Bitcoin close below $60,000 on Aug 31?") == "terminal_below"


def test_anytime_beats_settlement_marker():
    """An explicit 'anytime' outranks an 'on <date>' marker."""
    assert _type("Will Bitcoin trade above $70,000 anytime on Aug 15?") == "touch_above"


def test_range_questions_win_over_direction():
    spec = classify_question("Will BTC finish between $90k and $110k?")
    assert spec == {"type": "range", "low": 90_000.0, "high": 110_000.0}


@pytest.mark.parametrize(
    "question",
    [
        "Will Bitcoin go up in August?",              # no strike
        "Will Bitcoin be above $60,000 or $70,000?",  # ambiguous: two strikes
        "Will Bitcoin be ranked 1 by July 31?",       # bare number is not a price
    ],
)
def test_unpriceable_questions_are_dropped(question):
    assert classify_question(question) is None


# --- horizons ----------------------------------------------------------------
UTC = datetime.timezone.utc


def test_horizon_rounds_instead_of_truncating():
    """3 days 23 hours is 4 days, not 3. Truncation shaved time off every market."""
    now = datetime.datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
    market = {"endDate": "2026-08-14T23:00:00Z"}
    assert horizon_days(market, now=now) == 4


def test_horizon_never_below_one_day_while_live():
    now = datetime.datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
    assert horizon_days({"endDate": "2026-08-11T06:00:00Z"}, now=now) == 1


def test_horizon_is_none_once_past():
    now = datetime.datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
    assert horizon_days({"endDate": "2026-08-10T00:00:00Z"}, now=now) is None


def test_horizon_is_none_without_an_end_date():
    assert horizon_days({}) is None

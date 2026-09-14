from monte_carlo.monte_carlo import price_question
import yfinance as yf
import numpy as np
from datetime import date, timedelta

def produce_markets(yahoo_ticker, mc_asset, horizon=30):
    current_price = yf.Ticker(yahoo_ticker).history(period="1d")["Close"].iloc[-1]

    # Try strikes from 20% below to 20% above current price
    strike_multipliers = np.linspace(0.80, 1.20, 80)
    strikes = current_price * strike_multipliers

    passing_questions = []
    best_question = None
    best_difference = float("inf")

    for strike in strikes:
        question = {
            "type": "terminal_above",
            "strike": float(strike),
        }
        monte_carlo_prob = price_question(
            mc_asset,
            question,
            horizon=horizon,
        )
        result = {
            "question": question,
            "probability": monte_carlo_prob,
            "difference_from_50": abs(0.5 - monte_carlo_prob),
        }

        if 0.4 <= monte_carlo_prob <= 0.6:
            passing_questions.append(result)

        if result["difference_from_50"] < best_difference:
            best_difference = result["difference_from_50"]
            best_question = result

    return {
        "current_price": float(current_price),
        "best_question": best_question,
        "passing_questions": passing_questions,
    }

def _round_strike(strike):
    """Round a strike to a clean, human-readable level based on its magnitude."""
    strike = float(strike)
    if strike >= 10_000:
        step = 1_000
    elif strike >= 1_000:
        step = 100
    elif strike >= 100:
        step = 10
    elif strike >= 1:
        step = 1
    else:
        step = 0.01
    return round(strike / step) * step


def format_market_question(asset_name, horizon, question):
    """
    Turn a question spec into a human-readable market prompt, e.g.
    "Will BTC be above $65,000 on July 30, 2026?"

    Parameters
    ----------
    asset_name : ticker symbol, e.g. "BTC"
    horizon    : forecast horizon in days from today
    question   : dict with a 'type' key (see monte_carlo.price_question)
    """
    asset = asset_name.upper()
    target_date = date.today() + timedelta(days=horizon)
    # Windows strftime does not support %-d, so strip the leading zero manually.
    when = target_date.strftime("%B %d, %Y").replace(" 0", " ")

    q_type = question["type"]

    if q_type == "terminal_above":
        strike = _round_strike(question["strike"])
        return f"Will {asset} be above ${strike:,.0f} on {when}?"

    if q_type == "terminal_below":
        strike = _round_strike(question["strike"])
        return f"Will {asset} be below ${strike:,.0f} on {when}?"

    if q_type == "range":
        low = _round_strike(question["low"])
        high = _round_strike(question["high"])
        return f"Will {asset} be between ${low:,.0f} and ${high:,.0f} on {when}?"

    if q_type == "touch_above":
        barrier = _round_strike(question["barrier"])
        return f"Will {asset} reach ${barrier:,.0f} at any point before {when}?"

    if q_type == "touch_below":
        barrier = _round_strike(question["barrier"])
        return f"Will {asset} drop to ${barrier:,.0f} at any point before {when}?"

    if q_type == "max_drawdown":
        pct = round(question["threshold"] * 100)
        return f"Will {asset} draw down more than {pct}% at any point before {when}?"

    raise ValueError(f"Unknown question type: {q_type!r}")
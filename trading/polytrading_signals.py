from __future__ import annotations

import os
import warnings
from typing import Optional
from trading_config import Costs, Sizing, Signal
import numpy as np
import pandas as pd

THE_GATES = """
GATE 1 (paper trade): Paper-trade on live markets with fake money for a meaningful
        stretch before risking anything real.
GATE 2 (real capital): No real capital until calibration is validated (Section 4)
        AND paper trading confirms the edge survives live conditions and fees.
"""

# Flip these only when the corresponding evidence exists. They are checked by
# anything that would route an order to a live venue with real money.
CALIBRATION_VALIDATED = False    # set by Section 4 sign-off
PAPER_TRADING_PASSED  = False    # set after a meaningful live paper-trading stretch


def assert_clear_to_trade_real() -> None:
    """Hard stop. Raises unless both gates have been explicitly cleared."""
    if not (CALIBRATION_VALIDATED and PAPER_TRADING_PASSED):
        raise RuntimeError(
            "BLOCKED: real-capital gates not cleared.\n" + THE_GATES +
            f"\nCALIBRATION_VALIDATED={CALIBRATION_VALIDATED}, "
            f"PAPER_TRADING_PASSED={PAPER_TRADING_PASSED}"
        )


def edge(p_model: float, p_market: float) -> float:
    """Signed edge. >0 favours YES, <0 favours NO."""
    return p_model - p_market


def effective_cost(p_market: float, side: str, costs: Costs) -> float:
    """
    Per-share cost actually paid. You cross the spread (buy at the ask) and eat
    slippage on top. YES costs ~p_market; NO costs ~(1 - p_market).
    """
    base = p_market if side == "YES" else 1.0 - p_market
    return base + costs.half_spread + costs.slippage


def full_kelly(win_prob: float, cost_per_share: float) -> float:
    """
    Full-Kelly fraction for a binary contract bought at `cost_per_share` that
    pays $1 on a win. f* = (win_prob - cost) / (1 - cost). Clamped at 0.
    """
    if not (0.0 < cost_per_share < 1.0):
        return 0.0
    f = (win_prob - cost_per_share) / (1.0 - cost_per_share)
    return max(0.0, f)


def decide(p_model: float, p_market: float, tau: float,
           costs: Costs, sizing: Sizing) -> Signal:
    """
    Map a (model prob, market price) pair to an action.

    Acts only when the COST-ADJUSTED edge exceeds tau, then sizes with
    fractional Kelly against the price actually paid, capped at max_position.
    tau is the noise/uncertainty buffer on top of the modelled costs.
    """
    raw_edge = edge(p_model, p_market)
    side     = "YES" if raw_edge >= 0 else "NO"

    win_prob = p_model if side == "YES" else 1.0 - p_model
    eff_cost = effective_cost(p_market, side, costs)

    # Cost-adjusted edge: expected payoff per share minus what the share costs.
    net_edge = win_prob - eff_cost

    if net_edge <= tau:
        return Signal(None, raw_edge, net_edge, 0.0, p_market, eff_cost)

    f_full = full_kelly(win_prob, eff_cost)
    size   = min(sizing.kelly_fraction * f_full, sizing.max_position)
    if size <= 0.0:
        return Signal(None, raw_edge, net_edge, 0.0, p_market, eff_cost)

    return Signal(side, raw_edge, net_edge, size, p_market, eff_cost)


def trade_pnl(sig: Signal, outcome: int, stake_dollars: float, costs: Costs) -> float:
    """
    Realized P&L (in dollars) of a resolved position.

    Buy `shares = stake / eff_cost`; each pays $1 on a win, $0 otherwise. A
    resolution-risk haircut shaves expected payoff; fees are charged on notional.
    """
    if not sig.acts or stake_dollars <= 0:
        return 0.0
    shares = stake_dollars / sig.eff_cost
    win    = outcome if sig.side == "YES" else (1 - outcome)
    payoff = shares * win * (1.0 - costs.resolution_risk)
    fee    = costs.fee_rate * stake_dollars
    return payoff - stake_dollars - fee



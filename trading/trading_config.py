from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Costs:
    """
    All values in probability units (a contract pays $1 and is priced in [0, 1]),
    except fee_rate which is a fraction of notional staked.

    Edges die here first — keep these honest and, if anything, pessimistic.
    """
    fee_rate:        float = 0.00    # exchange fee, fraction of notional per trade
    half_spread:     float = 0.01    # half the bid-ask; you buy at the ask
    slippage:        float = 0.005   # extra adverse fill beyond the quoted ask
    resolution_risk: float = 0.01    # P(market mis-resolves / fails to pay) -> payoff haircut

COSTS = Costs()

@dataclass(frozen=True)
class Sizing:
    """Position sizing. NEVER full Kelly — quarter-Kelly is the default."""
    kelly_fraction:     float = 0.25   # fraction of full Kelly
    max_position:       float = 0.05   # cap per bet, fraction of bankroll
    max_total_exposure: float = 0.20   # cap on concurrent staked fraction (per resolution date)

SIZING = Sizing()

@dataclass(frozen=True)
class Signal:
    side:      Optional[str]   # "YES", "NO", or None (no action)
    edge:      float           # raw P_model - P_market
    net_edge:  float           # cost-adjusted edge actually used for the decision
    size:      float           # stake as a fraction of bankroll (post-cap)
    price:     float           # quoted market probability (mid)
    eff_cost:  float           # per-share cost actually paid on the chosen side

    @property
    def acts(self) -> bool:
        return self.side is not None and self.size > 0.0
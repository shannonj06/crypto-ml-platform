"""
engine.py — the one place the app asks "what does our model think?"

Two jobs:
  1. predict_asset(asset)      -> a plain-English price outlook for btc/eth/sol
  2. polymarket_signals()      -> for each relevant Polymarket market, what we
                                  predict, what the market says, and how much to bet

Everything reads the price history in Database/Crypto_ML_Dataset.csv and runs the
same block-bootstrap Monte Carlo you already wrote in monte_carlo/. It is kept
self-contained on purpose: no fragile cross-folder imports, so it runs the same
way from the API, a script, or a GitHub Action.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "Database" / "Crypto_ML_Dataset.csv"
ASSETS = ["btc", "eth", "sol"]

# Reuse the trade-sizing logic you already wrote (edge + fractional Kelly).
# It lives in trading/ and imports its config as a bare module, so put that
# folder on the path once, here, instead of scattering sys.path hacks around.
sys.path.insert(0, str(BASE_DIR))            # so polymarket_overlay.* resolves
sys.path.insert(0, str(BASE_DIR / "trading"))
from polytrading_signals import decide  # noqa: E402
from trading_config import COSTS, SIZING  # noqa: E402

# Monte Carlo knobs — same meaning as in monte_carlo/monte_carlo.py
N_SIMS = 20_000        # 20k paths -> results stable to ~0.5%
BLOCK_LEN = 20         # sample returns in ~1-month blocks (keeps vol clustering)
SEED = 42              # fixed so the same day always gives the same numbers
ANNUALIZATION = 365    # crypto trades every day


# ---------------------------------------------------------------------------
# Data + Monte Carlo core
# ---------------------------------------------------------------------------
def load_prices() -> pd.DataFrame:
    """Load the price history, newest last, indexed by date."""
    return (
        pd.read_csv(DATA_PATH, parse_dates=["date"])
        .sort_values("date")
        .drop_duplicates(subset="date")
        .set_index("date")
    )


def _closes(df: pd.DataFrame, asset: str) -> pd.Series:
    """Closing prices for one asset, with the trailing empty rows dropped."""
    return df[f"{asset}_close"].dropna()


def _log_returns(closes: pd.Series) -> np.ndarray:
    return np.log(closes / closes.shift(1)).dropna().to_numpy()


def _ewma_annual_vol(closes: pd.Series, lam: float = 0.94) -> float:
    """
    Forward volatility guess via EWMA (RiskMetrics lambda=0.94). Recent days
    count more than old ones. Returned annualized so it's easy to read.
    """
    r = np.log(closes / closes.shift(1)).dropna()
    variance = r.pow(2).ewm(alpha=1 - lam, adjust=False).mean()
    daily_vol = float(np.sqrt(variance.iloc[-1]))
    return daily_vol * np.sqrt(ANNUALIZATION)


def _bootstrap_return_paths(returns: np.ndarray, horizon: int,
                            rng: np.random.Generator) -> np.ndarray:
    """
    Draw n_sims fake futures by stitching together random chunks of real history.
    Sampling in blocks (not single days) keeps volatility clustering intact.
    Returns an (N_SIMS, horizon) array of daily log returns.
    (Same idea as monte_carlo._block_bootstrap_paths.)
    """
    n = len(returns)
    n_blocks = int(np.ceil(horizon / BLOCK_LEN))
    starts = rng.integers(0, n, size=(N_SIMS, n_blocks))
    offsets = np.arange(BLOCK_LEN)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n   # wrap around the end
    sampled = returns[idx.reshape(N_SIMS, -1)]
    return sampled[:, :horizon]


def simulate_price_paths(asset: str, df: pd.DataFrame, horizon: int):
    """
    Run the Monte Carlo for one asset and return (spot, price_paths, annual_vol).
    price_paths is (N_SIMS, horizon) of simulated prices.

    The raw bootstrap paths are rescaled so their volatility matches our EWMA
    forecast — this is the volatility-aware version from
    monte_carlo/connecting_monte_to_model.py, in one place.
    """
    closes = _closes(df, asset)
    spot = float(closes.iloc[-1])
    returns = _log_returns(closes)
    rng = np.random.default_rng(SEED)

    ret_paths = _bootstrap_return_paths(returns, horizon, rng)

    # Rescale so the paths' daily vol equals the EWMA forecast.
    annual_vol = _ewma_annual_vol(closes)
    target_daily = annual_vol / np.sqrt(ANNUALIZATION)
    sampled_daily = max(float(np.sqrt(np.mean(ret_paths ** 2))), 1e-8)
    ret_paths = ret_paths * (target_daily / sampled_daily)

    price_paths = spot * np.exp(np.cumsum(ret_paths, axis=1))
    return spot, price_paths, annual_vol


def probability_of(price_paths: np.ndarray, spot: float, question: dict) -> float:
    """
    Probability of a yes/no price question, measured across the simulated paths.
    Supported question types (same as monte_carlo):
        terminal_above / terminal_below : end price above/below a strike
        touch_above / touch_below       : ever crosses a barrier along the way
        range                           : ends between low and high
    """
    q = question["type"]
    terminal = price_paths[:, -1]
    # the classifier labels the price level "strike"; older specs use "barrier"
    level = question.get("strike", question.get("barrier"))
    if q == "terminal_above":
        hits = terminal > level
    elif q == "terminal_below":
        hits = terminal < level
    elif q == "touch_above":
        hits = price_paths.max(axis=1) > level
    elif q == "touch_below":
        hits = price_paths.min(axis=1) < level
    elif q == "range":
        hits = (terminal > question["low"]) & (terminal < question["high"])
    else:
        raise ValueError(f"Unknown question type: {q!r}")
    return float(hits.mean())


# ---------------------------------------------------------------------------
# Feature 1: price outlook for btc / eth / sol
# ---------------------------------------------------------------------------
def predict_asset(asset: str, horizon: int = 7, df: pd.DataFrame | None = None) -> dict:
    """
    A readable price outlook: where the price sits now, the likely range over the
    next `horizon` days, and a few move probabilities. This is what the every-3-days
    report and the /predictions endpoint are built from.
    """
    asset = asset.lower()
    if df is None:
        df = load_prices()
    spot, paths, annual_vol = simulate_price_paths(asset, df, horizon)
    terminal = paths[:, -1]

    def pct(q):
        return round(float(np.percentile(terminal, q)), 2)

    return {
        "asset": asset,
        "as_of": str(_closes(df, asset).index[-1].date()),
        "horizon_days": horizon,
        "spot": round(spot, 2),
        "forecast_annual_vol": round(float(annual_vol), 4),
        # likely range: 10th–90th percentile of where the price lands
        "low_p10": pct(10),
        "expected_p50": pct(50),
        "high_p90": pct(90),
        # a couple of headline probabilities
        "prob_up": round(float((terminal > spot).mean()), 3),
        "prob_up_5pct": round(float((terminal > spot * 1.05).mean()), 3),
        "prob_down_5pct": round(float((terminal < spot * 0.95).mean()), 3),
    }


def predict_all(horizon: int = 7) -> list[dict]:
    """Price outlook for every asset we model."""
    df = load_prices()
    return [predict_asset(a, horizon, df) for a in ASSETS]


# ---------------------------------------------------------------------------
# Feature 2: Polymarket signals (predict vs market + how much to bet)
# ---------------------------------------------------------------------------
def polymarket_signals(tau: float = 0.03, bankroll: float | None = None) -> list[dict]:
    """
    Find live Polymarket crypto markets we can price, run our Monte Carlo on each,
    and compare our probability to the market's. Where we have an edge, size the
    bet with your fractional-Kelly `decide()` logic.

    `tau` is the edge buffer (only act when the cost-adjusted edge clears it).
    `bankroll` (optional, in dollars) turns the suggested fraction into a dollar
    amount. Returns [] if Polymarket is unreachable or has no matching markets.
    """
    # Imported lazily so the price outlook works even with no internet.
    from polymarket_overlay.poly_data import find_crypto_events
    from polymarket_overlay.filtering_markets import filter_markets_for_algo

    df = load_prices()
    spot = {a: float(_closes(df, a).iloc[-1]) for a in ASSETS}

    try:
        events = find_crypto_events()
        markets = filter_markets_for_algo(events, spot=spot)
    except Exception as exc:  # network hiccup, API change, etc. — degrade gracefully
        return [{"error": f"could not load Polymarket markets: {exc}"}]

    if markets.empty:
        return []

    signals = []
    for m in markets.itertuples():
        _, paths, _ = simulate_price_paths(m.asset, df, int(m.horizon))
        p_model = probability_of(paths, spot[m.asset], m.spec)
        p_market = float(m.market_prob)

        sig = decide(p_model, p_market, tau, COSTS, SIZING)

        row = {
            "asset": m.asset,
            "question": m.question,
            "horizon_days": int(m.horizon),
            "our_probability": round(p_model, 3),
            "market_probability": round(p_market, 3),
            "edge": round(p_model - p_market, 3),
            "action": sig.side or "no bet",       # YES / NO / no bet
            "bet_fraction_of_bankroll": round(sig.size, 4),
        }
        if bankroll is not None:
            row["bet_dollars"] = round(sig.size * bankroll, 2)
        signals.append(row)

    # Strongest disagreements first.
    signals.sort(key=lambda r: abs(r["edge"]), reverse=True)
    return signals


if __name__ == "__main__":
    print("=== 7-day price outlook ===")
    for p in predict_all(horizon=7):
        print(
            f"{p['asset'].upper():4} spot ${p['spot']:,.0f}  "
            f"likely ${p['low_p10']:,.0f}–${p['high_p90']:,.0f} "
            f"(mid ${p['expected_p50']:,.0f})  "
            f"P(up)={p['prob_up']:.0%}"
        )

    print("\n=== Polymarket signals ===")
    sigs = polymarket_signals()
    if not sigs:
        print("no matching live markets right now")
    for s in sigs:
        print(s)

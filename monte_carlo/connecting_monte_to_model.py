#connect volatility forecasts to monte carlo pricing
import numpy as np
import pandas as pd
from Models.volatility_model import garch_forecast_single_window
from Models.feature_engineering import crypto_data
from monte_carlo.monte_carlo import _block_bootstrap_paths, _get_log_returns, DEFAULT_BLOCK_LEN, DEFAULT_N_SIMS

def forecast_volatility(asset, as_of=None, method='ewma', horizon=7, window=20):
    close = crypto_data[f"{asset}_close"].dropna()
    asset = asset.lower()
    method = method.lower()
    annualization = 365
    if as_of is not None:
        close = close.loc[:pd.Timestamp(as_of)]

    returns = np.log(close / close.shift(1)).dropna()

    if method == "ewma":
        lambda_ = 0.94

        variance = returns.pow(2).ewm(
            alpha=1 - lambda_,
            adjust=False
        ).mean()

        daily_vol = np.sqrt(variance.iloc[-1])

    elif method == "trailing":
        recent_returns = returns.tail(window)
        daily_vol = np.sqrt((recent_returns ** 2).mean())

    elif method == "parkinson":
        high = crypto_data[f"{asset}_high"].dropna()
        low = crypto_data[f"{asset}_low"].dropna()

        if as_of is not None:
            high = high.loc[:pd.Timestamp(as_of)]
            low = low.loc[:pd.Timestamp(as_of)]

        parkinson_var = (np.log(high / low) ** 2) / (4 * np.log(2))
        daily_vol = np.sqrt(parkinson_var.tail(window).mean())
    elif method == "garch":
        return garch_forecast_single_window(
            returns,
            horizon=horizon,
            annualization=annualization,
        )
    else:
        raise ValueError(
            "method must be 'ewma', 'trailing', 'trailing_30d', "
            "'parkinson', or 'garch'"
        )
    annual_vol = daily_vol * np.sqrt(annualization)
    return float(annual_vol)

def rescale_paths_to_vol(return_paths, annualized_vol, annualization=365):
    '''return paths is the bootstrap monte carlo paths
    annualized vol is the volatility generated from the prev func'''
    forecast_daily_vol = annualized_vol / np.sqrt(annualization)

    sampled_daily_vol = np.sqrt(np.mean(return_paths ** 2))
    sampled_daily_vol = max(sampled_daily_vol, 1e-8)

    scale = forecast_daily_vol / sampled_daily_vol
    adjusted_return_paths = return_paths * scale
    return adjusted_return_paths, scale

def returns_to_price_paths(asset, return_paths, as_of=None):
    """
    Convert simulated return paths into simulated price paths.
    return_paths:
        n_sims x horizon array of daily log returns
    returns:
        n_sims x horizon array of simulated prices
    """
    asset = asset.lower()
    close = crypto_data[f"{asset}_close"].dropna()

    if as_of is not None:
        close = close.loc[:pd.Timestamp(as_of)]

    current_price = close.iloc[-1]
    price_paths = current_price * np.exp(np.cumsum(return_paths, axis=1))
    return price_paths

def probability_from_paths(price_paths, question):
    """
    Calculate the probability of a betting question from simulated price paths.
    Supported question types:
    terminal_above:
        {"type": "terminal_above", "strike": 110000}

    terminal_below:
        {"type": "terminal_below", "strike": 95000}

    touch_above:
        {"type": "touch_above", "barrier": 120000}

    touch_below:
        {"type": "touch_below", "barrier": 90000}

    range:
        {"type": "range", "low": 95000, "high": 105000}

    max_drawdown:
        {"type": "max_drawdown", "threshold": 0.15}
    """
    q_type = question["type"]

    if q_type == "terminal_above":
        hits = price_paths[:, -1] > question["strike"]

    elif q_type == "terminal_below":
        hits = price_paths[:, -1] < question["strike"]

    elif q_type == "touch_above":
        hits = price_paths.max(axis=1) > question["barrier"]

    elif q_type == "touch_below":
        hits = price_paths.min(axis=1) < question["barrier"]

    elif q_type == "range":
        terminal_prices = price_paths[:, -1]
        hits = (
            (terminal_prices > question["low"])
            & (terminal_prices < question["high"])
        )

    elif q_type == "max_drawdown":
        running_max = np.maximum.accumulate(price_paths, axis=1)
        drawdowns = (running_max - price_paths) / running_max
        max_drawdowns = drawdowns.max(axis=1)
        hits = max_drawdowns > question["threshold"]

    else:
        raise ValueError(f"Unknown question type: {q_type}")

    probability = hits.mean()

    return float(probability)

if __name__ == "__main__":
    #0. get returns
    returns = _get_log_returns('btc')
    as_of = None
    horizon = 7
    n_sims =  DEFAULT_N_SIMS
    block_len = DEFAULT_BLOCK_LEN
    rng = np.random.default_rng(42)

    # 1. Get raw Monte Carlo bootstrap return paths
    ret_paths = _block_bootstrap_paths(
    returns,
    horizon,
    n_sims,
    block_len,
    rng,
)

# 2. Get annualized volatility forecast
    forecast_annual_vol = forecast_volatility(
    asset="btc",
    method="ewma",
    as_of=as_of,
    horizon=horizon,
)

# 3. Rescale the return paths
    adjusted_ret_paths, scale = rescale_paths_to_vol(
    ret_paths,
    forecast_annual_vol,
)

    # 4. Convert the vol-adjusted return paths into price paths
    price_paths = returns_to_price_paths("btc", adjusted_ret_paths, as_of=as_of)

    # 5. Anchor strikes on the current (as-of) price
    close = crypto_data["btc_close"].dropna()
    if as_of is not None:
        close = close.loc[:pd.Timestamp(as_of)]
    S0 = close.iloc[-1]

    questions = [
        ("P(terminal > +10%)",  {"type": "terminal_above", "strike":  S0 * 1.10}),
        ("P(terminal < -10%)",  {"type": "terminal_below", "strike":  S0 * 0.90}),
        ("P(range -5% to +5%)", {"type": "range",          "low": S0 * 0.95, "high": S0 * 1.05}),
        ("P(touch +20%)",       {"type": "touch_above",    "barrier": S0 * 1.20}),
        ("P(drawdown > 15%)",   {"type": "max_drawdown",   "threshold": 0.15}),
    ]

    # 6. Price each question off the vol-scaled paths
    print(f"BTC  S0={S0:,.0f}  horizon={horizon}d  "
          f"forecast_vol={forecast_annual_vol:.1%}  scale={scale:.3f}\n")
    for label, q in questions:
        p = probability_from_paths(price_paths, q)
        print(f"  {label:<22} {p:.4f}")
import pandas as pd
import numpy as np
from pathlib import Path

# --- Data source convention ---
# Prices   : Binance daily OHLCV candles, settled at 00:00 UTC (close = end of UTC day)
# Funding  : Binance perpetual 8-hour funding rate, last value of the calendar day
# Fear/Greed: alternative.me composite index, published daily
# Resolution: 1 calendar day; no timezone conversion needed downstream.

BASE_DIR = Path(__file__).resolve().parent.parent
path = BASE_DIR / "Database" / "Crypto_ML_Dataset.csv"

_raw = (
    pd.read_csv(path, parse_dates=["date"])
    .sort_values("date")
    .drop_duplicates(subset="date")
    .set_index("date")
)
assert _raw.index.is_unique, "Duplicate dates remain after dedup"

# Trim trailing rows where ALL price closes are NaN.
# These are pipeline-lag rows at the leading edge of time, not isolated gaps —
# interpolation would fabricate future prices, so we drop them instead.
_price_cols = [c for c in _raw.columns if c.endswith("_close")]
_raw = _raw.loc[: _raw[_price_cols].dropna(how="all").index[-1]]

# Forward-fill the 1–2 isolated NaN gaps in fear_greed / dominance / USD market-cap.
# These are smooth daily series; a 1-day carry-forward introduces negligible error.
crypto_data = _raw.ffill(limit=2)


def creating_feature_df(df):
    tickers = ["btc", "sol", "eth"]
    features = {}
    fg = df["fear_greed"]

    for ticker in tickers:
        close     = df[f"{ticker}_close"]
        log_close = np.log(close)

        # Log returns — additive across days, better-behaved for volatility work
        for n in [1, 3, 5, 7, 14, 20, 30, 60]:
            features[f"{ticker}_return_{n}d"] = log_close.diff(n)

        # Price / MA ratios (stationary)
        for w in [5, 10, 20, 50, 100]:
            ma = close.rolling(w).mean()
            features[f"{ticker}_MA{w}"] = close / ma

        features[f"{ticker}_30d_high_ratio"] = close / close.rolling(30).max() - 1
        features[f"{ticker}_90d_high_ratio"] = close / close.rolling(90).max() - 1
        features[f"{ticker}_30d_low_ratio"]  = close / close.rolling(30).min() - 1
        features[f"{ticker}_90d_low_ratio"]  = close / close.rolling(90).min() - 1

        # Volatility — rolling std of daily log returns
        daily_ret = log_close.diff()
        for w in [5, 10, 20, 30, 60]:
            features[f"{ticker}_volatility_{w}d"] = daily_ret.rolling(w).std()

        features[f"{ticker}_accel_5_20"] = features[f"{ticker}_return_5d"] - features[f"{ticker}_return_20d"]
        features[f"{ticker}_accel_1_5"]  = features[f"{ticker}_return_1d"]  - features[f"{ticker}_return_5d"]

        high        = df[f"{ticker}_high"]
        low         = df[f"{ticker}_low"]
        daily_range = (high - low) / close
        features[f"{ticker}_daily_range"] = daily_range
        features[f"{ticker}_range_ma5"]   = daily_range.rolling(5).mean()
        features[f"{ticker}_range_ma20"]  = daily_range.rolling(20).mean()
        features[f"{ticker}_range_ma60"]  = daily_range.rolling(60).mean()

        # Volume — raw level is non-stationary; keep only ratios and z-scores
        volume   = df[f"{ticker}_volume"]
        vol_ma5  = volume.rolling(5).mean()
        vol_ma20 = volume.rolling(20).mean()
        vol_ma60 = volume.rolling(60).mean()
        vol_std20 = volume.rolling(20).std()
        features[f"{ticker}_vol_ratio_1d"]       = volume / vol_ma5
        features[f"{ticker}_vol_ratio_5d"]        = vol_ma5  / vol_ma20
        features[f"{ticker}_vol_ratio_20d"]       = vol_ma20 / vol_ma60
        features[f"{ticker}_vol_volatility_5d"]   = volume.rolling(5).std()  / vol_ma5   # CV
        features[f"{ticker}_vol_volatility_20d"]  = volume.rolling(20).std() / vol_ma20  # CV
        features[f"{ticker}_vol_zscore"]          = (volume - vol_ma20) / vol_std20

        # Trades — raw count is non-stationary; keep ratios, momentum, z-score
        trades      = df[f"{ticker}_trades"]
        trade_ma5   = trades.rolling(5).mean()
        trade_ma20  = trades.rolling(20).mean()
        trade_ma60  = trades.rolling(60).mean()
        trade_std20 = trades.rolling(20).std()
        features[f"{ticker}_volume_per_trade"]   = volume / trades
        features[f"{ticker}_activity_ratio_5d"]  = trades / trade_ma5
        features[f"{ticker}_activity_ratio_20d"] = trades / trade_ma20
        features[f"{ticker}_activity_ratio_60d"] = trades / trade_ma60
        features[f"{ticker}_trade_momentum_1d"]  = np.log(trades).diff(1)
        features[f"{ticker}_trade_momentum_5d"]  = np.log(trades).diff(5)
        features[f"{ticker}_trade_momentum_20d"] = np.log(trades).diff(20)
        features[f"{ticker}_trade_zscore"]       = (trades - trade_ma20) / trade_std20

        # Funding rate — already a stationary percent; keep levels + derived stats
        funding    = df[f"{ticker}_funding_rate"]
        fund_ma5   = funding.rolling(5).mean()
        fund_ma20  = funding.rolling(20).mean()
        fund_ma60  = funding.rolling(60).mean()
        fund_std20 = funding.rolling(20).std()
        fund_std60 = funding.rolling(60).std()
        features[f"{ticker}_funding_ma5"]          = fund_ma5
        features[f"{ticker}_funding_ma20"]         = fund_ma20
        features[f"{ticker}_funding_ma60"]         = fund_ma60
        features[f"{ticker}_funding_change_1d"]    = funding.diff(1)
        features[f"{ticker}_funding_change_5d"]    = funding.diff(5)
        features[f"{ticker}_funding_change_20d"]   = funding.diff(20)
        features[f"{ticker}_funding_vol_20d"]      = fund_std20
        features[f"{ticker}_funding_zscore_20"]    = (funding - fund_ma20) / fund_std20
        features[f"{ticker}_funding_zscore_60"]    = (funding - fund_ma60) / fund_std60
        features[f"{ticker}_funding_gt_2std"]      = (funding > fund_ma20 + 2 * fund_std20).astype(int)
        features[f"{ticker}_funding_lt_minus2std"] = (funding < fund_ma20 - 2 * fund_std20).astype(int)
        features[f"{ticker}_funding_rate"]         = funding

        # Targets: log forward returns
        features[f"{ticker}_target_1d"]  = np.log(close.shift(-1)  / close)
        features[f"{ticker}_target_5d"]  = np.log(close.shift(-5)  / close)
        features[f"{ticker}_target_20d"] = np.log(close.shift(-20) / close)

    # Market cap — raw level is non-stationary; keep log returns and dominance ratios
    total_mc     = df["USD_total_market_cap"]
    log_total_mc = np.log(total_mc)
    mc_returns   = log_total_mc.diff()

    for n in [1, 5, 20, 60]:
        features[f"total_market_return_{n}d"] = log_total_mc.diff(n)
    features["total_market_vol_20d"] = mc_returns.rolling(20).std()
    features["total_market_vol_60d"] = mc_returns.rolling(60).std()
    mc_mean20 = mc_returns.rolling(20).mean()
    mc_std20  = mc_returns.rolling(20).std()
    features["total_market_zscore"]   = (mc_returns - mc_mean20) / mc_std20
    features["marketcap_change_5d"]   = log_total_mc.diff(5)
    features["marketcap_change_20d"]  = log_total_mc.diff(20)

    # Dominance (already a 0–1 ratio, stationary)
    for ticker in tickers:
        coin = ticker.lower()
        dom  = df[f"{coin}_market_cap"] / total_mc
        features[f"{coin}_computed_dominance"] = dom
        if coin in ("btc", "eth"):
            features[f"{coin}_dominance"]      = df[f"{coin}_dominance"]
            features[f"{coin}_dom_change_1d"]  = dom.diff(1)
            features[f"{coin}_dom_change_5d"]  = dom.diff(5)
            features[f"{coin}_dom_change_20d"] = dom.diff(20)
            dom_ma20 = dom.rolling(20).mean()
            features[f"{coin}_dom_ma20"]       = dom_ma20
            features[f"{coin}_dom_zscore"]     = (dom - dom_ma20) / dom.rolling(20).std()

    alt_share        = df["USD_altcoin_market_cap"] / df["USD_total_market_cap"]
    alt_volume_share = df["USD_altcoin_volume24h"]  / df["USD_total_volume24h"]
    features["alt_share"]                  = alt_share
    features["alt_volume_share"]           = alt_volume_share
    features["alt_share_change_5d"]        = alt_share.pct_change(5)
    features["alt_share_change_20d"]       = alt_share.pct_change(20)
    features["alt_volume_share_change_5d"] = alt_volume_share.pct_change(5)

    # Cross-coin relative log returns
    features["eth_btc_rel_return_5d"]  = features["eth_return_5d"]  - features["btc_return_5d"]
    features["eth_btc_rel_return_20d"] = features["eth_return_20d"] - features["btc_return_20d"]
    features["sol_btc_rel_return_5d"]  = features["sol_return_5d"]  - features["btc_return_5d"]
    features["sol_btc_rel_return_20d"] = features["sol_return_20d"] - features["btc_return_20d"]

    # Price ratios between coins (used as regime signals; may drift slowly)
    eth_btc_ratio = df["eth_close"] / df["btc_close"]
    sol_btc_ratio = df["sol_close"] / df["btc_close"]
    sol_eth_ratio = df["sol_close"] / df["eth_close"]
    features["eth_btc_ratio"]          = eth_btc_ratio
    features["sol_btc_ratio"]          = sol_btc_ratio
    features["sol_eth_ratio"]          = sol_eth_ratio
    features["eth_btc_ratio_return_5d"]  = np.log(eth_btc_ratio).diff(5)
    features["eth_btc_ratio_return_20d"] = np.log(eth_btc_ratio).diff(20)
    features["sol_btc_ratio_return_5d"]  = np.log(sol_btc_ratio).diff(5)
    features["sol_btc_ratio_return_20d"] = np.log(sol_btc_ratio).diff(20)

    # Lagged signals
    for lag in [1, 3, 7]:
        features[f"fear_greed_lag{lag}"]    = fg.shift(lag)
        features[f"btc_dominance_lag{lag}"] = features["btc_dominance"].shift(lag)
        features[f"btc_funding_lag{lag}"]   = df["btc_funding_rate"].shift(lag)

    # BTC regime flags
    btc_close   = df["btc_close"]
    btc_returns = np.log(btc_close).diff()
    btc_ma20    = btc_close.rolling(20).mean()
    btc_ma50    = btc_close.rolling(50).mean()
    btc_ma60    = btc_close.rolling(60).mean()
    btc_ma200   = btc_close.rolling(200).mean()
    btc_vol20   = btc_returns.rolling(20).std()

    features["btc_ma20_ma50_ratio"]   = btc_ma20 / btc_ma50
    features["btc_ma50_ma200_ratio"]  = btc_ma50 / btc_ma200
    features["btc_price_ma200_ratio"] = btc_close / btc_ma200
    features["bull_market_flag"]       = (btc_close > btc_ma200).astype(int)
    features["trend_flag"]             = ((btc_close > btc_ma20) & (btc_ma20 > btc_ma60)).astype(int)
    features["high_volatility_regime"] = (btc_vol20 > btc_vol20.rolling(60).mean()).astype(int)
    features["alt_season_flag"]        = (
        (features["eth_return_20d"] > features["btc_return_20d"]) &
        (features["sol_return_20d"] > features["btc_return_20d"]) &
        (features["btc_dom_change_20d"] < 0)
    ).astype(int)
    features["funding_euphoria_flag"]  = (
        features["btc_funding_gt_2std"] & features["eth_funding_gt_2std"]
    ).astype(int)
    features["fear_capitulation_flag"] = (
        (fg < 25) & (features["btc_return_5d"] < 0)
    ).astype(int)

    # Fear & Greed features
    features["fear_greed_ma5"]           = fg.rolling(5).mean()
    features["fear_greed_ma20"]          = fg.rolling(20).mean()
    features["fear_greed_ma60"]          = fg.rolling(60).mean()
    features["fear_greed_change_1d"]     = fg.diff(1)
    features["fear_greed_change_5d"]     = fg.diff(5)
    features["fear_greed_change_20d"]    = fg.diff(20)
    fg_mean30 = fg.rolling(30).mean()
    fg_std30  = fg.rolling(30).std()
    features["fear_greed_zscore_30d"]    = (fg - fg_mean30) / fg_std30
    features["fear_greed_extreme_fear"]  = (fg < 25).astype(int)
    features["fear_greed_fear"]          = ((fg >= 25) & (fg < 50)).astype(int)
    features["fear_greed_greed"]         = ((fg >= 50) & (fg < 75)).astype(int)
    features["fear_greed_extreme_greed"] = (fg >= 75).astype(int)
    features["fear_greed"]               = fg

    feature_df = pd.DataFrame(features, index=df.index)

    for ticker in tickers:
        feature_df[f"{ticker}_target_1d_up"]  = (feature_df[f"{ticker}_target_1d"]  > 0).astype(int)
        feature_df[f"{ticker}_target_5d_up"]  = (feature_df[f"{ticker}_target_5d"]  > 0).astype(int)
        feature_df[f"{ticker}_target_20d_up"] = (feature_df[f"{ticker}_target_20d"] > 0).astype(int)

    return feature_df.dropna()


feature_df = creating_feature_df(crypto_data)
feature_df = feature_df.select_dtypes(include="number")

TICKERS     = ["btc", "sol", "eth"]
all_targets = {c for c in feature_df.columns if "_target_" in c}

ticker_X_cols = {}
ticker_y_cols = {}

for ticker in TICKERS:
    own_features    = [c for c in feature_df.columns
                       if c.startswith(f"{ticker}_") and c not in all_targets]
    global_features = [c for c in feature_df.columns
                       if not any(c.startswith(f"{t}_") for t in TICKERS) and c not in all_targets]
    cross_features  = [c for c in feature_df.columns
                       if any(c.startswith(f"{t}_") for t in TICKERS if t != ticker)
                       and c not in all_targets]
    ticker_X_cols[ticker] = own_features + global_features + cross_features
    ticker_y_cols[ticker] = [c for c in feature_df.columns if c.startswith(f"{ticker}_target_")]

# Holdout gate — last 180 days are frozen; use only train_df for model development
HOLDOUT_CUTOFF = feature_df.index[-1] - pd.DateOffset(days=180)
train_df   = feature_df[feature_df.index <  HOLDOUT_CUTOFF]
holdout_df = feature_df[feature_df.index >= HOLDOUT_CUTOFF]
print(f"Training : {train_df.index[0].date()} -> {train_df.index[-1].date()}  ({len(train_df)} days)")
print(f"Holdout  : {holdout_df.index[0].date()} -> {holdout_df.index[-1].date()} ({len(holdout_df)} days)  <- DO NOT TOUCH")
feature_df.to_csv("Feature_DataFrame.csv")

#imports:
from pathlib import Path
import pandas as pd
import sys

from polymarket_overlay.poly_data import get_yes_token_id
sys.path.insert(0, str(Path(__file__).resolve().parent / "Models"))
from Models.feature_engineering import creating_feature_df
from Models.volatility_model import add_forward_vol_target, add_parkinson_fwd_vol, add_gk_fwd_vol, add_trailing_vol_baselines, add_ewma_vol, add_walk_forward_garch, add_walk_forward_ml_vol
from Models.vol_model_selection import score_volatility_forecasts
from polymarket_overlay.poly_data import find_crypto_events, iter_tradeable_markets, get_midpoint

def main():
    BASE_DIR = Path(__file__).resolve().parent
    main_csv_path = BASE_DIR / "Database" / "Crypto_ML_Dataset.csv"
    _raw = (
    pd.read_csv(main_csv_path, parse_dates=["date"])
    .sort_values("date")
    .drop_duplicates(subset="date")
    .set_index("date")
)
    assert _raw.index.is_unique, "Duplicate dates remain after dedup"
    _price_cols = [c for c in _raw.columns if c.endswith("_close")]
    _raw = _raw.loc[: _raw[_price_cols].dropna(how="all").index[-1]]

    crypto_data = _raw.ffill(limit=2)
    '''
    feature_df = creating_feature_df(main_df)
    feature_df = feature_df.select_dtypes(include="number") '''

    feature_path = BASE_DIR / "Models" / "Feature_DataFrame.csv"
    feature_df = pd.read_csv(feature_path, index_col=0, parse_dates=True)

    TICKERS     = ["btc", "sol", "eth"]
    all_targets = {c for c in feature_df.columns if "_target_" in c}

    #index by ticker for when u want to run an ml model on these features
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

    #adding forward volatility predictions 
    tickers = ['btc', 'sol', 'eth']
    for ticker in tickers:
        feature_df[f"{ticker}_log_returns"] = feature_df[f"{ticker}_return_1d"]
    for ticker in tickers:
        feature_df[f"{ticker}_fwd_vol_7d"] = add_forward_vol_target(feature_df, ticker)
        feature_df = add_parkinson_fwd_vol(feature_df, crypto_data, ticker)
        feature_df = add_gk_fwd_vol(feature_df, crypto_data, ticker)
        feature_df = add_trailing_vol_baselines(feature_df, ticker)
        feature_df = add_ewma_vol(feature_df, ticker)
        feature_df = add_walk_forward_garch(feature_df, ticker)
        # ML forecast trained on the Parkinson forward-vol target, aligned to the
        # same walk-forward span so it scores head-to-head with GARCH/EWMA/trailing.
        feature_df = add_walk_forward_ml_vol(
            feature_df, ticker_X_cols[ticker], ticker,
            target_col=f"{ticker}_fwd_park_vol_7d", horizon=7,
        )

    # persist the vol feature set: base features + realized-vol targets + every forecast
    vol_path = BASE_DIR / "Models" / "Feature_DataFrame_vol.csv"
    feature_df.to_csv(vol_path)
    print(f"wrote {vol_path.name}: {feature_df.shape[0]} rows x {feature_df.shape[1]} cols")

    # reshape wide -> long, then run the scoring function
    methods = ["trailing_vol_5d", "trailing_vol_7d", "trailing_vol_14d",
               "trailing_vol_20d", "trailing_vol_30d", "ewma_vol", "garch_vol_7d",
               "ml_vol_7d"]
    targets = {"realized_gk": "fwd_gk_vol_7d", "realized_park": "fwd_park_vol_7d"}
    rows = []
    for ticker in tickers:
        for m in methods:
            col = f"{ticker}_{m}"
            if col not in feature_df.columns:
                continue
            rec = pd.DataFrame({
                "date": feature_df.index, "asset": ticker, "horizon": 7,
                "method": m, "forecast_vol": feature_df[col].to_numpy(),
            })
            for key, tcol in targets.items():
                full = f"{ticker}_{tcol}"
                if full in feature_df.columns:
                    rec[key] = feature_df[full].to_numpy()
            rows.append(rec)
    results_df = pd.concat(rows, ignore_index=True)
    scores = score_volatility_forecasts(results_df)
    print("\n=== Volatility forecast scores (method x answer key) ===\n")
    print(scores.to_string(index=False))

    crypto_events = find_crypto_events()

    rows = []
    for event, market in iter_tradeable_markets(crypto_events):
        yes_token_id = get_yes_token_id(market)
        midpoint = get_midpoint(yes_token_id)
        if midpoint is None:
            continue  # no book after all; skip

        rows.append({
            "event": event["title"],
            "question": market["question"],
            "yes_token_id": yes_token_id,
            "yes_midpoint": midpoint,
        })

    if not rows:
        print("No tradeable crypto markets with a live orderbook found.")
    else:
        markets_df = pd.DataFrame(rows)
        print(markets_df.to_string(index=False))

        






if __name__ == "__main__":
    main()
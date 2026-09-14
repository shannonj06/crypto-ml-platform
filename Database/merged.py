import pandas as pd
coin_market_df = pd.read_csv("Database/Coin_Market_cap.csv")
fear_df = pd.read_csv("Database/Fear_Greed.csv")
final_market = pd.read_csv("Database/final_market_cap.csv")
binance = pd.read_csv("Database/binance_daily.csv")
raw = pd.read_csv("Database/binance_daily.csv")

print(raw.tail(30)[["date", "btc_close"]])
merged = (
    binance
    .merge(coin_market_df, on="date", how="left")
    .merge(fear_df, on="date", how="left")
    .merge(final_market, on="date", how="left")
)

merged = merged.drop(columns=[
    "btc_sum_open_interest",
    "btc_sum_open_interest_value",
    "btc_count_long_short_ratio",
    "btc_sum_taker_long_short_vol_ratio",
    "eth_sum_open_interest",
    "eth_sum_open_interest_value",
    "eth_count_long_short_ratio",
    "eth_sum_taker_long_short_vol_ratio",
    "sol_sum_open_interest",
    "sol_sum_open_interest_value",
    "sol_count_long_short_ratio",
    "sol_sum_taker_long_short_vol_ratio",
    "Unnamed: 0_x",
    "Unnamed: 0_y"
], errors="ignore")

merged.to_csv("Crypto_ML_Dataset.csv", index=False)


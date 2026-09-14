import pandas as pd
import os

_DIR = os.path.dirname(os.path.abspath(__file__))


def clean_market_data(csv_path):
    df = pd.read_csv(os.path.join(_DIR, csv_path))

    df["date"] = pd.to_datetime(df["timestamp"])
    cols_to_keep = [
        "date",
        "btc_dominance",
        "eth_dominance",
        "USD_total_market_cap",
        "USD_total_volume24h",
        "USD_altcoin_market_cap",
        "USD_altcoin_volume24h"
    ]
    df = df[cols_to_keep]

    for col in cols_to_keep[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("date").reset_index(drop=True)
    return df


if __name__ == "__main__":
    df = clean_market_data("total_market_cap.csv")
    df.to_csv(os.path.join(_DIR, "final_market_cap.csv"), index=False)

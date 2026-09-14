import pandas as pd
import os

_DIR = os.path.dirname(__file__)


def create_df():
    out = None
    for coin in ["btc", "eth", "sol"]:
        df = pd.read_csv(os.path.join(_DIR, f"{coin}_market_cap.csv"))
        df = df[df["asset"] == coin].copy()
        df["date"] = pd.to_datetime(df["time"], utc=True).dt.date
        df = (
            df[["date", "CapMrktEstUSD"]]
            .drop_duplicates(subset="date", keep="last")
            .rename(columns={"CapMrktEstUSD": f"{coin}_market_cap"})
        )
        out = df if out is None else out.merge(df, on="date", how="outer")
    return out.sort_values("date").reset_index(drop=True)

if __name__ == "__main__":
    df = create_df()
    df.to_csv("Coin_Market_cap.csv")
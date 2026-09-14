import pandas as pd
from .dataSourcing import _get

URL = "https://api.alternative.me/fng/"
params = {
    "limit": 0
}
def get_fear_greed():
    response = _get(URL, params=params)
    df = pd.DataFrame(response["data"])
    return process_fear_greed(df)

def process_fear_greed(df):
    df = df.copy()

    df["date"] = pd.to_datetime(
        pd.to_numeric(df["timestamp"]),
        unit="s",
        utc=True
    ).dt.date

    df["fear_greed"] = pd.to_numeric(
        df["value"],
        errors="coerce"
    )

    df = (
        df[["date", "fear_greed"]]
        .sort_values("date")
        .reset_index(drop=True)
    )
    return df
if __name__ == "__main__":
    # Write into Database/ regardless of where this is run from. It used to land
    # in the working directory while merged.py read it from Database/.
    from pathlib import Path

    out = Path(__file__).resolve().parent.parent / "Database" / "Fear_Greed.csv"
    df = get_fear_greed()
    df.to_csv(out, index=False)
    print(f"Fear & Greed: {len(df)} rows through {df['date'].max()} -> {out}")

    
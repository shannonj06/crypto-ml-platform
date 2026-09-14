import pandas as pd
import os

_DIR = os.path.dirname(__file__)
COINS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT"}


def _epoch_to_utc_date(epoch):
    """Convert an epoch column to UTC calendar dates, tolerating mixed units.

    Binance's data.binance.vision bulk dumps switched their timestamp columns
    from milliseconds to microseconds starting with Jan-2025 data, so a single
    multi-year file can contain both. Scale the 16-digit microsecond rows down
    to milliseconds before converting.
    """
    s = pd.to_numeric(epoch, errors="coerce")
    ms = s.where(s < 1e15, s / 1000)
    return pd.to_datetime(ms, unit="ms", utc=True).dt.date


def process_funding_df(csv_path):
    # e.g. "funding_BTCUSDT.csv" -> "btc"
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    coin = stem.split("_")[1].replace("USDT", "").lower()

    df = pd.read_csv(csv_path)
    df["date"] = _epoch_to_utc_date(df["calc_time"])
    df = (
        df.groupby("date")
          .agg(funding_rate=("funding_rate", "mean"))
          .reset_index()
    )
    return df.rename(columns={"funding_rate": f"{coin}_funding_rate"})


def process_klines_df(csv_path, coin):
    df = pd.read_csv(csv_path)
    df["date"] = _epoch_to_utc_date(df["open_time"])
    cols = ["open", "high", "low", "close", "volume", "trades"]
    df = df[["date"] + cols]
    return df.rename(columns={c: f"{coin}_{c}" for c in cols})


def process_metrics(csv_path, coin):
    # Metrics dumps use a string timestamp ("2021-01-01 00:00:00") at 5-minute
    # granularity, not an epoch number, so parse it as a datetime and average
    # each day down to one daily row.
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(
        df["create_time"], format="%Y-%m-%d %H:%M:%S", utc=True
    ).dt.date
    cols = [
        "sum_open_interest",
        "sum_open_interest_value",
        "count_long_short_ratio",
        "sum_taker_long_short_vol_ratio",
    ]
    df = df.groupby("date")[cols].mean().reset_index()
    return df.rename(columns={c: f"{coin}_{c}" for c in cols})


def _merge_on_date(frames):
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on="date", how="outer")
    return out


def build_funding():
    return _merge_on_date([
        process_funding_df(os.path.join(_DIR, f"funding_{sym}.csv"))
        for sym in COINS.values()
    ])


def build_klines():
    return _merge_on_date([
        process_klines_df(os.path.join(_DIR, f"klines_{sym}.csv"), coin)
        for coin, sym in COINS.items()
    ])


def build_metrics():
    return _merge_on_date([
        process_metrics(os.path.join(_DIR, f"metrics_{sym}.csv"), coin)
        for coin, sym in COINS.items()
    ])


def build_combined():
    """One daily frame: klines + funding + futures metrics for BTC/ETH/SOL."""
    combined = _merge_on_date([build_klines(), build_funding(), build_metrics()])
    return combined.sort_values("date").reset_index(drop=True)


if __name__ == "__main__":
    combined = build_combined()
    print(f"rows: {len(combined)}")
    print(f"date range: {combined['date'].min()} -> {combined['date'].max()}")
    print(f"columns ({len(combined.columns)}):")
    for c in combined.columns:
        print(f"  {c}")
    out_path = os.path.join(_DIR, "binance_full.csv")
    combined.to_csv(out_path, index=False)
    print(f"\nwrote {out_path}")

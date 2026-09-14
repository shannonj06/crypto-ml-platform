"""
update_prices.py — keep Database/Crypto_ML_Dataset.csv fresh.

The prediction engine reads daily closes from that CSV. If the CSV is stale, the
forecasts (and every Polymarket "edge") are stale too. This script pulls the most
recent daily candles for BTC / ETH / SOL from Binance's public data endpoint
(no API key needed) and appends any dates the CSV is missing.

It only fills the OHLCV columns for new rows. The other columns (funding,
fear_greed, market caps) stay blank — the forecast only uses closes, so that is
enough to keep predictions current. Run it before the outlook report.

    python -m app.update_prices
"""
from __future__ import annotations

import pandas as pd
import requests

from app.engine import DATA_PATH

# Public Binance data mirror — works from GitHub Actions without a key or geo block.
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
COINS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT"}


def _fetch_daily(symbol: str, limit: int = 90) -> pd.DataFrame:
    """Last `limit` daily candles for one symbol, as a date-indexed OHLCV frame."""
    r = requests.get(BASE_URL, params={"symbol": symbol, "interval": "1d", "limit": limit})
    r.raise_for_status()
    rows = r.json()
    # Binance kline columns: [open_time, open, high, low, close, volume, close_time,
    #                         quote_volume, trades, ...]
    df = pd.DataFrame(rows).iloc[:, [0, 1, 2, 3, 4, 5, 8]]
    df.columns = ["open_time", "open", "high", "low", "close", "volume", "trades"]
    df["date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_convert(None).dt.normalize()
    df = df.drop(columns="open_time").astype(
        {"open": float, "high": float, "low": float, "close": float,
         "volume": float, "trades": float}
    )
    return df.set_index("date")


def fetch_recent_prices(limit: int = 90) -> pd.DataFrame:
    """One frame of recent OHLCV for all coins, columns named like the CSV."""
    frames = []
    for coin, symbol in COINS.items():
        df = _fetch_daily(symbol, limit)
        frames.append(df.rename(columns={c: f"{coin}_{c}" for c in df.columns}))
    return pd.concat(frames, axis=1)


def update_csv(limit: int = 90) -> int:
    """Append any missing recent dates to the dataset. Returns rows added."""
    existing = pd.read_csv(DATA_PATH, parse_dates=["date"]).set_index("date")
    fresh = fetch_recent_prices(limit)

    # Drop today's still-forming candle; keep only fully closed days.
    today = pd.Timestamp.now("UTC").normalize().tz_localize(None)
    fresh = fresh[fresh.index < today]

    prev_latest = existing.index.max()
    # combine_first keeps existing values and fills blanks (and new dates) from
    # `fresh`. This both adds new days AND backfills any empty recent closes.
    combined = existing.combine_first(fresh).sort_index()
    combined.index.name = "date"
    combined.to_csv(combined_path := DATA_PATH)

    added = int((combined.index > prev_latest).sum())
    new_latest = combined.index.max()
    if added == 0 and new_latest == prev_latest:
        print(f"Already up to date (latest {prev_latest.date()}).")
    else:
        print(f"Updated through {new_latest.date()} (+{added} new day(s)).")
    return added


if __name__ == "__main__":
    update_csv()

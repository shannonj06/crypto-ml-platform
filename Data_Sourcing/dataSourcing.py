import time
import pandas as pd
import requests
from Data_Sourcing.db import cloud_engine, require
from datetime import date
from config import API_KEY, BINANCE_URL

API_KEY = API_KEY
BASE_URL = BINANCE_URL

df = pd.DataFrame()
headers = {"x-cg-demo-api-key": API_KEY}

def _get(url, params=None):
    for attempt in range(5):
        response = requests.get(url, params=params, headers=None)
        print(response.status_code)
        if response.status_code == 429:
            wait = int(response.headers.get("Retry-After", 2 ** attempt))
            print(f"429 — waiting {wait}s")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"rate limited after retries: {url}")

def get_coin_data(coin_id, days="max"):
    url = f"{BASE_URL}coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
        "precision": "3"
    }
    return _get(url, params)

def get_market_data(days="max"):
    params = {
        "days": days
    }
    url = f"{BASE_URL}global"
    return _get(url, params)

def get_olhcv_data(coin_id, days="max"):
    params = {
        "days": days
    }
    url = f"{BASE_URL}global"
    return _get(url, params)

def _parse_coin_df(data, prefix):
    series = [
        (f"{prefix}_price", data["prices"]),
        (f"{prefix}_market_cap", data["market_caps"]),
        (f"{prefix}_volume", data["total_volumes"]),
    ]
    dfs = []
    for col, rows in series:
        part = pd.DataFrame(rows, columns=["timestamp", col])
        part["timestamp"] = (
            pd.to_datetime(part["timestamp"], unit="ms", utc=True)
            .dt.floor("D")
            .dt.tz_convert(None)  # naive UTC — consistent with DB and update_df
        )
        dfs.append(part)
    merged = dfs[0]
    for d in dfs[1:]:
        merged = merged.merge(d, on="timestamp", how="inner")
    return merged


def build_crypto_dataframe(days):
    btc_data = get_coin_data("bitcoin", days)
    eth_data = get_coin_data("ethereum", days)
    sol_data = get_coin_data("solana", days)

    btc_df = _parse_coin_df(btc_data, "btc")
    eth_df = _parse_coin_df(eth_data, "eth")
    sol_df = _parse_coin_df(sol_data, "sol")

    # outer so coins with different date ranges don't drop each other's rows
    merged = btc_df.merge(eth_df, on="timestamp", how="outer")
    merged = merged.merge(sol_df, on="timestamp", how="outer")
    return merged.sort_values("timestamp").reset_index(drop=True)


def update_df():
    db = require(cloud_engine, "NEON_URL")
    query = "SELECT MAX(timestamp) FROM crypto_prices"
    latest_timestamp = pd.read_sql(query, db).iloc[0, 0]

    # Empty table -> nothing to update against, so source a full year.
    if pd.isna(latest_timestamp):
        days_to_source = 1825  # 5 years
    else:
        # Stored timestamps are UTC (from pd.to_datetime(..., unit="ms")),
        # so compare against UTC now rather than local time.
        latest_timestamp = pd.Timestamp(latest_timestamp)
        now_utc = pd.Timestamp.now(tz="UTC").tz_localize(None)
        days_to_source = (now_utc - latest_timestamp).days
        days_to_source = max(days_to_source, 7)

    if days_to_source < 1:
        print("crypto_prices is already up to date.")
        return

    new_df = build_crypto_dataframe(days_to_source)

    new_df = new_df[
    new_df["timestamp"] > latest_timestamp
    ]

    new_df.to_sql(
    "crypto_prices", 
    cloud_engine, 
    if_exists="append", 
    index=False)


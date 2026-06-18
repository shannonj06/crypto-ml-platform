import time
import pandas as pd
import requests
from db import engine, cloud_engine
from datetime import date
from config import API_KEY, COIN_GEKO_URL

API_KEY = API_KEY
BASE_URL = COIN_GEKO_URL

df = pd.DataFrame()
headers = {"x-cg-demo-api-key": API_KEY}

def _get(url, params=None):
    for attempt in range(5):
        response = requests.get(url, params=params, headers=headers)
        print(response.status_code)
        if response.status_code == 429:
            wait = int(response.headers.get("Retry-After", 2 ** attempt))
            print(f"429 — waiting {wait}s")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"rate limited after retries: {url}")

def get_coin_data(coin_id, days=365):
    url = f"{BASE_URL}coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
        "precision": "3"
    }
    return _get(url, params)

def get_market_data():
    url = f"{BASE_URL}global"
    return _get(url)

def get_olhc(coin_id, days=365):
    url = f"{BASE_URL}coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": days
    }
    return _get(url, params)

def get_circ_and_fdv(coin_id):
    url = f"{BASE_URL}coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false"
    }
    return _get(url, params)

#NEED THIS DATA REMAINING   
'''
    market wide:
    -btc_dominance
    -fear greed value
    -total market cap
'''

def build_crypto_dataframe(days):
#this only gives prices market caps and total volumes
    btc_data = get_coin_data("bitcoin", days)
    eth_data = get_coin_data("ethereum", days)
    sol_data= get_coin_data("solana", days)

#BTC PRICE DATA
    price_df = pd.DataFrame(btc_data['prices'], columns=["timestamp", "btc_prices"])
    market_cap_df = pd.DataFrame(btc_data["market_caps"], columns=["timestamp", "btc_market_cap"])
    volume_df = pd.DataFrame(btc_data["total_volumes"], columns=["timestamp", "btc_volumes"])
    merged_btc = price_df.merge(market_cap_df, on= "timestamp", how="inner")
    merged_btc = merged_btc.merge(volume_df, on= "timestamp", how="inner")

#ETH PRICE DATA
    price_df = pd.DataFrame(eth_data['prices'], columns=["timestamp", "eth_prices"])
    market_cap_df = pd.DataFrame(eth_data["market_caps"], columns=["timestamp", "eth_market_cap"])
    volume_df = pd.DataFrame(eth_data["total_volumes"], columns=["timestamp", "eth_volumes"])
    merged_eth = price_df.merge(market_cap_df, on= "timestamp", how="inner")
    merged_eth = merged_eth.merge(volume_df, on= "timestamp", how="inner")

#SOL PRICE DATA
    price_df = pd.DataFrame(sol_data['prices'], columns=["timestamp", "sol_prices"])
    market_cap_df = pd.DataFrame(sol_data["market_caps"], columns=["timestamp", "sol_market_cap"])
    volume_df = pd.DataFrame(sol_data["total_volumes"], columns=["timestamp", "sol_volumes"])
    merged_sol = price_df.merge(market_cap_df, on= "timestamp", how="inner")
    merged_sol = merged_sol.merge(volume_df, on= "timestamp", how="inner")

#MERGED PRICE DATA
    merged_price = merged_btc.merge(merged_eth, on='timestamp', how='inner')
    merged_price = merged_price.merge(merged_sol, on="timestamp", how='inner')

#OLHC DATA
    btc_ohlc = get_olhc("bitcoin", days)
    eth_ohlc = get_olhc("ethereum", days)
    sol_ohlc = get_olhc("solana", days)

    btc_olhc_df = pd.DataFrame(btc_ohlc, columns=["timestamp", 'btc_open', 'btc_high', 'btc_low', 'btc_close'])
    eth_olhc_df = pd.DataFrame(eth_ohlc, columns=["timestamp", 'eth_open', 'eth_high', 'eth_low', 'eth_close'])
    sol_olhc_df = pd.DataFrame(sol_ohlc, columns=["timestamp", 'sol_open', 'sol_high', 'sol_low', 'sol_close'])

    merged_olhc = btc_olhc_df.merge(eth_olhc_df, on= 'timestamp', how='inner')
    merged_olhc = merged_olhc.merge(sol_olhc_df, on='timestamp', how='inner')

    merged_df = merged_price.merge(merged_olhc, on='timestamp', how='inner')

    merged_df["timestamp"] = pd.to_datetime(
    merged_df["timestamp"],
    unit="ms"
)
    return merged_df


'''market_data = get_market_data()
print(market_data)
print(market_data.keys()) 

#i need historical data for this but it isnt lol ill figure it out later
btc_dominance = market_data['data']['market_cap_percentage']['btc']
eth_dominance = market_data['data']['market_cap_percentage']['eth']
sol_dominance = market_data['data']['market_cap_percentage']['sol']
total_market_cap = market_data['data']['total_market_cap']['usd'] '''

'''
#CIRC AND FDV, not timestamped need to fix
btc_info = get_circ_and_fdv("bitcoin")
eth_info = get_circ_and_fdv("ethereum") 
sol_info = get_circ_and_fdv("solana")
 '''

def update_df():
    query = "SELECT MAX(timestamp) FROM crypto_prices"
    latest_timestamp = pd.read_sql(query, engine).iloc[0, 0]

    # Empty table -> nothing to update against, so source a full year.
    if pd.isna(latest_timestamp):
        days_to_source = 365
    else:
        # Stored timestamps are UTC (from pd.to_datetime(..., unit="ms")),
        # so compare against UTC now rather than local time.
        latest_timestamp = pd.Timestamp(latest_timestamp)
        now_utc = pd.Timestamp.now(tz="UTC").tz_localize(None)
        days_to_source = (now_utc - latest_timestamp).days

    if days_to_source < 1:
        print("crypto_prices is already up to date.")
        return

    new_df = build_crypto_dataframe(days_to_source)
    new_df = build_crypto_dataframe(days_to_source)

    new_df = new_df[
    new_df["timestamp"] > latest_timestamp
    ]

    new_df.to_sql(
    "crypto_prices",
    engine,
    if_exists="append",
    index=False
)
    new_df.to_sql(
    "crypto_prices", 
    cloud_engine, 
    if_exists="append", 
    index=False)
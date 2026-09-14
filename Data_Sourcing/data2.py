import time
import pandas as pd
import requests
from Data_Sourcing.db import cloud_engine
from datetime import date
from config import BINANCE_URL, FUTURES_BINANCE_URL, OPEN_INTEREST_URL

BASE_URL = BINANCE_URL
FUTURES_URL = FUTURES_BINANCE_URL
INTEREST_URL = OPEN_INTEREST_URL

df = pd.DataFrame()

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

#BTCUSDT, ETHUSDT, SOLUSDT
def get_ohlcv(coin):
    URL = f"{BASE_URL}klines"
    params = {
    "symbol": coin,
    "interval": "1d",
    "limit": 1000
}
    return _get(URL, params=params)

def get_funding_rate(coin):
    URL = f"{FUTURES_BINANCE_URL}fundingRate"
    params = {
    "symbol": coin,
    "limit": 1000
}
    return _get(URL, params=params)

def get_open_interest(coin):
    URL = OPEN_INTEREST_URL
    params = {
    "symbol": coin,
    "period": "1d",
    "limit": 100
}
    return _get(URL, params=params)

def get_long_short_ratio(coin):
    url = f"{FUTURES_BINANCE_URL}globalLongShortAccountRatio"

    params = {
        "symbol": coin,
        "period": "1d",
        "limit": 500
    }
    return _get(url, params=params)


get_ohlcv("BTCUSDT")
get_ohlcv("ETHUSDT")
get_ohlcv("SOLUSDT")

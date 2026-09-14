import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("COIN_GEKO_API_KEY")

# Despite the name, this is the CoinGecko API base (dataSourcing builds
# "{BASE_URL}coins/{id}/market_chart" from it). The GitHub Action passed it as
# BASE_URL while this read BINANCE_URL, so it resolved to None in CI and every
# request went to "Nonecoins/...". Accept every name that has been used.
COINGECKO_URL = (
    os.getenv("COINGECKO_URL") or os.getenv("BINANCE_URL") or os.getenv("BASE_URL")
)
BINANCE_URL = COINGECKO_URL  # legacy alias — dataSourcing.py and data2.py import this
POSTGRE_URL = os.getenv("POSTGRE_URL")
NEON_URL = os.getenv("NEON_URL")


FUTURES_BINANCE_URL = os.getenv("FUTURES_BINANCE_URL")
OPEN_INTEREST_URL = os.getenv("OPEN_INTEREST_URL")
LONG_SHORT_URL = os.getenv("LONG_SHORT_URL")
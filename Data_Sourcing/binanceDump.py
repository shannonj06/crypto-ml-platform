#!/usr/bin/env python3
"""
binance_dump.py - pull Binance public-data dumps for BTC, ETH, SOL.

Features grabbed (all free, no API key):
  - spot klines       -> OHLCV / price / volume per coin
  - futures funding   -> funding rate
  - futures metrics   -> open interest (+ long/short ratios)

Source : https://data.binance.vision
Output : ./binance_data/<feature>_<SYMBOL>.csv

Setup  : pip install requests pandas
Run    : python binance_dump.py
"""

import io
import zipfile
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import pandas as pd

BASE = "https://data.binance.vision/data"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
KLINE_INTERVAL = "1d"            # try "1h" or "1m" for finer data
START = dt.date(2021, 1, 1)     # earliest period to attempt (older = more files = slower)
END = dt.date.today()
OUT = Path("binance_data")
OUT.mkdir(exist_ok=True)

S = requests.Session()

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
              "quote_volume", "trades", "taker_base", "taker_quote", "ignore"]
FUNDING_COLS = ["calc_time", "funding_interval_hours", "funding_rate"]


def month_range(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def day_range(a, b):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def grab(url):
    """Return the inner CSV of a Binance zip as a DataFrame, or None if the file doesn't exist."""
    r = S.get(url, timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            raw = f.read()
    # Binance added header rows to newer files; sniff whether row 0 is a header or data.
    first_cell = raw.split(b"\n", 1)[0].split(b",", 1)[0]
    try:
        float(first_cell)
        header = None       # row 0 is data
    except ValueError:
        header = 0          # row 0 is a header
    return pd.read_csv(io.BytesIO(raw), header=header)


def pull_monthly(kind, symbol, url_fn, cols=None):
    frames = []
    for y, m in month_range(START, END):
        try:
            df = grab(url_fn(y, m))
        except Exception as e:
            print(f"  [{kind}] {symbol} {y}-{m:02d}  skip ({e})")
            continue
        if df is not None:
            frames.append(df)
            print(f"  [{kind}] {symbol} {y}-{m:02d}  ({len(df)} rows)")
    if not frames:
        print(f"  [{kind}] {symbol}: nothing found")
        return
    out = pd.concat(frames, ignore_index=True)
    if cols and out.shape[1] == len(cols):
        out.columns = cols
    out.to_csv(OUT / f"{kind}_{symbol}.csv", index=False)


def pull_metrics(symbol, workers=16):
    """Open interest + long/short ratios. metrics is published as DAILY files only,
    so this downloads one file per day in parallel and prints progress as it goes."""
    dates = list(day_range(START, END))
    total = len(dates)
    found = {}

    def task(d):
        url = f"{BASE}/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{d:%Y-%m-%d}.zip"
        try:
            return d, grab(url)
        except Exception:
            return d, None

    print(f"  [metrics] {symbol}: checking {total} days with {workers} workers...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(task, d) for d in dates]
        for i, fut in enumerate(as_completed(futures), 1):
            d, df = fut.result()
            if df is not None:
                found[d] = df
            if i % 100 == 0 or i == total:
                print(f"  [metrics] {symbol}: {i}/{total} days checked, {len(found)} with data")

    if not found:
        print(f"  [metrics] {symbol}: nothing found (OI archive may not reach your START date)")
        return
    out = pd.concat([found[d] for d in sorted(found)], ignore_index=True)
    out.to_csv(OUT / f"metrics_{symbol}.csv", index=False)
    print(f"  [metrics] {symbol}: {len(out)} rows")


def main():
    for sym in SYMBOLS:
        print(sym)
        pull_monthly(
            "klines", sym,
            lambda y, m, s=sym: f"{BASE}/spot/monthly/klines/{s}/{KLINE_INTERVAL}/{s}-{KLINE_INTERVAL}-{y:04d}-{m:02d}.zip",
            KLINE_COLS,
        )
        pull_monthly(
            "funding", sym,
            lambda y, m, s=sym: f"{BASE}/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{y:04d}-{m:02d}.zip",
            FUNDING_COLS,
        )
        pull_metrics(sym)
    print(f"\nDone. CSVs are in ./{OUT}/")


if __name__ == "__main__":
    main()
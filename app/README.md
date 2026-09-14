# Crypto Outlook backend (`app/`)

This folder is the finished backend. It turns the Monte Carlo engine and Polymarket
parsing into two features and an API a frontend can call.

## The two features

1. **Price outlook** — for BTC, ETH, SOL: current price, the likely range over the
   next N days, and the chance of going up. From block-bootstrap Monte Carlo paths,
   scaled to an EWMA volatility forecast.
2. **Polymarket signals** — for each live crypto market we can price: our probability
   vs the market's, the edge, and how much to bet (fractional Kelly).

## Files

| File | What it does |
|------|--------------|
| `engine.py` | The brain. `predict_all()` and `polymarket_signals()`. Everything else just calls these. |
| `report.py` | Writes the "every 3 days" outlook to `reports/outlook_latest.md` and `.json`. |
| `api.py` | FastAPI web server the frontend talks to. |
| `update_prices.py` | Refreshes daily closes in the dataset from Binance (no API key). |

## Run it locally

```bash
pip install -r requirements.txt

# 1. get fresh prices (do this first — stale prices = meaningless signals)
python -m app.update_prices

# 2a. generate the report (both features -> reports/)
python -m app.report

# 2b. or run the API and open http://127.0.0.1:8000/docs
uvicorn app.api:app --reload
```

## API endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /health` | `{"status": "ok"}` |
| `GET /predictions?horizon=7` | price outlook for each asset |
| `GET /polymarket?bankroll=1000` | live markets: our prob vs market + bet size |
| `GET /outlook` | the last saved report (fast, no recompute) |

## Automation (GitHub Actions)

- `.github/workflows/outlook.yml` — every 3 days: refresh prices → build report →
  commit `reports/` and the updated dataset back to the repo. You can also run it
  by hand from the **Actions** tab (`workflow_dispatch`).
- `.github/workflows/update_data.yml` — the existing daily job that loads data into
  your Neon database.

## Important: real money

The bet sizes are **not** cleared for real capital. The gates live in
`trading/polytrading_signals.py` (`CALIBRATION_VALIDATED`, `PAPER_TRADING_PASSED`),
both `False`. Paper-trade and validate first.

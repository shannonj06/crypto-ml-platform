"""
api.py — the HTTP layer a frontend talks to.

Run it locally with:
    uvicorn app.api:app --reload

Then open http://127.0.0.1:8000/docs for an interactive page of every endpoint.

Endpoints:
    GET /health                     is the server up?
    GET /predictions?horizon=7      price outlook for btc / eth / sol
    GET /polymarket?bankroll=1000   live markets: our prob vs market + bet size
    GET /outlook                    the last saved report (fast; no recompute)
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.engine import BASE_DIR, predict_all, polymarket_signals

app = FastAPI(title="Crypto Outlook API", version="1.0")

# Let a frontend on any origin call this during development. Tighten later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/predictions")
def predictions(horizon: int = 7):
    """Monte Carlo price outlook for each asset over `horizon` days."""
    return predict_all(horizon)


@app.get("/polymarket")
def polymarket(bankroll: float = 1000.0, tau: float = 0.03):
    """
    Live Polymarket crypto markets we can price: our probability, the market's,
    the edge, and a suggested bet (fraction of bankroll + dollars).
    """
    return polymarket_signals(tau=tau, bankroll=bankroll)


@app.get("/outlook")
def outlook():
    """The most recent saved report (written by app/report.py). No recompute."""
    path = BASE_DIR / "reports" / "outlook_latest.json"
    if not path.exists():
        return {"error": "no report yet — run: python -m app.report"}
    return json.loads(path.read_text(encoding="utf-8"))

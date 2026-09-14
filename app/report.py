"""
report.py — the "every 3 days" outlook.

Run this on a schedule (a GitHub Action does it for you). It writes two files
into reports/:
  - outlook_latest.md    a readable summary for you and the team
  - outlook_latest.json  the same numbers as data, for the API / a frontend

It covers both features:
  1. price outlook for btc / eth / sol
  2. any live Polymarket markets we can price, with our number vs the market's
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.engine import BASE_DIR, predict_all, polymarket_signals

REPORTS_DIR = BASE_DIR / "reports"


def _env_number(name: str, default: float) -> float:
    """Read a numeric override from the environment, ignoring junk values."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"warning: {name}={raw!r} is not a number — using {default}")
        return default


# Overridable so the GitHub Action's workflow_dispatch inputs actually do
# something: OUTLOOK_HORIZON / OUTLOOK_BANKROLL.
HORIZON = int(_env_number("OUTLOOK_HORIZON", 7))      # forecast window in days
BANKROLL = _env_number("OUTLOOK_BANKROLL", 1000.0)    # so bet sizes show as dollars


def build_report(horizon: int = HORIZON, bankroll: float = BANKROLL) -> dict:
    """Gather both features into one plain dict."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "horizon_days": horizon,
        "bankroll": bankroll,
        "predictions": predict_all(horizon),
        "polymarket_signals": polymarket_signals(bankroll=bankroll),
    }


def to_markdown(report: dict) -> str:
    """Turn the report dict into a readable markdown page."""
    lines = [
        f"# Crypto Outlook — {report['generated_at'][:10]}",
        "",
        f"*Generated {report['generated_at']} · {report['horizon_days']}-day horizon*",
        "",
        "## Price outlook (btc / eth / sol)",
        "",
        "| Asset | Price now | Likely range | Chance up |",
        "|-------|-----------|--------------|-----------|",
    ]
    for p in report["predictions"]:
        lines.append(
            f"| {p['asset'].upper()} | ${p['spot']:,.0f} "
            f"| ${p['low_p10']:,.0f} – ${p['high_p90']:,.0f} "
            f"| {p['prob_up']:.0%} |"
        )
    stale = report["predictions"][0]["as_of"] if report["predictions"] else "?"
    lines += [
        "",
        f"*Range is the 10th–90th percentile of {report['horizon_days']}-day "
        f"Monte Carlo paths. Based on prices through {stale}.*",
        "",
        "## Polymarket signals",
        "",
    ]

    sigs = report["polymarket_signals"]
    if not sigs:
        lines.append("_No live crypto markets we can price right now._")
    elif len(sigs) == 1 and "error" in sigs[0]:
        lines.append(f"_{sigs[0]['error']}_")
    else:
        # Show only the bets worth acting on (biggest edges first). The full list —
        # including "no bet" markets — is in outlook_latest.json for the frontend.
        actionable = [s for s in sigs if s["action"] != "no bet"]
        top = actionable[:15]
        lines += [
            f"Showing the top {len(top)} of {len(actionable)} actionable markets "
            f"({len(sigs)} priced in total — see the JSON for all).",
            "",
            "| Market | Our prob | Market prob | Edge | Action | Bet |",
            "|--------|----------|-------------|------|--------|-----|",
        ]
        for s in top:
            bet = f"${s.get('bet_dollars', 0):,.0f}"
            q = s["question"] if len(s["question"]) <= 50 else s["question"][:47] + "..."
            lines.append(
                f"| {q} | {s['our_probability']:.0%} | {s['market_probability']:.0%} "
                f"| {s['edge']:+.0%} | {s['action']} | {bet} |"
            )
        lines += [
            "",
            f"*Bet sizes assume a ${report['bankroll']:,.0f} bankroll, quarter-Kelly. "
            "This is not cleared for real money — see the gates in trading/.*",
        ]

    lines.append("")
    return "\n".join(lines)


def main():
    REPORTS_DIR.mkdir(exist_ok=True)
    report = build_report()

    (REPORTS_DIR / "outlook_latest.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (REPORTS_DIR / "outlook_latest.md").write_text(
        to_markdown(report), encoding="utf-8"
    )
    print(f"wrote {REPORTS_DIR / 'outlook_latest.md'}")
    print(f"wrote {REPORTS_DIR / 'outlook_latest.json'}")


if __name__ == "__main__":
    main()

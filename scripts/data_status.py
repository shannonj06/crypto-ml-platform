"""
One health report for every dataset in Database/.

With this many sources, the failure that actually hurts isn't a crashed job —
it's a source that quietly stops updating while everything stays green. This
prints how fresh each file is, as a Markdown table, so the GitHub Actions run
summary shows it on every run.

    python -m scripts.data_status              # human-readable
    python -m scripts.data_status --markdown   # for $GITHUB_STEP_SUMMARY
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "Database"

# The file the prediction engine actually reads. Stale here means every
# forecast and every Polymarket edge is wrong, so it gets its own threshold.
CRITICAL = "Crypto_ML_Dataset.csv"
CRITICAL_MAX_AGE_DAYS = 3
DEFAULT_MAX_AGE_DAYS = 7

DATE_COLUMNS = ("date", "timestamp", "time", "Date", "day")


def _last_date(df: pd.DataFrame):
    """Newest date in whichever column holds one, or None."""
    for col in DATE_COLUMNS:
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce", utc=True).dropna()
            if not parsed.empty:
                return parsed.max().tz_convert(None)
    return None


def survey() -> list[dict]:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    rows = []

    for path in sorted(DATA_DIR.glob("*.csv")):
        row = {
            "file": path.name,
            "rows": None,
            "last": None,
            "age": None,
            "limit": CRITICAL_MAX_AGE_DAYS if path.name == CRITICAL else DEFAULT_MAX_AGE_DAYS,
            "status": "ok",
            "note": "",
        }
        try:
            df = pd.read_csv(path, low_memory=False)
            row["rows"] = len(df)
            last = _last_date(df)
            if last is None:
                row["status"] = "unknown"
                row["note"] = "no date column"
            else:
                row["last"] = last.date()
                row["age"] = int((today - last.normalize()).days)
                if row["age"] > row["limit"]:
                    row["status"] = "stale"
        except Exception as exc:  # unreadable file shouldn't hide the others
            row["status"] = "error"
            row["note"] = str(exc)[:80]
        rows.append(row)

    if not any(r["file"] == CRITICAL for r in rows):
        rows.append({
            "file": CRITICAL, "rows": None, "last": None, "age": None,
            "limit": CRITICAL_MAX_AGE_DAYS, "status": "missing",
            "note": "the engine cannot run without this",
        })
    return rows


MARKS = {"ok": "ok", "stale": "STALE", "missing": "MISSING", "error": "ERROR", "unknown": "?"}


def render(rows: list[dict], markdown: bool) -> str:
    if markdown:
        out = ["| Dataset | Rows | Last date | Age | Status |", "|---|---:|---|---:|---|"]
        for r in rows:
            age = "—" if r["age"] is None else f"{r['age']}d"
            note = f" — {r['note']}" if r["note"] else ""
            out.append(
                f"| `{r['file']}` | {r['rows'] or '—'} | {r['last'] or '—'} | {age} "
                f"| {MARKS[r['status']]}{note} |"
            )
        return "\n".join(out)

    width = max(len(r["file"]) for r in rows)
    out = []
    for r in rows:
        age = "—" if r["age"] is None else f"{r['age']}d old"
        out.append(
            f"{r['file']:<{width}}  {str(r['rows'] or '—'):>6} rows  "
            f"last {str(r['last'] or '—'):>10}  {age:>9}  {MARKS[r['status']]} {r['note']}"
        )
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--markdown", action="store_true", help="emit a Markdown table")
    ap.add_argument(
        "--strict",
        action="store_true",
        help=f"exit non-zero if {CRITICAL} is stale or missing",
    )
    args = ap.parse_args()

    rows = survey()
    print(render(rows, args.markdown))

    critical = next((r for r in rows if r["file"] == CRITICAL), None)
    if args.strict and critical and critical["status"] in ("stale", "missing", "error"):
        print(
            f"\n{CRITICAL} is {critical['status']} "
            f"(limit {CRITICAL_MAX_AGE_DAYS} days) — predictions would be meaningless.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

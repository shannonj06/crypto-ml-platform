import os
import warnings
from dataclasses import replace

import numpy as np
import pandas as pd

from trading_config import Costs, Sizing, Signal
from polytrading_signals import (
    THE_GATES,
    assert_clear_to_trade_real,
    edge,
    decide,
    effective_cost,
    full_kelly,
    trade_pnl,
)

# ---------------------------------------------------------------------------
# Walk-forward backtest
# ---------------------------------------------------------------------------

def _scale_for_total_exposure(sizes: np.ndarray, cap: float) -> np.ndarray:
    """Proportionally shrink a batch of stakes so their sum respects `cap`."""
    total = sizes.sum()
    if total > cap and total > 0:
        return sizes * (cap / total)
    return sizes


def walk_forward(df: pd.DataFrame, tau: float, costs: Costs, sizing: Sizing,
                 start_bankroll: float = 1.0) -> dict:
    """
    Replay questions in date order. Bets opened on a date are sized off the
    bankroll at the start of that date (no peeking at same-day results), with a
    per-date total-exposure cap, then resolved and compounded.

    df needs columns: date, prob (P_model), market_prob (P_market), outcome.
    Returns metrics plus the per-bet ledger and the equity curve.
    """
    required = {"date", "prob", "market_prob", "outcome"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(f"walk_forward missing columns: {sorted(missing)}")

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date", kind="mergesort").reset_index(drop=True)

    bankroll = start_bankroll
    equity   = [bankroll]
    ledger   = []

    for date, day in d.groupby("date", sort=True):
        signals = [decide(r.prob, r.market_prob, tau, costs, sizing)
                   for r in day.itertuples()]
        sizes = np.array([s.size for s in signals])
        sizes = _scale_for_total_exposure(sizes, sizing.max_total_exposure)

        day_pnl = 0.0
        for (r, sig, size) in zip(day.itertuples(), signals, sizes):
            if size <= 0:
                continue
            stake = size * bankroll
            pnl   = trade_pnl(replace(sig, size=size), int(r.outcome), stake, costs)
            day_pnl += pnl
            ledger.append({
                "date":     date,
                "side":     sig.side,
                "p_model":  r.prob,
                "p_market": r.market_prob,
                "edge":     sig.edge,
                "net_edge": sig.net_edge,
                "size":     size,
                "stake":    stake,
                "outcome":  int(r.outcome),
                "won":      int((r.outcome == 1) if sig.side == "YES" else (r.outcome == 0)),
                "ret":      pnl / stake if stake > 0 else 0.0,
                "pnl":      pnl,
            })

        bankroll += day_pnl
        equity.append(bankroll)
        if bankroll <= 0:
            warnings.warn("Bankroll wiped out — stopping walk-forward.", stacklevel=2)
            break

    ledger_df  = pd.DataFrame(ledger)
    equity_arr = np.array(equity)
    return {
        **_metrics(ledger_df, equity_arr, start_bankroll),
        "ledger": ledger_df,
        "equity": equity_arr,
    }


def _max_drawdown(equity: np.ndarray) -> float:
    """Largest peak-to-trough fractional drop of the equity curve."""
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float(((peak - equity) / peak).max())


def _metrics(ledger: pd.DataFrame, equity: np.ndarray, start_bankroll: float) -> dict:
    if ledger.empty:
        return {"n_bets": 0, "final_bankroll": float(equity[-1]),
                "total_return": float(equity[-1] / start_bankroll - 1.0),
                "hit_rate": float("nan"), "sharpe": float("nan"),
                "max_drawdown": _max_drawdown(equity), "avg_edge": float("nan"),
                "taken_brier": float("nan")}

    rets = ledger["ret"].to_numpy()
    # Per-bet Sharpe (unannualized — bets span mixed horizons; treat as risk per bet).
    sd = rets.std(ddof=1) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / sd) if sd > 0 else float("nan")

    # Calibration of the bets we ACTUALLY took: Brier of P(side wins) vs win.
    side_win_prob = np.where(ledger["side"] == "YES",
                             ledger["p_model"], 1.0 - ledger["p_model"]).astype(float)
    taken_brier = float(np.mean((side_win_prob - ledger["won"]) ** 2))

    return {
        "n_bets":         int(len(ledger)),
        "final_bankroll": float(equity[-1]),
        "total_return":   float(equity[-1] / start_bankroll - 1.0),
        "hit_rate":       float(ledger["won"].mean()),
        "sharpe":         sharpe,
        "max_drawdown":   _max_drawdown(equity),
        "avg_edge":       float(ledger["edge"].abs().mean()),
        "taken_brier":    taken_brier,
    }


# ---------------------------------------------------------------------------
# Dumb baselines — a strategy that can't beat these isn't a strategy.
# ---------------------------------------------------------------------------

def _fixed_size_backtest(df: pd.DataFrame, side_fn, costs: Costs, sizing: Sizing,
                         start_bankroll: float = 1.0) -> dict:
    """Shared engine for baselines: side chosen by `side_fn(row, rng)`, flat sizing."""
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date", kind="mergesort").reset_index(drop=True)
    rng = np.random.default_rng(0)

    bankroll = start_bankroll
    equity   = [bankroll]
    ledger   = []
    for date, day in d.groupby("date", sort=True):
        day_pnl = 0.0
        rows  = list(day.itertuples())
        sizes = _scale_for_total_exposure(
            np.full(len(rows), sizing.max_position), sizing.max_total_exposure)
        for r, size in zip(rows, sizes):
            side = side_fn(r, rng)
            if side is None:
                continue
            eff   = effective_cost(r.market_prob, side, costs)
            sig   = Signal(side, edge(r.prob, r.market_prob), 0.0, size, r.market_prob, eff)
            stake = size * bankroll
            pnl   = trade_pnl(sig, int(r.outcome), stake, costs)
            day_pnl += pnl
            ledger.append({"date": date, "side": side, "p_model": r.prob,
                           "p_market": r.market_prob, "edge": sig.edge,
                           "net_edge": 0.0, "size": size, "stake": stake,
                           "outcome": int(r.outcome),
                           "won": int((r.outcome == 1) if side == "YES" else (r.outcome == 0)),
                           "ret": pnl / stake if stake > 0 else 0.0, "pnl": pnl})
        bankroll += day_pnl
        equity.append(bankroll)
        if bankroll <= 0:
            break
    ledger_df = pd.DataFrame(ledger)
    return {**_metrics(ledger_df, np.array(equity), start_bankroll),
            "ledger": ledger_df, "equity": np.array(equity)}


def baseline_favorite(df, costs, sizing, start_bankroll=1.0):
    """Always buy the market's favourite (the side priced above 0.50)."""
    return _fixed_size_backtest(
        df, lambda r, rng: "YES" if r.market_prob >= 0.5 else "NO",
        costs, sizing, start_bankroll)


def baseline_random(df, costs, sizing, start_bankroll=1.0):
    """Coin-flip the side on every question."""
    return _fixed_size_backtest(
        df, lambda r, rng: "YES" if rng.random() < 0.5 else "NO",
        costs, sizing, start_bankroll)


# ---------------------------------------------------------------------------
# Market price source
# ---------------------------------------------------------------------------

def synthesize_market(df: pd.DataFrame, shrink: float = 0.85, noise_sd: float = 0.03,
                      seed: int = 7) -> pd.Series:
    """
    STAND-IN ONLY — not a real market.

    Real deployment must replace this with actual Polymarket (or other venue)
    quotes aligned to each question. This synthetic market is the model's own
    probability shrunk toward 0.5 plus mean-zero noise, i.e. it deliberately
    *under-reacts* in the tails so the pipeline has a recoverable edge to trade
    against. It exists to exercise the machinery, NOT to estimate live P&L.
    """
    warnings.warn(
        "Using SYNTHETIC market prices (synthesize_market). Backtest P&L is a "
        "pipeline smoke-test, NOT an estimate of live edge. Gates remain unmet.",
        stacklevel=2,
    )
    rng = np.random.default_rng(seed)
    p   = df["prob"].to_numpy()
    q   = 0.5 + (p - 0.5) * shrink + rng.normal(0.0, noise_sd, size=len(p))
    return pd.Series(np.clip(q, 0.02, 0.98), index=df.index, name="market_prob")


def load_questions(path: str) -> pd.DataFrame:
    """Load backtest_*.csv and attach a market_prob column (synthetic if absent)."""
    df = pd.read_csv(path)
    if "market_prob" not in df.columns:
        df["market_prob"] = synthesize_market(df)
    return df


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt(res: dict) -> str:
    return (f"  bets={res['n_bets']:>4}  final={res['final_bankroll']:.4f}  "
            f"ret={res['total_return']:+.2%}  hit={res['hit_rate']:.3f}  "
            f"sharpe={res['sharpe']:.3f}  maxDD={res['max_drawdown']:.2%}  "
            f"taken_brier={res['taken_brier']:.4f}")


def report(df: pd.DataFrame, tau: float, costs: Costs, sizing: Sizing) -> dict:
    strat = walk_forward(df, tau, costs, sizing)
    fav   = baseline_favorite(df, costs, sizing)
    rand  = baseline_random(df, costs, sizing)

    print(f"\n  tau={tau}  costs={costs}\n  sizing={sizing}\n")
    print("  STRATEGY (edge + fractional Kelly):")
    print(_fmt(strat))
    print("  BASELINE always-favourite:")
    print(_fmt(fav))
    print("  BASELINE random:")
    print(_fmt(rand))
    return {"strategy": strat, "favorite": fav, "random": rand}


# ---------------------------------------------------------------------------
# Demo / smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import unittest

    print("=" * 78)
    print("Section 5 — probabilities -> trading signals")
    print(THE_GATES)
    print("=" * 78)

    costs  = Costs()
    sizing = Sizing()

    # Single-signal illustration.
    print("\n--- single signal examples ---")
    for p_model, p_market in [(0.70, 0.55), (0.55, 0.54), (0.30, 0.50), (0.90, 0.88)]:
        sig = decide(p_model, p_market, tau=0.03, costs=costs, sizing=sizing)
        action = f"{sig.side} @ {sig.size:.3%}" if sig.acts else "no action"
        print(f"  P_model={p_model:.2f}  P_market={p_market:.2f}  "
              f"edge={sig.edge:+.2f}  net={sig.net_edge:+.3f}  -> {action}")

    # Walk-forward on the holdout questions (synthetic market — see warning).
    here = os.path.dirname(os.path.abspath(__file__))
    holdout_path = os.path.join(here, "backtest_holdout.csv")
    if os.path.exists(holdout_path):
        print("\n--- walk-forward backtest on HOLDOUT (synthetic market) ---")
        questions = load_questions(holdout_path)
        report(questions, tau=0.03, costs=costs, sizing=sizing)
    else:
        print(f"\n(skipping backtest — {holdout_path} not found; run backtest.py first)")

    # Gate check is a hard stop until both conditions are signed off.
    print("\n--- real-capital gate check ---")
    try:
        assert_clear_to_trade_real()
        print("  CLEAR to trade real capital.")
    except RuntimeError as e:
        print("  " + str(e).splitlines()[0])

    print("\n=== unit tests ===\n")

    class TestSignals(unittest.TestCase):
        C = Costs(fee_rate=0.0, half_spread=0.01, slippage=0.005, resolution_risk=0.0)
        S = Sizing(kelly_fraction=0.25, max_position=0.05, max_total_exposure=0.20)

        def test_edge_sign(self):
            self.assertGreater(edge(0.7, 0.5), 0)
            self.assertLess(edge(0.3, 0.5), 0)

        def test_no_edge_no_bet(self):
            # Equal probs: cost-adjusted edge is negative, must not act.
            self.assertFalse(decide(0.5, 0.5, 0.0, self.C, self.S).acts)

        def test_side_selection(self):
            self.assertEqual(decide(0.8, 0.5, 0.02, self.C, self.S).side, "YES")
            self.assertEqual(decide(0.2, 0.5, 0.02, self.C, self.S).side, "NO")

        def test_threshold_gates(self):
            # Tiny gross edge that costs eat -> no action under a real tau.
            self.assertFalse(decide(0.555, 0.55, 0.03, self.C, self.S).acts)
            # Big edge clears it.
            self.assertTrue(decide(0.75, 0.55, 0.03, self.C, self.S).acts)

        def test_fractional_below_full_kelly(self):
            sig = decide(0.9, 0.55, 0.02, self.C, self.S)
            eff = effective_cost(0.55, "YES", self.C)
            self.assertLess(sig.size, full_kelly(0.9, eff))

        def test_position_cap(self):
            sig = decide(0.99, 0.50, 0.0, self.C, self.S)
            self.assertLessEqual(sig.size, self.S.max_position + 1e-12)

        def test_costs_kill_marginal_edge(self):
            cheap = Costs(0, 0.0, 0.0, 0.0)
            dear  = Costs(0, 0.05, 0.03, 0.0)
            self.assertTrue(decide(0.60, 0.55, 0.0, cheap, self.S).acts)
            self.assertFalse(decide(0.60, 0.55, 0.0, dear, self.S).acts)

        def test_pnl_win_and_loss(self):
            sig  = decide(0.8, 0.5, 0.02, self.C, self.S)  # YES, eff_cost ~0.515
            win  = trade_pnl(sig, 1, 100.0, self.C)
            loss = trade_pnl(sig, 0, 100.0, self.C)
            self.assertAlmostEqual(loss, -100.0, places=6)       # lose the stake
            self.assertAlmostEqual(win, 100.0 / sig.eff_cost - 100.0, places=6)

        def test_total_exposure_cap(self):
            sizes  = np.array([0.05, 0.05, 0.05, 0.05, 0.05])    # sums to 0.25
            scaled = _scale_for_total_exposure(sizes, 0.20)
            self.assertAlmostEqual(scaled.sum(), 0.20, places=9)

        def test_walk_forward_runs(self):
            grid = np.linspace(0.2, 0.9, 20)
            df = pd.DataFrame({
                "date":        pd.date_range("2025-01-01", periods=20, freq="7D"),
                "prob":        grid,
                "market_prob": np.clip(grid - 0.05, 0.02, 0.98),
                "outcome":     (grid > 0.5).astype(int),
            })
            res = walk_forward(df, tau=0.0, costs=self.C, sizing=self.S)
            self.assertEqual(len(res["equity"]), df["date"].nunique() + 1)
            self.assertIn("max_drawdown", res)

    suite  = unittest.TestLoader().loadTestsFromTestCase(TestSignals)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

import numpy as np
import pandas as pd

from feature_engineering import crypto_data, HOLDOUT_CUTOFF
from monte_carlo.monte_carlo import _block_bootstrap_paths, DEFAULT_BLOCK_LEN

ASSETS       = ["btc", "eth", "sol"]
HORIZONS     = [7, 20]
STRIKE_MULTS = [0.90, 0.95, 1.00, 1.05, 1.10]
WARMUP       = 200          # rows of history needed before the first question
N_SIMS       = 10_000       # plenty for a calibration estimate


def backtest_asset(asset, horizon, start_pos, end_pos, n_sims=N_SIMS, seed=42):
    """Replay one asset/horizon. t steps by `horizon` -> non-overlapping windows."""
    close   = crypto_data[f"{asset}_close"].dropna()
    rng     = np.random.default_rng(seed)
    records = []

    for i in range(start_pos, end_pos, horizon):
        hist    = close.iloc[: i + 1]                       # prices <= t
        S0      = hist.iloc[-1]
        returns = np.log(hist / hist.shift(1)).dropna().to_numpy()

        ret_paths = _block_bootstrap_paths(returns, horizon, n_sims, DEFAULT_BLOCK_LEN, rng)
        terminal  = S0 * np.exp(ret_paths.sum(axis=1))      # terminal price per sim

        actual = close.iloc[i + horizon]                    # resolution (allowed to look forward)
        for m in STRIKE_MULTS:
            K = S0 * m
            records.append({
                "asset":   asset,
                "horizon": horizon,
                "date":    close.index[i],
                "mult":    m,
                "prob":    float((terminal > K).mean()),
                "outcome": int(actual > K),
            })
    return records


def score(df):
    """Brier, log loss, base rate, and calibration slope/intercept for one slice."""
    p = df["prob"].to_numpy()
    y = df["outcome"].to_numpy()
    pc = np.clip(p, 1e-15, 1 - 1e-15)

    base  = y.mean()
    slope, intercept = np.polyfit(p, y, 1)          # observed ~ slope*pred + intercept
    return {
        "n":            len(y),
        "brier":        np.mean((p - y) ** 2),
        "log_loss":     -np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)),
        "brier_0.50":   np.mean((0.5 - y) ** 2),    # baseline: always 0.50
        "brier_base":   np.mean((base - y) ** 2),   # baseline: predict the base rate
        "base_rate":    base,
        "cal_slope":    slope,                       # ideal 1.0
        "cal_intercept": intercept,                  # ideal 0.0
    }


def reliability(df, n_bins=10):
    """Binned predicted prob vs observed frequency."""
    p = df["prob"].to_numpy()
    y = df["outcome"].to_numpy()
    edges = np.linspace(0, 1, n_bins + 1)
    idx   = np.clip(np.digitize(p, edges) - 1, 0, n_bins - 1)

    rows = []
    for b in range(n_bins):
        mask = idx == b
        if mask.any():
            rows.append({
                "bin":       f"{edges[b]:.1f}-{edges[b+1]:.1f}",
                "mean_pred": p[mask].mean(),
                "obs_freq":  y[mask].mean(),
                "n":         int(mask.sum()),
            })
    return pd.DataFrame(rows)


def save_reliability_plot(rel, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping reliability plot.")
        return
    plt.figure(figsize=(5, 5))
    plt.plot([0, 1], [0, 1], "--", color="gray", label="perfect")
    plt.plot(rel["mean_pred"], rel["obs_freq"], "o-", label="engine")
    plt.xlabel("Mean predicted probability")
    plt.ylabel("Observed frequency")
    plt.title("Reliability diagram")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    print(f"Saved reliability plot to {path}")


def run(label, start_fn, end_fn):
    """start_fn/end_fn map (close series, holdout position, horizon) -> t-position bounds."""
    all_records = []
    for asset in ASSETS:
        close = crypto_data[f"{asset}_close"].dropna()
        holdout_pos = close.index.searchsorted(HOLDOUT_CUTOFF)
        for horizon in HORIZONS:
            start = start_fn(close, holdout_pos, horizon)
            end   = end_fn(close, holdout_pos, horizon)
            all_records += backtest_asset(asset, horizon, start, end)

    df = pd.DataFrame(all_records)

    print(f"\n=== {label}: scores by asset / horizon ===\n")
    summary = []
    for (asset, horizon), grp in df.groupby(["asset", "horizon"]):
        s = score(grp)
        s.update({"asset": asset, "horizon": horizon})
        summary.append(s)
    summary.append({**score(df), "asset": "ALL", "horizon": "-"})
    summary_df = pd.DataFrame(summary).round(4)
    cols = ["asset", "horizon", "n", "brier", "brier_0.50", "brier_base",
            "log_loss", "base_rate", "cal_slope", "cal_intercept"]
    print(summary_df[cols].to_string(index=False))

    print(f"\n=== {label}: reliability (all questions pooled) ===\n")
    rel = reliability(df)
    print(rel.round(4).to_string(index=False))
    return df, summary_df, rel


if __name__ == "__main__":
    # TRAIN: t from WARMUP, and t+horizon must resolve before the holdout starts.
    train_df, train_summary, train_rel = run(
        "TRAIN",
        start_fn=lambda close, hp, h: WARMUP,
        end_fn=lambda close, hp, h: hp - h,
    )
    train_df.to_csv("backtest_train.csv", index=False)
    save_reliability_plot(train_rel, "reliability_train.png")

    # HOLDOUT: frozen final number. t in [holdout, end-horizon]; history <= t may
    # include train data (that's legitimate, not leakage).
    holdout_df, holdout_summary, holdout_rel = run(
        "HOLDOUT (frozen — final number)",
        start_fn=lambda close, hp, h: hp,
        end_fn=lambda close, hp, h: len(close) - h,
    )
    holdout_df.to_csv("backtest_holdout.csv", index=False)
    save_reliability_plot(holdout_rel, "reliability_holdout.png")

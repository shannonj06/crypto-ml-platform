import numpy as np
import pandas as pd


def _score_pair(forecast, realized, n):
    """Metrics for one aligned (forecast, realized) pair. All vols annualized."""
    forecast = forecast.astype(float).clip(lower=1e-8)
    realized = realized.astype(float)
    error = forecast - realized

    # Regime hit: did the model call above/below-median vol correctly?
    forecast_high = forecast > forecast.median()
    realized_high = realized > realized.median()

    return {
        "n": n,
        "MAE": np.mean(np.abs(error)),
        "RMSE": np.sqrt(np.mean(error ** 2)),
        # QLIKE: lower is better; heavily punishes underestimating realized vol.
        "QLIKE": np.mean(np.log(forecast ** 2) + (realized ** 2) / (forecast ** 2)),
        "bias": np.mean(error),                         # +/- => over/under forecast
        "corr": forecast.corr(realized),
        "regime_accuracy": np.mean(forecast_high == realized_high),
    }

def score_volatility_forecasts(results_df, target_cols=None):
    if target_cols is None:
        target_cols = [c for c in results_df.columns if c.startswith("realized")]
    if not target_cols:
        raise ValueError(
            "No realized-vol target columns found. Pass target_cols=[...] or name "
            "your answer-key columns 'realized_*' (e.g. realized_gk, realized_park)."
        )

    rows = []
    for (asset, horizon, method), group in results_df.groupby(["asset", "horizon", "method"]):
        for target in target_cols:
            pair = group.dropna(subset=["forecast_vol", target])
            if len(pair) == 0:
                continue
            rows.append({
                "asset": asset,
                "horizon": horizon,         /
                "method": method,
                "target": target,
                **_score_pair(pair["forecast_vol"], pair[target], len(pair)),
            })

    summary = pd.DataFrame(rows)
    return summary.sort_values(
        ["target", "horizon", "QLIKE", "RMSE", "MAE"],
        ascending=True,
    ).reset_index(drop=True)

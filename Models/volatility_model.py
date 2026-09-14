import numpy as np
from pathlib import Path
from feature_engineering import feature_df, crypto_data
import pandas as pd
from scipy import stats

def get_log_returns():
    # feature_df already has {ticker}_return_1d = log(close_t / close_{t-1}), identical to log returns
    tickers = ['btc', 'sol', 'eth']
    for i in tickers:
        feature_df[f"{i}_log_returns"] = feature_df[f"{i}_return_1d"]
def add_forward_vol_target(df, ticker, horizon=7, annualization=365):
    log_return = df[f"{ticker}_log_returns"]
    fwd = pd.DataFrame(index=df.index)
    for i in range(1, horizon + 1):
        fwd[i] = log_return.shift(-i)
    complete = fwd.notna().all(axis=1)
    daily_vol = np.sqrt((fwd ** 2).mean(axis=1)).where(complete)
    return daily_vol * np.sqrt(annualization)


def add_parkinson_fwd_vol(df, raw_df, ticker, horizon=7, annualization=365):
    """
    Forward realized vol using daily Parkinson variance: (ln(H/L))^2 / (4*ln(2)).
    ~5x more efficient per day than close-to-close squared returns.
    """
    park_var = (np.log(raw_df[f"{ticker}_high"] / raw_df[f"{ticker}_low"]) ** 2) / (4 * np.log(2))
    fwd = pd.DataFrame(index=raw_df.index)
    for i in range(1, horizon + 1):
        fwd[i] = park_var.shift(-i)
    complete = fwd.notna().all(axis=1)
    vol = np.sqrt(fwd.mean(axis=1)).where(complete) * np.sqrt(annualization)
    df[f"{ticker}_fwd_park_vol_{horizon}d"] = vol.reindex(df.index)
    return df


def add_gk_fwd_vol(df, raw_df, ticker, horizon=7, annualization=365):
    """
    Forward realized vol using Garman-Klass variance: uses O/H/L/C.
    GK = 0.5*(ln(H/L))^2 - (2*ln(2)-1)*(ln(C/O))^2
    Skipped silently if open prices are absent.
    """
    if f"{ticker}_open" not in raw_df.columns:
        return df
    h, l = raw_df[f"{ticker}_high"], raw_df[f"{ticker}_low"]
    c, o = raw_df[f"{ticker}_close"], raw_df[f"{ticker}_open"]
    gk_var = (0.5 * np.log(h / l) ** 2 - (2 * np.log(2) - 1) * np.log(c / o) ** 2).clip(lower=0)
    fwd = pd.DataFrame(index=raw_df.index)
    for i in range(1, horizon + 1):
        fwd[i] = gk_var.shift(-i)
    complete = fwd.notna().all(axis=1)
    vol = np.sqrt(fwd.mean(axis=1)).where(complete) * np.sqrt(annualization)
    df[f"{ticker}_fwd_gk_vol_{horizon}d"] = vol.reindex(df.index)
    return df

#naive training
def add_trailing_vol_baselines(df, ticker, windows=[5, 7, 14, 20, 30], annualization=365):
    r = df[f"{ticker}_log_returns"]
    for window in windows:
        col = f"{ticker}_trailing_vol_{window}d"
        df[col] = (
            np.sqrt(r.pow(2).rolling(window).mean())
            * np.sqrt(annualization)
        )
    return df

def add_ewma_vol(df, ticker, lambda_=0.94, annualization=365):
    r = df[f"{ticker}_log_returns"]
    ewma_variance = r.pow(2).ewm(
        alpha=1 - lambda_,
        adjust=False
    ).mean()
    df[f"{ticker}_ewma_vol"] = (
        np.sqrt(ewma_variance)
        * np.sqrt(annualization)
    )
    return df

from arch import arch_model

# Default spec is GJR-GARCH(1,1,1) with Student-t errors and a constant mean.
# vs. the old Normal GARCH(1,1)/zero-mean this buys two things that matter for crypto:
#   - dist="t": fat tails, so the model stops systematically under-forecasting after shocks
#   - o=1     : leverage/asymmetry, vol reacts more to down moves than up moves (GJR term)
GARCH_DEFAULTS = dict(mean="Constant", vol="GARCH", p=1, o=1, q=1, dist="t")

# Small candidate set for AIC-based selection (used only when select_best=True).
GARCH_CANDIDATES = [
    dict(mean="Constant", vol="GARCH",  p=1, o=0, q=1, dist="normal"),  # the old baseline
    dict(mean="Constant", vol="GARCH",  p=1, o=0, q=1, dist="t"),
    dict(mean="Constant", vol="GARCH",  p=1, o=1, q=1, dist="t"),       # GJR-t (default)
    dict(mean="Constant", vol="EGARCH", p=1, o=1, q=1, dist="skewt"),
]


def _forecast_from_fit(fitted, horizon, annualization):
    # fitted on returns*100, so variance is in percent^2 -> divide by 100^2 to get decimals.
    fc = fitted.forecast(horizon=horizon, reindex=False)
    future_variances = fc.variance.iloc[-1].to_numpy() / (100 ** 2)
    # Target is RMS-style vol: sqrt(mean of future daily variances), then annualize.
    daily_vol = np.sqrt(np.mean(future_variances))
    return daily_vol * np.sqrt(annualization)


def garch_forecast_single_window(returns, horizon=7, annualization=365,
                                 select_best=False, **spec):
    """
    Fit one GARCH-family model on `returns` and forecast annualized vol over `horizon`.

    spec overrides GARCH_DEFAULTS (e.g. o=0 for plain GARCH, dist="normal").
    select_best=True instead fits GARCH_CANDIDATES and keeps the lowest-AIC model.
    """
    returns = returns.dropna()
    # arch fits are far better conditioned when returns are in percent form.
    returns_percent = returns * 100

    if select_best:
        best_fit, best_aic = None, np.inf
        for cand in GARCH_CANDIDATES:
            try:
                f = arch_model(returns_percent, rescale=False, **cand).fit(disp="off")
                if f.aic < best_aic:
                    best_fit, best_aic = f, f.aic
            except Exception:
                continue
        if best_fit is None:
            raise RuntimeError("all GARCH candidates failed to fit")
        return _forecast_from_fit(best_fit, horizon, annualization)

    cfg = {**GARCH_DEFAULTS, **spec}
    fitted = arch_model(returns_percent, rescale=False, **cfg).fit(disp="off")
    return _forecast_from_fit(fitted, horizon, annualization)


def add_walk_forward_garch(df, ticker, train_window=365, horizon=7, annualization=365,
                           refit_every=1, select_best=False, **spec):
    """
    Walk-forward GARCH vol forecast written to `{ticker}_garch_vol_{horizon}d`.

    refit_every>1 re-estimates params only every N steps and carries the forecast
    forward in between (much faster with the heavier t/GJR spec; refit_every=1 keeps
    the original daily-refit behaviour).
    """
    return_col = f"{ticker}_log_returns"
    pred_col = f"{ticker}_garch_vol_{horizon}d"
    df[pred_col] = np.nan
    returns = df[return_col]
    col_idx = df.columns.get_loc(pred_col)

    for i in range(train_window, len(df) - horizon):
        if (i - train_window) % refit_every != 0:
            continue
        # Only use returns up to and including row i (no look-ahead).
        train_returns = returns.iloc[i - train_window + 1 : i + 1]
        try:
            pred_vol = garch_forecast_single_window(
                train_returns, horizon=horizon, annualization=annualization,
                select_best=select_best, **spec,
            )
        except Exception:
            pred_vol = np.nan
        df.iloc[i, col_idx] = pred_vol

    if refit_every > 1:
        # carry each estimate forward only until the next scheduled refit
        df[pred_col] = df[pred_col].ffill(limit=refit_every - 1)
    return df


def add_walk_forward_ml_vol(df, x_cols, ticker, target_col, horizon=7,
                            min_train=365, refit_every=21, model=None):
    """
    Walk-forward ML volatility forecast written to `{ticker}_ml_vol_{horizon}d`,
    so the ML model can be scored side-by-side with GARCH/EWMA/trailing.

    Honest out-of-sample: at prediction day i the model is trained only on rows
    whose forward target was fully realized before day i (the last `horizon` rows
    are embargoed), and features are scaled on the training window only.

    x_cols     : feature columns to use (e.g. ticker_X_cols[ticker])
    target_col : realized-vol target column, e.g. f"{ticker}_fwd_park_vol_{horizon}d"
    refit_every: re-fit the model every N steps; predict every day in between.
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import GradientBoostingRegressor

    if model is None:
        model = GradientBoostingRegressor(random_state=42, n_estimators=300, max_depth=3)

    pred_col = f"{ticker}_ml_vol_{horizon}d"
    df[pred_col] = np.nan
    col_idx = df.columns.get_loc(pred_col)

    X = df[x_cols].to_numpy(dtype=float)
    y = df[target_col].to_numpy(dtype=float)
    row_ok = np.isfinite(X).all(axis=1)

    scaler = None
    for i in range(min_train, len(df) - horizon):
        if (i - min_train) % refit_every == 0:
            # embargo the last `horizon` rows: their target peeks at/after day i
            train_end = i - horizon
            idx = np.where(row_ok[:train_end] & np.isfinite(y[:train_end]))[0]
            if len(idx) < min_train // 2:
                continue
            scaler = StandardScaler().fit(X[idx])
            model.fit(scaler.transform(X[idx]), y[idx])

        if scaler is None or not row_ok[i]:
            continue
        df.iloc[i, col_idx] = float(model.predict(scaler.transform(X[i:i + 1]))[0])

    return df


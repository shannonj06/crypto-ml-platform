import numpy as np
import unittest
import warnings
from feature_engineering import crypto_data

DEFAULT_BLOCK_LEN = 20   # ~1 month; captures volatility clustering
DEFAULT_N_SIMS    = 20_000
CONVERGENCE_SE    = 0.01  # warn if SE exceeds 1%

def _get_log_returns(asset: str) -> np.ndarray:
    close = crypto_data[f"{asset}_close"].dropna()
    return np.log(close / close.shift(1)).dropna().to_numpy()


def _current_price(asset: str) -> float:
    return float(crypto_data[f"{asset}_close"].dropna().iloc[-1])


def _block_bootstrap_paths(
    returns:   np.ndarray,
    horizon:   int,
    n_sims:    int,
    block_len: int,
    rng:       np.random.Generator,
) -> np.ndarray:

    n = len(returns)
    n_blocks = int(np.ceil(horizon / block_len))

    # Block start indices: (n_sims, n_blocks)
    starts = rng.integers(0, n, size=(n_sims, n_blocks))

    # Within-block offsets: (block_len,)
    offsets = np.arange(block_len)

    # Index array: (n_sims, n_blocks, block_len)  → circular via modulo
    indices = (starts[:, :, np.newaxis] + offsets[np.newaxis, np.newaxis, :]) % n

    # Flatten to (n_sims, n_blocks * block_len) and trim to horizon
    sampled = returns[indices.reshape(n_sims, -1)]
    return sampled[:, :horizon]


def price_question(
    asset:         str,
    question_spec: dict,
    horizon:       int,
    n_sims:        int = DEFAULT_N_SIMS,
    block_len:     int = DEFAULT_BLOCK_LEN,
    seed:          int = 42,
) -> float:
    """
    Estimate a probability over price paths using block-bootstrap Monte Carlo.

    Parameters
    ----------
    asset         : 'btc', 'eth', or 'sol'
    question_spec : dict with a 'type' key. Supported types:

        terminal_above   – P(S_T > strike)
            {'type': 'terminal_above', 'strike': K}

        terminal_below   – P(S_T < strike)
            {'type': 'terminal_below', 'strike': K}

        range            – P(A < S_T < B)
            {'type': 'range', 'low': A, 'high': B}

        touch_above      – P(max path > barrier)   [≥ terminal_above]
            {'type': 'touch_above', 'barrier': K}

        touch_below      – P(min path < barrier)   [≥ terminal_below]
            {'type': 'touch_below', 'barrier': K}

        max_drawdown     – P(peak-to-trough drawdown > threshold)
            {'type': 'max_drawdown', 'threshold': X}   # X in (0, 1)

    horizon       : forecast horizon in days
    n_sims        : number of paths (20k → SE_max ≈ 0.35 %; 10k → ≈ 0.5 %)
    block_len     : bootstrap block length in days
    seed          : RNG seed for reproducibility

    Returns
    -------
    float in [0, 1]
    """
    returns = _get_log_returns(asset)
    rng     = np.random.default_rng(seed)
    S0      = _current_price(asset)

    # Return matrix: (n_sims, horizon)
    ret_paths = _block_bootstrap_paths(returns, horizon, n_sims, block_len, rng)

    # Price paths: (n_sims, horizon)  — vectorized compound
    price_paths = S0 * np.exp(np.cumsum(ret_paths, axis=1))

    q_type = question_spec["type"]

    if q_type == "terminal_above":
        hits = price_paths[:, -1] > question_spec["strike"]

    elif q_type == "terminal_below":
        hits = price_paths[:, -1] < question_spec["strike"]

    elif q_type == "range":
        terminal = price_paths[:, -1]
        hits = (terminal > question_spec["low"]) & (terminal < question_spec["high"])

    elif q_type == "touch_above":
        hits = price_paths.max(axis=1) > question_spec["barrier"]

    elif q_type == "touch_below":
        hits = price_paths.min(axis=1) < question_spec["barrier"]

    elif q_type == "max_drawdown":
        running_max = np.maximum.accumulate(price_paths, axis=1)
        max_dd = ((running_max - price_paths) / running_max).max(axis=1)
        hits = max_dd > question_spec["threshold"]

    else:
        raise ValueError(f"Unknown question type: {q_type!r}")

    prob = float(hits.mean())

    # Convergence check: SE = sqrt(p(1-p)/N)
    se = np.sqrt(prob * (1.0 - prob) / n_sims)
    if se > CONVERGENCE_SE:
        warnings.warn(
            f"SE={se:.4f} > {CONVERGENCE_SE} for p={prob:.3f} with n_sims={n_sims}. "
            "Increase n_sims for estimates stable to 1%.",
            stacklevel=2,
        )

    return prob

class TestMonteCarlo(unittest.TestCase):

    # Shared large path batch to avoid re-generating inside each test
    _N = 50_000
    _horizon = 30

    def _terminal_probs_from_synthetic(self, returns, horizon=30, n_sims=50_000, seed=0):
        """Compound zero-based price paths from a custom return array."""
        rng       = np.random.default_rng(seed)
        ret_paths = _block_bootstrap_paths(returns, horizon, n_sims, DEFAULT_BLOCK_LEN, rng)
        terminal  = np.exp(ret_paths.sum(axis=1))   # S0 = 1
        return terminal

    def _btc_paths(self, n_sims=50_000, horizon=30, seed=99):
        rng       = np.random.default_rng(seed)
        returns   = _get_log_returns("btc")
        ret_paths = _block_bootstrap_paths(returns, horizon, n_sims, DEFAULT_BLOCK_LEN, rng)
        S0        = _current_price("btc")
        return S0 * np.exp(np.cumsum(ret_paths, axis=1))   # (n_sims, horizon)

    def test_atm_zero_drift(self):
        """
        Synthetic returns with mean exactly 0.
        P(S_T > S0) should be ≈ 0.50 — within 3 standard errors.
        """
        rng_synth = np.random.default_rng(1)
        raw = rng_synth.normal(0.0, 0.02, 3000)
        raw -= raw.mean()                          # enforce zero mean exactly

        n_sims  = 50_000
        terminal = self._terminal_probs_from_synthetic(raw, n_sims=n_sims)
        prob = (terminal > 1.0).mean()
        se   = np.sqrt(0.25 / n_sims)             # max SE at p = 0.5

        self.assertAlmostEqual(
            prob, 0.5, delta=3 * se,
            msg=f"ATM zero-drift: P(terminal > S0) = {prob:.4f}, expected 0.50 ± {3*se:.4f}",
        )

    def test_touch_geq_terminal(self):
        """
        A touch event fires whenever the price crosses K *at any point*.
        It strictly dominates the terminal event, so P(touch) >= P(terminal).
        """
        paths     = self._btc_paths()
        S0        = _current_price("btc")
        K         = S0 * 1.10                     # 10% above today

        p_touch    = (paths.max(axis=1) > K).mean()
        p_terminal = (paths[:, -1] > K).mean()

        self.assertGreaterEqual(
            p_touch, p_terminal,
            msg=f"P(touch {K:.0f}) = {p_touch:.4f} < P(terminal > {K:.0f}) = {p_terminal:.4f}",
        )

    def test_probability_monotone_in_strike(self):
        """
        Higher strike → fewer paths end above it.
        Checks strict monotonicity across five levels.
        """
        paths       = self._btc_paths()
        S0          = _current_price("btc")
        multipliers = [0.70, 0.85, 1.00, 1.15, 1.30]
        terminal    = paths[:, -1]
        probs       = [(terminal > S0 * m).mean() for m in multipliers]

        for i in range(len(probs) - 1):
            self.assertGreater(
                probs[i], probs[i + 1],
                msg=(
                    f"Monotonicity violated between K={multipliers[i]:.2f}×S0 "
                    f"(p={probs[i]:.4f}) and K={multipliers[i+1]:.2f}×S0 "
                    f"(p={probs[i+1]:.4f})"
                ),
            )

if __name__ == "__main__":
    import sys

    print("=== Monte Carlo demo (BTC, 30-day horizon) ===\n")
    S0 = _current_price("btc")
    cases = [
        ("P(terminal > +10%)",  {"type": "terminal_above", "strike":  S0 * 1.10}),
        ("P(terminal < -10%)",  {"type": "terminal_below", "strike":  S0 * 0.90}),
        ("P(range -5% to +5%)", {"type": "range",          "low":     S0 * 0.95, "high": S0 * 1.05}),
        ("P(touch +20%)",       {"type": "touch_above",    "barrier": S0 * 1.20}),
        ("P(touch -20%)",       {"type": "touch_below",    "barrier": S0 * 0.80}),
        ("P(drawdown > 15%)",   {"type": "max_drawdown",   "threshold": 0.15}),
    ]
    for label, spec in cases:
        p = price_question("btc", spec, horizon=30, n_sims=50_000)
        print(f"  {label:<28}  {p:.4f}")

    print("\n=== Running unit tests ===\n")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMonteCarlo)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    runner.run(suite)

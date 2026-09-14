/**
 * The pricing math, client-side.
 *
 * The backend's engine runs a block-bootstrap Monte Carlo and reports the 10th
 * and 90th percentile of where each price lands. Those two numbers pin down the
 * width of the terminal distribution, so we can re-price an arbitrary threshold
 * here without re-running 10,000 paths in the browser.
 *
 * Log-returns are treated as normal with no drift, which is what the bootstrap
 * produces in aggregate (its prob_up sits at 50–52%). Widths scale with √t.
 */

/** Abramowitz & Stegun 7.1.26. Max error ~1.5e-7. */
function erf(x: number): number {
  const sign = x < 0 ? -1 : 1
  const a = Math.abs(x)
  const t = 1 / (1 + 0.3275911 * a)
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t +
      0.254829592) *
      t *
      Math.exp(-a * a)
  return sign * y
}

export const normalCdf = (z: number): number => 0.5 * (1 + erf(z / Math.SQRT2))

/** The p10–p90 spread of a zero-drift normal spans 2 × 1.2816 standard deviations. */
const P10_P90_SPAN = 2 * 1.2815515655446004

/** Log-return sigma implied by a Monte Carlo run's reported percentile range. */
export function impliedSigma(lowP10: number, highP90: number): number {
  return Math.log(highP90 / lowP10) / P10_P90_SPAN
}

/** Rescale a sigma measured over `fromDays` to a different holding period. */
export function scaleSigma(sigma: number, fromDays: number, toDays: number): number {
  return sigma * Math.sqrt(toDays / fromDays)
}

export type Threshold =
  | { kind: 'above'; level: number }
  | { kind: 'below'; level: number }
  | { kind: 'between'; level: number; upper: number }

/** Probability the price settles inside the threshold, given spot and sigma. */
export function probabilityOf(spec: Threshold, spot: number, sigma: number): number {
  if (sigma <= 0) return 0.5
  const z = (level: number) => Math.log(level / spot) / sigma

  switch (spec.kind) {
    case 'above':
      return 1 - normalCdf(z(spec.level))
    case 'below':
      return normalCdf(z(spec.level))
    case 'between': {
      const lo = Math.min(spec.level, spec.upper)
      const hi = Math.max(spec.level, spec.upper)
      return normalCdf(z(hi)) - normalCdf(z(lo))
    }
  }
}

/** Percentile of the terminal distribution — used to redraw the likely range. */
export function quantile(spot: number, sigma: number, q: number): number {
  // Inverse normal CDF, Acklam's rational approximation (abridged, |error| < 1e-4).
  const a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924]
  const b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857]
  const c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878]
  const d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742]
  const pLow = 0.02425
  let z: number

  if (q < pLow) {
    const s = Math.sqrt(-2 * Math.log(q))
    z = (((((c[0] * s + c[1]) * s + c[2]) * s + c[3]) * s + c[4]) * s + c[5]) /
        ((((d[0] * s + d[1]) * s + d[2]) * s + d[3]) * s + 1)
  } else if (q <= 1 - pLow) {
    const s = q - 0.5
    const r = s * s
    z = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * s /
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
  } else {
    const s = Math.sqrt(-2 * Math.log(1 - q))
    z = -(((((c[0] * s + c[1]) * s + c[2]) * s + c[3]) * s + c[4]) * s + c[5]) /
         ((((d[0] * s + d[1]) * s + d[2]) * s + d[3]) * s + 1)
  }
  return spot * Math.exp(z * sigma)
}

// ---------------------------------------------------------------------------
// Betting math
// ---------------------------------------------------------------------------

export type Side = 'YES' | 'NO'

/** What one side costs per $1 of payout. */
export const priceOf = (side: Side, marketProbability: number) =>
  side === 'YES' ? marketProbability : 1 - marketProbability

/** Our edge measured in the direction we're actually betting. Always ≥ 0 if we bet. */
export const edgeOn = (side: Side, model: number, market: number) =>
  side === 'YES' ? model - market : market - model

export type Ticket = {
  stake: number
  price: number
  shares: number
  /** Profit if the market resolves our way. */
  payoutIfRight: number
  /** Probability-weighted profit, by our own numbers. */
  expectedProfit: number
}

export function ticketFor(
  side: Side,
  model: number,
  market: number,
  stake: number,
): Ticket {
  const price = priceOf(side, market)
  const shares = price > 0 ? stake / price : 0
  const winProbability = side === 'YES' ? model : 1 - model
  return {
    stake,
    price,
    shares,
    payoutIfRight: shares - stake,
    expectedProfit: winProbability * (shares - stake) - (1 - winProbability) * stake,
  }
}

/** Fractional Kelly, matching the backend's quarter-Kelly sizing. */
export function kellyFraction(
  side: Side,
  model: number,
  market: number,
  fraction = 0.25,
  cap = 0.05,
): number {
  const price = priceOf(side, market)
  if (price <= 0 || price >= 1) return 0
  const p = side === 'YES' ? model : 1 - model
  const b = (1 - price) / price
  const full = (p * b - (1 - p)) / b
  return Math.max(0, Math.min(cap, full * fraction))
}

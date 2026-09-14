/**
 * Shaped like the backend's GET /polymarket and GET /predictions responses,
 * seeded with the figures from reports/outlook_latest.md.
 *
 * Edge, side, and bet size are all derived (see lib/stats.ts) rather than
 * stored, so changing the bankroll or the edge buffer moves every number on
 * the page the way it would move on the real desk.
 */

export type Asset = 'btc' | 'eth' | 'sol'

export type Market = {
  id: string
  asset: Asset
  question: string
  horizonDays: number
  closeDate: string
  ourProbability: number
  marketProbability: number
  volumeUsd: number
}

export type Outlook = {
  asset: Asset
  name: string
  spot: number
  lowP10: number
  highP90: number
  probUp: number
}

export const ASSET_NAMES: Record<Asset, string> = {
  btc: 'Bitcoin',
  eth: 'Ethereum',
  sol: 'Solana',
}

/** The engine's own thresholds, mirrored from trading/. */
export const ENGINE = {
  /** Edge buffer. Act only when the cost adjusted edge clears this. */
  tau: 0.03,
  /** Fees plus expected slippage, per unit of probability. */
  costs: 0.01,
  /** Fraction of full Kelly the desk actually sizes to. */
  kellyFraction: 0.25,
  /** Hard cap on any single position, as a share of bankroll. */
  positionCap: 0.05,
}

export const runMeta = {
  generatedAt: '2026-08-11T22:14:54Z',
  pricesThrough: '2026-08-10',
  horizonDays: 7,
  marketsPriced: 133,
  paths: 10000,
  /** Prices older than this many days get flagged as stale in the header. */
  staleAfterDays: 3,
}

export const markets: Market[] = [
  { id: 'btc-dip-62500-aug', asset: 'btc', question: 'Will Bitcoin dip to $62,500 in August?', horizonDays: 7, closeDate: '2026-08-31', ourProbability: 0.27, marketProbability: 0.78, volumeUsd: 412_000 },
  { id: 'sol-dip-50-w', asset: 'sol', question: 'Will Solana dip to $50 the week of August 10?', horizonDays: 6, closeDate: '2026-08-16', ourProbability: 0.004, marketProbability: 0.5, volumeUsd: 88_400 },
  { id: 'sol-dip-60-w', asset: 'sol', question: 'Will Solana dip to $60 the week of August 10?', horizonDays: 6, closeDate: '2026-08-16', ourProbability: 0.012, marketProbability: 0.48, volumeUsd: 96_100 },
  { id: 'eth-dip-1800-aug', asset: 'eth', question: 'Will Ethereum dip to $1,800 in August?', horizonDays: 7, closeDate: '2026-08-31', ourProbability: 0.26, marketProbability: 0.66, volumeUsd: 233_500 },
  { id: 'sol-dip-70-w', asset: 'sol', question: 'Will Solana dip to $70 the week of August 10?', horizonDays: 6, closeDate: '2026-08-16', ourProbability: 0.021, marketProbability: 0.4, volumeUsd: 61_800 },
  { id: 'btc-dip-62000-w', asset: 'btc', question: 'Will Bitcoin dip to $62,000 the week of August 10?', horizonDays: 6, closeDate: '2026-08-16', ourProbability: 0.105, marketProbability: 0.4, volumeUsd: 174_200 },
  { id: 'btc-dip-60000-aug', asset: 'btc', question: 'Will Bitcoin dip to $60,000 in August?', horizonDays: 7, closeDate: '2026-08-31', ourProbability: 0.108, marketProbability: 0.38, volumeUsd: 305_900 },
  { id: 'sol-dip-70-aug', asset: 'sol', question: 'Will Solana dip to $70 in August?', horizonDays: 7, closeDate: '2026-08-31', ourProbability: 0.115, marketProbability: 0.38, volumeUsd: 54_300 },
  { id: 'eth-reach-2000-aug', asset: 'eth', question: 'Will Ethereum reach $2,000 in August?', horizonDays: 7, closeDate: '2026-08-31', ourProbability: 0.31, marketProbability: 0.56, volumeUsd: 519_700 },
  { id: 'eth-dip-1700-aug', asset: 'eth', question: 'Will Ethereum dip to $1,700 in August?', horizonDays: 7, closeDate: '2026-08-31', ourProbability: 0.088, marketProbability: 0.32, volumeUsd: 147_000 },
  { id: 'eth-band-1800-1900', asset: 'eth', question: 'Will Ethereum be between $1,800 and $1,900 on August 15?', horizonDays: 5, closeDate: '2026-08-15', ourProbability: 0.8, marketProbability: 0.6, volumeUsd: 71_600 },
  { id: 'eth-reach-1900-aug', asset: 'eth', question: 'Will Ethereum reach $1,900 in August?', horizonDays: 7, closeDate: '2026-08-31', ourProbability: 0.73, marketProbability: 0.94, volumeUsd: 288_400 },
  { id: 'eth-above-1900', asset: 'eth', question: 'Will Ethereum be above $1,900 on August 15?', horizonDays: 5, closeDate: '2026-08-15', ourProbability: 0.17, marketProbability: 0.37, volumeUsd: 63_200 },
  { id: 'eth-band-1900-2000', asset: 'eth', question: 'Will Ethereum be between $1,900 and $2,000 on August 15?', horizonDays: 5, closeDate: '2026-08-15', ourProbability: 0.17, marketProbability: 0.36, volumeUsd: 44_900 },
  { id: 'sol-band-70-80', asset: 'sol', question: 'Will Solana be between $70 and $80 on August 16?', horizonDays: 6, closeDate: '2026-08-16', ourProbability: 0.96, marketProbability: 0.78, volumeUsd: 39_500 },
  { id: 'btc-above-65000', asset: 'btc', question: 'Will Bitcoin be above $65,000 on August 16?', horizonDays: 6, closeDate: '2026-08-16', ourProbability: 0.38, marketProbability: 0.41, volumeUsd: 226_800 },
  { id: 'eth-above-1850', asset: 'eth', question: 'Will Ethereum be above $1,850 on August 16?', horizonDays: 6, closeDate: '2026-08-16', ourProbability: 0.55, marketProbability: 0.53, volumeUsd: 118_300 },
]

export const outlooks: Outlook[] = [
  { asset: 'btc', name: 'Bitcoin', spot: 63970, lowP10: 61531, highP90: 66656, probUp: 0.52 },
  { asset: 'eth', name: 'Ethereum', spot: 1873, lowP10: 1776, highP90: 1990, probUp: 0.51 },
  { asset: 'sol', name: 'Solana', spot: 76, lowP10: 72, highP90: 81, probUp: 0.5 },
]

export const outlookFor = (asset: Asset) =>
  outlooks.find((o) => o.asset === asset) as Outlook

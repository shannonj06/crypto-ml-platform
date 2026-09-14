import { ENGINE, type Market } from '../data/desk'
import { edgeOn, kellyFraction, ticketFor, type Side, type Ticket } from './stats'

export type Signal = Market & {
  /** Our probability minus the market's. Sign tells you which side is cheap. */
  edge: number
  side: Side
  /** Edge measured in the direction we'd bet — never negative. */
  grossEdge: number
  /** What's left after fees and slippage. This is what has to clear the buffer. */
  netEdge: number
  actionable: boolean
  kelly: number
  stake: number
  ticket: Ticket
}

/**
 * A market is ACTIONABLE when the edge still clears the buffer after costs:
 *
 *     |our probability − market probability| − costs  >  tau
 *
 * Everything else gets priced and logged, but left alone. This mirrors
 * `decide()` in trading/ — the buffer is what stops the desk from trading
 * noise in its own model.
 */
export function evaluate(market: Market, bankroll: number, tau = ENGINE.tau): Signal {
  const edge = market.ourProbability - market.marketProbability
  const side: Side = edge >= 0 ? 'YES' : 'NO'
  const grossEdge = edgeOn(side, market.ourProbability, market.marketProbability)
  const netEdge = grossEdge - ENGINE.costs
  const actionable = netEdge > tau

  const kelly = actionable
    ? kellyFraction(
        side,
        market.ourProbability,
        market.marketProbability,
        ENGINE.kellyFraction,
        ENGINE.positionCap,
      )
    : 0
  const stake = Math.round(kelly * bankroll * 100) / 100

  return {
    ...market,
    edge,
    side,
    grossEdge,
    netEdge,
    actionable,
    kelly,
    stake,
    ticket: ticketFor(side, market.ourProbability, market.marketProbability, stake),
  }
}

export const evaluateAll = (markets: Market[], bankroll: number, tau = ENGINE.tau) =>
  markets
    .map((m) => evaluate(m, bankroll, tau))
    .sort((a, b) => b.netEdge - a.netEdge)

export type Book = {
  actionable: number
  priced: number
  staked: number
  expectedProfit: number
  bestCase: number
  /** Expected return on the capital actually put at risk. */
  expectedReturn: number
}

export function summarize(signals: Signal[]): Book {
  const live = signals.filter((s) => s.actionable)
  const staked = live.reduce((t, s) => t + s.stake, 0)
  const expectedProfit = live.reduce((t, s) => t + s.ticket.expectedProfit, 0)
  const bestCase = live.reduce((t, s) => t + s.ticket.payoutIfRight, 0)

  return {
    actionable: live.length,
    priced: signals.length,
    staked,
    expectedProfit,
    bestCase,
    expectedReturn: staked > 0 ? expectedProfit / staked : 0,
  }
}

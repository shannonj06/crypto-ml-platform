import { Link } from 'react-router-dom'
import { ProbabilityAxis } from '../components/ProbabilityAxis'
import { Badge, Panel, SectionHead, Stat, btn } from '../components/ui'
import { markets, outlooks, runMeta } from '../data/desk'
import { useDesk } from '../lib/desk-state'
import { evaluateAll, summarize } from '../lib/signals'
import { cents, pct, shortDate, signedUsd, usd } from '../lib/format'

/** Where the price is likely to land, on its own scale. */
function RangeBar({ low, spot, high }: { low: number; spot: number; high: number }) {
  const at = (v: number) => `${((v - low) / (high - low)) * 100}%`

  return (
    <div className="relative h-9" aria-hidden>
      <div className="absolute inset-x-0 top-4 h-px bg-accent/40" />
      <div className="absolute top-2 left-0 h-4 w-px bg-line-strong" />
      <div className="absolute top-2 right-0 h-4 w-px bg-line-strong" />
      <div
        className="absolute top-[13px] size-[6px] -translate-x-1/2 rounded-full bg-accent"
        style={{ left: at(spot) }}
      />
      <div className="absolute top-6 flex w-full justify-between font-mono text-micro text-muted">
        <span>{usd(low)}</span>
        <span>{usd(high)}</span>
      </div>
    </div>
  )
}

export function Pricing() {
  const { bankroll, tau } = useDesk()
  const signals = evaluateAll(markets, bankroll, tau)
  const book = summarize(signals)
  const top = signals[0]

  return (
    <div className="space-y-10">
      <section className="grid gap-x-12 gap-y-8 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <h1 className="text-title">Pricing engine</h1>

          <p className="mt-4 max-w-[48ch] text-lead text-muted">
            We price every crypto market on Polymarket with a block bootstrap Monte Carlo,
            then set our probability beside the market's. Where the two disagree by more
            than it costs to trade, there is a position worth taking.
          </p>

          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/overlay" className={btn('primary')}>
              Open the overlay
            </Link>
            <Link to="/markets" className={btn('outline')}>
              Make a market
            </Link>
          </div>
        </div>

        {/* The largest disagreement, drawn */}
        <div className="lg:col-span-7 lg:border-l lg:border-line lg:pl-12">
          <Panel className="p-5 md:p-6">
            <div className="flex items-center gap-3 text-micro text-muted">
              <Badge>{top.asset.toUpperCase()}</Badge>
              <span>closes {shortDate(top.closeDate)}</span>
              <span className="ml-auto uppercase tracking-wide">Largest gap</span>
            </div>

            <h2 className="mt-4 max-w-[34ch] text-lg leading-snug font-medium">
              {top.question}
            </h2>

            <div className="mt-8">
              <ProbabilityAxis
                model={top.ourProbability}
                market={top.marketProbability}
                edge={top.edge}
              />
            </div>

            <dl className="mt-6 grid grid-cols-3 gap-5 border-t border-line pt-4">
              <Stat label="Side" value={`${top.side} at ${cents(top.ticket.price)}`} />
              <Stat label="Stake" value={usd(top.stake, 2)} />
              <Stat
                label="Expected profit"
                value={signedUsd(top.ticket.expectedProfit)}
                tone="accent"
              />
            </dl>
          </Panel>
        </div>
      </section>

      {/* The book, in one line */}
      <section className="border-y border-line py-4">
        <div className="flex flex-wrap items-center gap-x-10 gap-y-5">
          <Stat label="Markets priced" value={runMeta.marketsPriced} />
          <Stat label="Actionable" value={book.actionable} tone="accent" />
          <Stat label="Expected profit" value={signedUsd(book.expectedProfit)} />
          <Stat label="Staked" value={usd(book.staked, 0)} />
          <Link to="/overlay" className={btn('outline', 'ml-auto')}>
            All markets
          </Link>
        </div>
      </section>

      {/* Underlying price outlook */}
      <section>
        <SectionHead
          title={`${runMeta.horizonDays} day price outlook`}
          note="The simulation every probability here is derived from. The bar spans the 10th to the 90th percentile of where each price lands."
          action={
            <Link to="/markets" className={btn('quiet')}>
              Build a market on this
            </Link>
          }
        />

        <div className="mt-6 grid gap-8 sm:grid-cols-3">
          {outlooks.map((o) => (
            <div key={o.asset}>
              <div className="flex items-baseline gap-2">
                <Badge tone="muted">{o.asset.toUpperCase()}</Badge>
                <span className="text-sm text-muted">{o.name}</span>
                <span className="ml-auto font-mono text-micro text-muted">
                  {pct(o.probUp)} up
                </span>
              </div>
              <div className="mt-3 font-mono text-[1.375rem] leading-none">{usd(o.spot)}</div>
              <div className="mt-4">
                <RangeBar low={o.lowP10} spot={o.spot} high={o.highP90} />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { MiniAxis } from '../components/ProbabilityAxis'
import { Badge, Button, Field, Panel, SectionHead, Select, Stat } from '../components/ui'
import { ASSET_NAMES, markets, type Asset } from '../data/desk'
import { useDesk } from '../lib/desk-state'
import { evaluateAll, summarize, type Signal } from '../lib/signals'
import { cents, pct, shortDate, signedPct, signedUsd, usd } from '../lib/format'

type Sort = 'edge' | 'profit' | 'stake' | 'closing'

const COLS =
  'lg:grid lg:grid-cols-[minmax(0,1fr)_72px_72px_76px_56px_88px_96px_104px] lg:items-center lg:gap-x-4'

function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 lg:block lg:text-right">
      <span className="text-micro text-muted lg:hidden">{label}</span>
      {children}
    </div>
  )
}

function Row({ signal }: { signal: Signal }) {
  const { stage, unstage, isStaged } = useDesk()
  const staged = isStaged(signal.id)

  return (
    <li
      className={`border-b border-line px-3 py-3 ${COLS} ${
        signal.actionable ? '' : 'opacity-55'
      }`}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Badge tone="muted">{signal.asset.toUpperCase()}</Badge>
          <p className="truncate text-sm">{signal.question}</p>
        </div>
        <div className="mt-2 flex items-center gap-4">
          <div className="w-32 shrink-0">
            <MiniAxis model={signal.ourProbability} market={signal.marketProbability} />
          </div>
          <span className="font-mono text-micro text-muted">
            closes {shortDate(signal.closeDate)}
          </span>
          {!signal.actionable && (
            <span className="text-micro text-muted">
              below the {pct(signal.netEdge >= 0 ? signal.netEdge : 0, 1)} bar
            </span>
          )}
        </div>
      </div>

      <div className="mt-3 space-y-2 lg:contents lg:mt-0 lg:space-y-0">
        <Cell label="Ours">
          <span className="font-mono text-sm text-accent">{pct(signal.ourProbability)}</span>
        </Cell>
        <Cell label="Market">
          <span className="font-mono text-sm">{pct(signal.marketProbability)}</span>
        </Cell>
        <Cell label="Net edge">
          <span className="font-mono text-sm">{signedPct(signal.netEdge, 1)}</span>
        </Cell>
        <Cell label="Side">
          <span className="font-mono text-micro">{signal.side}</span>
        </Cell>
        <Cell label="Stake">
          <span className="font-mono text-sm">{usd(signal.stake, 2)}</span>
        </Cell>
        <Cell label="Expected">
          <span
            className={`font-mono text-sm ${
              signal.actionable ? 'text-accent' : 'text-muted'
            }`}
          >
            {signedUsd(signal.ticket.expectedProfit)}
          </span>
        </Cell>

        <div className="pt-2 lg:pt-0">
          {signal.actionable ? (
            <Button
              variant={staged ? 'outline' : 'primary'}
              className="w-full !px-2 !text-micro"
              onClick={() => (staged ? unstage(signal.id) : stage(signal))}
            >
              {staged ? 'Staged' : `Stage ${signal.side}`}
            </Button>
          ) : (
            <span className="block text-right font-mono text-micro text-muted">no bet</span>
          )}
        </div>
      </div>
    </li>
  )
}

function Slip() {
  const { slip, unstage, clearSlip, bankroll } = useDesk()
  if (slip.length === 0) return null

  const staked = slip.reduce((t, b) => t + b.stake, 0)
  const expected = slip.reduce((t, b) => t + b.expectedProfit, 0)
  const best = slip.reduce((t, b) => t + b.payoutIfRight, 0)

  return (
    <Panel className="p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 className="text-sm font-semibold tracking-wide uppercase">
          Slip ({slip.length} {slip.length === 1 ? 'position' : 'positions'})
        </h2>
        <Button variant="quiet" className="!px-2 !text-micro" onClick={clearSlip}>
          Clear all
        </Button>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-5 border-y border-line py-4 sm:grid-cols-4">
        <Stat label="Staked" value={usd(staked, 2)} hint={pct(staked / bankroll, 1)} />
        <Stat label="Expected profit" value={signedUsd(expected)} tone="accent" />
        <Stat
          label="Expected return"
          value={signedPct(staked > 0 ? expected / staked : 0, 1)}
        />
        <Stat label="If all right" value={usd(best, 2)} />
      </dl>

      <ul className="mt-1">
        {slip.map((b) => (
          <li
            key={b.marketId}
            className="flex items-center gap-4 border-b border-line py-2.5 last:border-b-0"
          >
            <Badge tone="muted">{b.asset.toUpperCase()}</Badge>
            <p className="min-w-0 flex-1 truncate text-sm">{b.question}</p>
            <span className="font-mono text-micro">
              {b.side} at {cents(b.price)}
            </span>
            <span className="w-16 text-right font-mono text-sm">{usd(b.stake, 2)}</span>
            <span className="w-20 text-right font-mono text-sm text-accent">
              {signedUsd(b.expectedProfit)}
            </span>
            <Button
              variant="quiet"
              className="!px-2 !text-micro"
              onClick={() => unstage(b.marketId)}
              aria-label={`Remove ${b.question} from the slip`}
            >
              Remove
            </Button>
          </li>
        ))}
      </ul>

      <p className="mt-4 border-l border-line-strong pl-3 text-micro text-muted">
        Paper only. Nothing here is sent to Polymarket. The real capital gates in{' '}
        <code className="font-mono text-fg">trading/</code> are still closed.
      </p>
    </Panel>
  )
}

export function Overlay() {
  const { bankroll, setBankroll, tau, setTau } = useDesk()
  const [asset, setAsset] = useState<Asset | 'all'>('all')
  const [onlyActionable, setOnlyActionable] = useState(true)
  const [sort, setSort] = useState<Sort>('edge')

  const all = useMemo(() => evaluateAll(markets, bankroll, tau), [bankroll, tau])
  const book = useMemo(() => summarize(all), [all])

  const rows = useMemo(() => {
    const filtered = all
      .filter((s) => asset === 'all' || s.asset === asset)
      .filter((s) => !onlyActionable || s.actionable)

    const sorters: Record<Sort, (a: Signal, b: Signal) => number> = {
      edge: (a, b) => b.netEdge - a.netEdge,
      profit: (a, b) => b.ticket.expectedProfit - a.ticket.expectedProfit,
      stake: (a, b) => b.stake - a.stake,
      closing: (a, b) => a.closeDate.localeCompare(b.closeDate),
    }
    return [...filtered].sort(sorters[sort])
  }, [all, asset, onlyActionable, sort])

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-title">Polymarket overlay</h1>
        <p className="mt-3 max-w-[70ch] text-lead text-muted">
          Our probability against the market&apos;s, on every crypto market we can price.
          Set your bankroll and the engine sizes each position at quarter Kelly, capped at{' '}
          {pct(0.05)} of the book.
        </p>
      </div>

      <Panel className="p-5 md:p-6">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr] lg:items-center">
          <div>
            <p className="text-micro tracking-wide text-muted uppercase">
              Expected profit across {book.actionable} actionable markets
            </p>
            <p className="mt-3 font-mono text-[2.25rem] leading-none text-accent">
              {signedUsd(book.expectedProfit, 2)}
            </p>
            <p className="mt-3 text-sm text-muted">
              on {usd(book.staked, 2)} staked, by our own probabilities
            </p>
          </div>

          <dl className="grid grid-cols-2 gap-6 border-t border-line pt-5 sm:grid-cols-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-8">
            <Stat label="Expected return" value={signedPct(book.expectedReturn, 1)} />
            <Stat label="If all resolve our way" value={usd(book.bestCase, 0)} />
            <Stat
              label="Capital at risk"
              value={usd(book.staked, 0)}
              hint={pct(book.staked / bankroll, 1)}
            />
            <Stat label="Priced but skipped" value={book.priced - book.actionable} />
          </dl>
        </div>
      </Panel>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field
          label="Bankroll"
          type="number"
          min={0}
          step={100}
          prefix="$"
          value={bankroll}
          onChange={(e) => setBankroll(Math.max(0, Number(e.target.value)))}
          hint="Scales every stake below"
        />
        <Field
          label="Edge buffer"
          type="number"
          min={0}
          max={50}
          step={0.5}
          suffix="%"
          value={+(tau * 100).toFixed(1)}
          onChange={(e) => setTau(Math.max(0, Number(e.target.value) / 100))}
          hint="Higher means fewer, stronger signals"
        />
        <Select
          label="Asset"
          value={asset}
          onChange={(e) => setAsset(e.target.value as Asset | 'all')}
        >
          <option value="all">All assets</option>
          {(Object.keys(ASSET_NAMES) as Asset[]).map((a) => (
            <option key={a} value={a}>
              {ASSET_NAMES[a]}
            </option>
          ))}
        </Select>
        <Select label="Sort by" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="edge">Net edge</option>
          <option value="profit">Expected profit</option>
          <option value="stake">Stake size</option>
          <option value="closing">Closing soonest</option>
        </Select>
      </div>

      <Slip />

      <section>
        <SectionHead
          title={`${rows.length} ${rows.length === 1 ? 'market' : 'markets'}`}
          note={
            onlyActionable
              ? `Showing only markets whose edge clears costs plus the ${pct(tau)} buffer.`
              : 'Showing everything we priced, including markets the engine would skip.'
          }
          action={
            <label className="flex cursor-pointer items-center gap-2.5 text-sm text-muted">
              <input
                type="checkbox"
                checked={onlyActionable}
                onChange={(e) => setOnlyActionable(e.target.checked)}
                className="size-3.5 accent-accent"
              />
              Actionable only
            </label>
          }
        />

        <div
          className={`hidden border-b border-line px-3 py-2 text-micro tracking-wide text-muted uppercase lg:block ${COLS}`}
        >
          <span>Market</span>
          <span className="text-right">Ours</span>
          <span className="text-right">Market</span>
          <span className="text-right">Net edge</span>
          <span className="text-right">Side</span>
          <span className="text-right">Stake</span>
          <span className="text-right">Expected</span>
          <span />
        </div>

        {rows.length === 0 ? (
          <p className="border-b border-line px-3 py-10 text-center text-sm text-muted">
            No market clears a {pct(tau)} buffer on this filter. Lower the buffer or switch
            to all assets.
          </p>
        ) : (
          <ul>
            {rows.map((s) => (
              <Row key={s.id} signal={s} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

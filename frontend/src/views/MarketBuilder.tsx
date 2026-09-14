import { useEffect, useMemo, useState } from 'react'
import { Badge, Button, Field, Panel, SectionHead, Select, Stat } from '../components/ui'
import { ASSET_NAMES, outlookFor, outlooks, runMeta, type Asset } from '../data/desk'
import { useDesk, type CreatedMarket } from '../lib/desk-state'
import { impliedSigma, probabilityOf, quantile, scaleSigma, type Threshold } from '../lib/stats'
import { cents, pct, shortDate, usd } from '../lib/format'

/** Sensible strike increments per asset, so generated levels read like real ones. */
const STEP: Record<Asset, number> = { btc: 500, eth: 50, sol: 5 }

const roundTo = (v: number, step: number) => Math.round(v / step) * step
const floorTo = (v: number, step: number) => Math.floor(v / step) * step
const ceilTo = (v: number, step: number) => Math.ceil(v / step) * step

const isoDate = (d: Date) => d.toISOString().slice(0, 10)

function addDays(days: number, from = new Date()) {
  const d = new Date(from)
  d.setUTCDate(d.getUTCDate() + days)
  return d
}

/** Sigma of log-returns for this asset over `days`, from the last Monte Carlo run. */
function sigmaFor(asset: Asset, days: number) {
  const o = outlookFor(asset)
  return scaleSigma(impliedSigma(o.lowP10, o.highP90), runMeta.horizonDays, days)
}

function questionFor(asset: Asset, spec: Threshold, closeDate: string) {
  const name = ASSET_NAMES[asset]
  const on = `on ${shortDate(closeDate)}`
  switch (spec.kind) {
    case 'above':
      return `Will ${name} be above ${usd(spec.level)} ${on}?`
    case 'below':
      return `Will ${name} be below ${usd(spec.level)} ${on}?`
    case 'between':
      return `Will ${name} be between ${usd(Math.min(spec.level, spec.upper))} and ${usd(
        Math.max(spec.level, spec.upper),
      )} ${on}?`
  }
}

/** The simulated terminal distribution, with the resolving region shaded. */
function DistributionBar({
  asset,
  days,
  spec,
}: {
  asset: Asset
  days: number
  spec: Threshold
}) {
  const o = outlookFor(asset)
  const sigma = sigmaFor(asset, days)
  const p5 = quantile(o.spot, sigma, 0.05)
  const p95 = quantile(o.spot, sigma, 0.95)
  const p10 = quantile(o.spot, sigma, 0.1)
  const p90 = quantile(o.spot, sigma, 0.9)

  const levels = spec.kind === 'between' ? [spec.level, spec.upper] : [spec.level]
  const lo = Math.min(p5, ...levels) * 0.995
  const hi = Math.max(p95, ...levels) * 1.005
  const at = (v: number) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))

  const shade =
    spec.kind === 'above'
      ? { left: at(spec.level), width: 100 - at(spec.level) }
      : spec.kind === 'below'
        ? { left: 0, width: at(spec.level) }
        : {
            left: at(Math.min(spec.level, spec.upper)),
            width: at(Math.max(spec.level, spec.upper)) - at(Math.min(spec.level, spec.upper)),
          }

  return (
    <div>
      <div className="relative h-14">
        {/* p10 to p90 body of the distribution */}
        <div
          className="absolute top-5 h-2 border-x border-line-strong bg-raised"
          style={{ left: `${at(p10)}%`, width: `${at(p90) - at(p10)}%` }}
        />
        {/* the region that resolves YES */}
        <div
          className="absolute top-3 h-6 bg-accent/15"
          style={{ left: `${shade.left}%`, width: `${shade.width}%` }}
        />
        <div className="absolute inset-x-0 top-6 h-px bg-line" />
        {/* strikes */}
        {levels.map((l) => (
          <div key={l} className="absolute top-1 h-11 w-px bg-accent" style={{ left: `${at(l)}%` }}>
            <span className="absolute -top-0.5 left-2 font-mono text-micro whitespace-nowrap text-accent">
              {usd(l)}
            </span>
          </div>
        ))}
        {/* spot */}
        <div
          className="absolute top-[21px] size-[6px] -translate-x-1/2 rounded-full border border-fg bg-canvas"
          style={{ left: `${at(o.spot)}%` }}
        />
        <div className="absolute inset-x-0 bottom-0 flex justify-between font-mono text-micro text-muted">
          <span>{usd(p5)}</span>
          <span>spot {usd(o.spot)}</span>
          <span>{usd(p95)}</span>
        </div>
      </div>
    </div>
  )
}

export function MarketBuilder() {
  const { created, addMarket, removeMarket } = useDesk()

  const [asset, setAsset] = useState<Asset>('btc')
  const [kind, setKind] = useState<Threshold['kind']>('above')
  const [days, setDays] = useState(3)
  const [level, setLevel] = useState(() => roundTo(outlookFor('btc').spot, STEP.btc))
  const [upper, setUpper] = useState(() => roundTo(outlookFor('btc').spot, STEP.btc) + STEP.btc)

  // Retarget the strikes whenever the underlying changes.
  useEffect(() => {
    const spot = outlookFor(asset).spot
    setLevel(roundTo(spot, STEP[asset]))
    setUpper(roundTo(spot, STEP[asset]) + STEP[asset])
  }, [asset])

  const closeDate = isoDate(addDays(days))
  const spec: Threshold = useMemo(
    () => (kind === 'between' ? { kind: 'between', level, upper } : { kind, level }),
    [kind, level, upper],
  )

  const sigma = sigmaFor(asset, days)
  const probability = probabilityOf(spec, outlookFor(asset).spot, sigma)
  const question = questionFor(asset, spec, closeDate)

  function create() {
    addMarket({
      id: `${asset}-${kind}-${level}-${closeDate}-${Date.now()}`,
      asset,
      question,
      spec,
      openedOn: isoDate(new Date()),
      closeDate,
      horizonDays: days,
      ourProbability: probability,
      fairPrice: probability,
    })
  }

  /** One above, one below, one band per asset, all at the horizon set above. */
  function generateBatch() {
    const close = isoDate(addDays(days))
    const batch: CreatedMarket[] = []

    for (const o of outlooks) {
      const step = STEP[o.asset]
      const s = sigmaFor(o.asset, days)
      const specs: Threshold[] = [
        { kind: 'above', level: ceilTo(o.spot, step) },
        { kind: 'below', level: floorTo(o.spot, step) },
        { kind: 'between', level: floorTo(o.spot, step), upper: ceilTo(o.spot, step) + step },
      ]

      for (const sp of specs) {
        const p = probabilityOf(sp, o.spot, s)
        batch.push({
          id: `${o.asset}-${sp.kind}-${sp.level}-${close}-${Date.now()}-${Math.random()}`,
          asset: o.asset,
          question: questionFor(o.asset, sp, close),
          spec: sp,
          openedOn: isoDate(new Date()),
          closeDate: close,
          horizonDays: days,
          ourProbability: p,
          fairPrice: p,
        })
      }
    }
    batch.forEach(addMarket)
  }

  const step = STEP[asset]

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-title">Make a market</h1>
        <p className="mt-3 max-w-[70ch] text-lead text-muted">
          Write a question against the simulation and it comes back priced. The
          distribution widens with the square root of time, so a 2 day market sits much
          tighter than a 7 day one.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[340px_minmax(0,1fr)] lg:gap-12">
        {/* The form */}
        <div className="space-y-4">
          <Select
            label="Underlying"
            value={asset}
            onChange={(e) => setAsset(e.target.value as Asset)}
          >
            {outlooks.map((o) => (
              <option key={o.asset} value={o.asset}>
                {o.name} at {usd(o.spot)}
              </option>
            ))}
          </Select>

          <Select
            label="Resolves YES when the price is"
            value={kind}
            onChange={(e) => setKind(e.target.value as Threshold['kind'])}
          >
            <option value="above">Above a level</option>
            <option value="below">Below a level</option>
            <option value="between">Between two levels</option>
          </Select>

          <div className="grid grid-cols-2 gap-4">
            <Field
              label={kind === 'between' ? 'Lower level' : 'Level'}
              type="number"
              step={step}
              prefix="$"
              value={level}
              onChange={(e) => setLevel(Number(e.target.value))}
            />
            {kind === 'between' && (
              <Field
                label="Upper level"
                type="number"
                step={step}
                prefix="$"
                value={upper}
                onChange={(e) => setUpper(Number(e.target.value))}
              />
            )}
          </div>

          <div>
            <Field
              label="Closes in"
              type="number"
              min={1}
              max={60}
              suffix={`days, ${shortDate(closeDate)}`}
              value={days}
              onChange={(e) => setDays(Math.max(1, Math.min(60, Number(e.target.value))))}
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {[1, 2, 3, 5, 7, 14].map((d) => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`rounded-sm border px-2 py-0.5 font-mono text-micro transition-colors ${
                    days === d
                      ? 'border-accent text-accent'
                      : 'border-line-strong text-muted hover:text-fg'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          <Button variant="primary" className="w-full" onClick={create}>
            Create market
          </Button>
        </div>

        {/* The price */}
        <Panel className="p-5 md:p-6">
          <div className="flex items-center gap-3 text-micro text-muted">
            <Badge>{asset.toUpperCase()}</Badge>
            <span>{days} day horizon</span>
            <span className="ml-auto">closes {shortDate(closeDate)}</span>
          </div>

          <h2 className="mt-4 text-lg leading-snug font-medium">{question}</h2>

          <div className="mt-7">
            <DistributionBar asset={asset} days={days} spec={spec} />
          </div>

          <dl className="mt-7 grid grid-cols-2 gap-6 border-t border-line pt-5 sm:grid-cols-4">
            <Stat label="Our probability" value={pct(probability, 1)} tone="accent" />
            <Stat label="Fair price" value={cents(probability)} hint="per $1 of payout" />
            <Stat label="Fair NO price" value={cents(1 - probability)} />
            <Stat
              label="Move sigma"
              value={pct(sigma, 1)}
              hint={`over ${days} ${days === 1 ? 'day' : 'days'}`}
            />
          </dl>
        </Panel>
      </div>

      <section>
        <SectionHead
          title={`Open markets (${created.length})`}
          note="Markets you have written on this desk. Prices come straight from the simulation, before any Polymarket comparison."
          action={
            <Button variant="outline" onClick={generateBatch}>
              Generate a batch
            </Button>
          }
        />

        {created.length === 0 ? (
          <p className="border-b border-line px-3 py-10 text-sm text-muted">
            No markets yet. Build one above, or generate a batch of nine at the {days} day
            horizon.
          </p>
        ) : (
          <ul>
            {created.map((m) => (
              <li
                key={m.id}
                className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line px-3 py-3"
              >
                <Badge tone="muted">{m.asset.toUpperCase()}</Badge>
                <p className="min-w-0 flex-1 truncate text-sm">{m.question}</p>
                <span className="font-mono text-micro text-muted">
                  {m.horizonDays}d to {shortDate(m.closeDate)}
                </span>
                <span className="w-20 text-right font-mono text-sm text-accent">
                  {cents(m.fairPrice)}
                </span>
                <span className="w-16 text-right font-mono text-sm">
                  {pct(m.ourProbability, 1)}
                </span>
                <Button
                  variant="quiet"
                  className="!px-2 !text-micro"
                  onClick={() => removeMarket(m.id)}
                  aria-label={`Remove ${m.question}`}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

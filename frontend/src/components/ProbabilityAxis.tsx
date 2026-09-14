import { pct, signedPct } from '../lib/format'

type Props = {
  model: number
  market: number
  edge: number
}

/** Keeps a label from running off either end of the track. */
function anchorFor(p: number) {
  if (p < 14) return { transform: 'translateX(0)' }
  if (p > 86) return { transform: 'translateX(-100%)' }
  return { transform: 'translateX(-50%)' }
}

const TICKS = [0, 25, 50, 75, 100]

/**
 * Our probability and the market's, placed on
 * a shared 0 to 100% scale, with the distance between them called out as the edge.
 */
export function ProbabilityAxis({ model, market, edge }: Props) {
  const lo = Math.min(model, market) * 100
  const hi = Math.max(model, market) * 100
  const span = hi - lo

  return (
    <div
      role="img"
      aria-label={`Our model says ${pct(model)}, Polymarket says ${pct(
        market,
      )}, an edge of ${signedPct(edge)}.`}
    >
      {/* Readings, tethered to their position on the scale below. */}
      <div className="relative h-[68px]">
        {(
          [
            { p: model * 100, label: 'Our model', value: pct(model), accent: true },
            { p: market * 100, label: 'Polymarket', value: pct(market), accent: false },
          ] as const
        ).map((m) => (
          <div
            key={m.label}
            className="absolute bottom-0"
            style={{ left: `${m.p}%`, ...anchorFor(m.p) }}
          >
            <div className="text-micro text-muted whitespace-nowrap">{m.label}</div>
            <div
              className={`font-mono text-[1.5rem] leading-none mt-1.5 ${
                m.accent ? 'text-accent' : 'text-fg'
              }`}
            >
              {m.value}
            </div>
          </div>
        ))}
      </div>

      {/* Connectors from each reading down to the scale. */}
      <div className="relative h-4">
        <div
          className="absolute top-0 bottom-0 w-px -translate-x-1/2 bg-accent/45"
          style={{ left: `${model * 100}%` }}
        />
        <div
          className="absolute top-0 bottom-0 w-px -translate-x-1/2 bg-line-strong"
          style={{ left: `${market * 100}%` }}
        />
      </div>

      {/* The scale. */}
      <div className="relative h-2.5">
        <div className="absolute inset-x-0 top-0 h-px bg-line" />
        <div
          className="absolute top-0 h-px bg-accent/60"
          style={{ left: `${lo}%`, width: `${span}%` }}
        />
        {TICKS.map((t) => (
          <div
            key={t}
            className="absolute top-0 h-1.5 w-px bg-line"
            style={{ left: `${t}%` }}
            aria-hidden
          />
        ))}
        <div
          className="absolute -top-[3px] size-[6px] rounded-full bg-accent"
          style={{ left: `${model * 100}%`, transform: 'translateX(-50%)' }}
        />
        <div
          className="absolute -top-[3px] size-[6px] rounded-full border border-muted bg-canvas"
          style={{ left: `${market * 100}%`, transform: 'translateX(-50%)' }}
        />
      </div>

      {/* The gap, measured. */}
      <div className="relative h-8">
        <div
          className="absolute top-0 border-x border-b border-line-strong h-2.5"
          style={{ left: `${lo}%`, width: `${span}%` }}
          aria-hidden
        />
        <div
          className="absolute top-[18px] font-mono text-sm text-fg whitespace-nowrap"
          style={{ left: `${lo + span / 2}%`, transform: 'translateX(-50%)' }}
        >
          {signedPct(edge)} edge
        </div>
      </div>

      <div className="flex justify-between font-mono text-micro text-muted">
        <span>0%</span>
        <span>100%</span>
      </div>
    </div>
  )
}

/** The same drawing at row scale, without the annotation. */
export function MiniAxis({ model, market }: { model: number; market: number }) {
  const lo = Math.min(model, market) * 100
  const hi = Math.max(model, market) * 100

  return (
    <div className="relative h-2 w-full" aria-hidden>
      <div className="absolute inset-x-0 top-1 h-px bg-line" />
      <div
        className="absolute top-1 h-px bg-accent/50"
        style={{ left: `${lo}%`, width: `${hi - lo}%` }}
      />
      <div
        className="absolute top-[2px] size-[5px] rounded-full bg-accent"
        style={{ left: `${model * 100}%`, transform: 'translateX(-50%)' }}
      />
      <div
        className="absolute top-[2px] size-[5px] rounded-full border border-muted bg-canvas"
        style={{ left: `${market * 100}%`, transform: 'translateX(-50%)' }}
      />
    </div>
  )
}

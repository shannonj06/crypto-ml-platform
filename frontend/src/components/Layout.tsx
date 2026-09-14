import { NavLink, Outlet } from 'react-router-dom'
import { runMeta } from '../data/desk'
import { daysBetween, usd } from '../lib/format'
import { useDesk } from '../lib/desk-state'

/** Two dots on a scale: the figure the pricing view draws at full size. */
function Mark() {
  return (
    <span className="relative block h-2.5 w-8" aria-hidden>
      <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-line-strong" />
      <span className="absolute top-1/2 left-[18%] size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent" />
      <span className="absolute top-1/2 left-[78%] size-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-muted bg-canvas" />
    </span>
  )
}

const NAV = [
  { to: '/', label: 'Pricing', end: true },
  { to: '/overlay', label: 'Overlay', end: false },
  { to: '/markets', label: 'Make a market', end: false },
]

function StaleNotice() {
  const age = daysBetween(runMeta.pricesThrough, new Date())
  if (age <= runMeta.staleAfterDays) return null

  return (
    <div className="border-b border-line bg-raised">
      <div className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-x-6 gap-y-2 px-6 py-2.5 md:px-10">
        <p className="text-sm">
          <span className="font-mono text-accent">{age} days</span> since the last price
          refresh. Every probability and edge here is computed from closes through{' '}
          <span className="font-mono">{runMeta.pricesThrough}</span>. Stale inputs
          manufacture edges that are not there.
        </p>
        <code className="ml-auto rounded-sm border border-line-strong px-2 py-0.5 font-mono text-micro text-muted">
          python -m app.update_prices
        </code>
      </div>
    </div>
  )
}

export function Layout() {
  const { bankroll, slip } = useDesk()
  const staked = slip.reduce((t, b) => t + b.stake, 0)

  return (
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-10 border-b border-line bg-canvas">
        <div className="mx-auto flex h-12 max-w-[1240px] items-center gap-8 px-6 md:px-10">
          <NavLink
            to="/"
            className="flex items-center gap-2.5 text-sm font-semibold tracking-tight"
          >
            <Mark />
            Overlay
          </NavLink>

          <nav className="hidden items-center gap-5 md:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `text-sm transition-colors ${
                    isActive ? 'text-fg' : 'text-muted hover:text-fg'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-4">
            <span className="hidden font-mono text-micro text-muted lg:inline">
              bankroll {usd(bankroll)}
            </span>
            <NavLink
              to="/overlay"
              className="rounded-sm border border-line-strong px-2.5 py-1 font-mono text-micro transition-colors hover:bg-raised"
            >
              Slip ({slip.length}){slip.length > 0 ? ` ${usd(staked)}` : ''}
            </NavLink>
          </div>
        </div>

        <nav className="flex gap-5 overflow-x-auto border-t border-line px-6 py-2 md:hidden">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `whitespace-nowrap text-sm ${isActive ? 'text-fg' : 'text-muted'}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <StaleNotice />

      <main className="mx-auto max-w-[1240px] px-6 pt-8 pb-24 md:px-10">
        <Outlet />
      </main>
    </div>
  )
}

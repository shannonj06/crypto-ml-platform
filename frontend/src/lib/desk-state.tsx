import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ENGINE, type Asset } from '../data/desk'
import type { Signal } from './signals'
import type { Side, Threshold } from './stats'

export type StagedBet = {
  marketId: string
  question: string
  asset: Asset
  side: Side
  stake: number
  price: number
  expectedProfit: number
  payoutIfRight: number
}

export type CreatedMarket = {
  id: string
  asset: Asset
  question: string
  spec: Threshold
  openedOn: string
  closeDate: string
  horizonDays: number
  ourProbability: number
  fairPrice: number
}

type DeskState = {
  bankroll: number
  setBankroll: (n: number) => void
  tau: number
  setTau: (n: number) => void

  slip: StagedBet[]
  stage: (signal: Signal) => void
  unstage: (marketId: string) => void
  clearSlip: () => void
  isStaged: (marketId: string) => boolean

  created: CreatedMarket[]
  addMarket: (m: CreatedMarket) => void
  removeMarket: (id: string) => void
}

const Ctx = createContext<DeskState | null>(null)

const STORE_KEY = 'overlay.desk.v1'

type Persisted = Partial<
  Pick<DeskState, 'bankroll' | 'tau'> & {
    slip: StagedBet[]
    created: CreatedMarket[]
  }
>

function load(): Persisted {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) ?? '{}') as Persisted
  } catch {
    return {}
  }
}

export function DeskProvider({ children }: { children: ReactNode }) {
  const saved = useMemo(load, [])

  const [bankroll, setBankroll] = useState(saved.bankroll ?? 1000)
  const [tau, setTau] = useState(saved.tau ?? ENGINE.tau)
  const [slip, setSlip] = useState<StagedBet[]>(saved.slip ?? [])
  const [created, setCreated] = useState<CreatedMarket[]>(saved.created ?? [])

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ bankroll, tau, slip, created }))
    } catch {
      // Private window or blocked storage. The desk still works, it just forgets.
    }
  }, [bankroll, tau, slip, created])

  const stage = useCallback((s: Signal) => {
    setSlip((current) => {
      const bet: StagedBet = {
        marketId: s.id,
        question: s.question,
        asset: s.asset,
        side: s.side,
        stake: s.stake,
        price: s.ticket.price,
        expectedProfit: s.ticket.expectedProfit,
        payoutIfRight: s.ticket.payoutIfRight,
      }
      const existing = current.findIndex((b) => b.marketId === s.id)
      if (existing === -1) return [...current, bet]
      const next = [...current]
      next[existing] = bet
      return next
    })
  }, [])

  const unstage = useCallback((marketId: string) => {
    setSlip((current) => current.filter((b) => b.marketId !== marketId))
  }, [])

  const clearSlip = useCallback(() => setSlip([]), [])

  const addMarket = useCallback((m: CreatedMarket) => {
    setCreated((current) => [m, ...current])
  }, [])

  const removeMarket = useCallback((id: string) => {
    setCreated((current) => current.filter((m) => m.id !== id))
  }, [])

  const value = useMemo<DeskState>(
    () => ({
      bankroll,
      setBankroll,
      tau,
      setTau,
      slip,
      stage,
      unstage,
      clearSlip,
      isStaged: (id: string) => slip.some((b) => b.marketId === id),
      created,
      addMarket,
      removeMarket,
    }),
    [bankroll, tau, slip, created, stage, unstage, clearSlip, addMarket, removeMarket],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useDesk(): DeskState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useDesk must be used inside <DeskProvider>')
  return ctx
}

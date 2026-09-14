export const pct = (n: number, digits = 0) => `${(n * 100).toFixed(digits)}%`

export const signedPct = (n: number, digits = 0) =>
  `${n > 0 ? '+' : n < 0 ? '-' : ''}${(Math.abs(n) * 100).toFixed(digits)}%`

export const usd = (n: number, digits = 0) =>
  `$${n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`

export const signedUsd = (n: number, digits = 2) =>
  `${n < 0 ? '-' : n > 0 ? '+' : ''}${usd(Math.abs(n), digits)}`

/** Prediction-market convention: a probability quoted as cents on the dollar. */
export const cents = (n: number) => `${(n * 100).toFixed(1)}¢`

export const shortDate = (iso: string) =>
  new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })

export const daysBetween = (fromIso: string, to: Date) =>
  Math.floor(
    (Date.UTC(to.getUTCFullYear(), to.getUTCMonth(), to.getUTCDate()) -
      Date.parse(`${fromIso.slice(0, 10)}T00:00:00Z`)) /
      86_400_000,
  )

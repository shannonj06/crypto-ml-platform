import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'outline' | 'quiet'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-canvas hover:bg-accent/90 border border-accent',
  outline: 'border border-line-strong text-fg hover:bg-raised',
  quiet: 'border border-transparent text-muted hover:text-fg hover:bg-raised',
}

export const btn = (variant: Variant = 'outline', extra = '') =>
  `inline-flex items-center justify-center gap-2 rounded-sm px-3 py-1.5 text-sm font-medium
   transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${extra}`

export function Button({
  variant = 'outline',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={btn(variant, className)} {...props} />
}

export function Panel({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`rounded-sm border border-line bg-card ${className}`}>{children}</div>
  )
}

export function Stat({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: 'default' | 'accent'
}) {
  return (
    <div>
      <dt className="text-micro uppercase tracking-wide text-muted">{label}</dt>
      <dd
        className={`mt-1.5 font-mono text-base leading-none ${
          tone === 'accent' ? 'text-accent' : 'text-fg'
        }`}
      >
        {value}
      </dd>
      {hint ? <p className="mt-1.5 text-micro text-muted">{hint}</p> : null}
    </div>
  )
}

export function Badge({
  children,
  tone = 'line',
}: {
  children: ReactNode
  tone?: 'line' | 'accent' | 'muted'
}) {
  const tones = {
    line: 'border-line-strong text-fg',
    accent: 'border-accent/50 text-accent',
    muted: 'border-line text-muted',
  }
  return (
    <span
      className={`inline-flex items-center rounded-sm border px-1.5 py-px font-mono text-micro ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

export function Field({
  label,
  hint,
  prefix,
  suffix,
  className = '',
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string
  hint?: string
  prefix?: string
  suffix?: string
}) {
  return (
    <label className={`block ${className}`}>
      <span className="text-micro uppercase tracking-wide text-muted">{label}</span>
      <span className="mt-1.5 flex items-center rounded-sm border border-line-strong bg-raised focus-within:border-accent">
        {prefix ? (
          <span className="pl-2.5 font-mono text-sm text-muted">{prefix}</span>
        ) : null}
        <input
          className="w-full bg-transparent px-2.5 py-1.5 font-mono text-sm text-fg outline-none"
          {...props}
        />
        {suffix ? (
          <span className="pr-2.5 font-mono text-micro whitespace-nowrap text-muted">
            {suffix}
          </span>
        ) : null}
      </span>
      {hint ? <span className="mt-1.5 block text-micro text-muted">{hint}</span> : null}
    </label>
  )
}

export function Select({
  label,
  children,
  className = '',
  ...props
}: InputHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) {
  return (
    <label className={`block ${className}`}>
      <span className="text-micro uppercase tracking-wide text-muted">{label}</span>
      <select
        className="mt-1.5 w-full rounded-sm border border-line-strong bg-raised px-2.5 py-1.5 text-sm text-fg outline-none focus:border-accent"
        {...props}
      >
        {children}
      </select>
    </label>
  )
}

export function SectionHead({
  title,
  note,
  action,
}: {
  title: string
  note?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-3">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide">{title}</h2>
        {note ? <p className="mt-1.5 max-w-[62ch] text-sm text-muted">{note}</p> : null}
      </div>
      {action}
    </div>
  )
}

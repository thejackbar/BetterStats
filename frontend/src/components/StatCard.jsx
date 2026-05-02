import clsx from 'clsx'

export default function StatCard({ label, value, sub, accent = false, large = false }) {
  return (
    <div className={clsx(
      'card p-4 flex flex-col gap-1',
      accent && 'border-accent/30 bg-accent/5',
    )}>
      <span className="section-label">{label}</span>
      <span className={clsx(
        'stat-number font-bold leading-none',
        large ? 'text-4xl' : 'text-2xl',
        accent ? 'text-accent' : 'text-white',
      )}>
        {value ?? '—'}
      </span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </div>
  )
}

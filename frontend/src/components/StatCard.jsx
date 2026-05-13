import clsx from 'clsx'

export default function StatCard({ label, value, sub, accent = false, large = false }) {
  return (
    <div className={clsx(
      'pb-card p-4 flex flex-col gap-1',
      accent && 'border-pb-accent/30',
    )}
    style={accent ? { background: 'color-mix(in srgb, var(--pb-accent) 5%, var(--pb-surface))' } : {}}
    >
      <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{label}</span>
      <span className={clsx(
        'font-mono font-bold leading-none',
        large ? 'text-4xl' : 'text-2xl',
        accent ? 'text-pb-accent' : 'text-pb-text',
      )}
      style={accent ? { color: 'var(--pb-accent)' } : {}}
      >
        {value ?? '—'}
      </span>
      {sub && <span className="font-mono text-[10px] text-pb-faintest">{sub}</span>}
    </div>
  )
}

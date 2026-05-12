export default function LoadingSpinner({ size = 'md', message = '' }) {
  const sz = { sm: 'w-5 h-5', md: 'w-8 h-8', lg: 'w-12 h-12' }[size]
  return (
    <div className="flex flex-col items-center gap-3 py-12">
      <div className={`${sz} border-2 border-pb-surface2 rounded-full animate-spin`} style={{ borderTopColor: 'var(--pb-accent)' }} />
      {message && <p className="font-mono text-[11px] text-pb-faint">{message}</p>}
    </div>
  )
}

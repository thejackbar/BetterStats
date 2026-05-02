export default function LoadingSpinner({ size = 'md', message = '' }) {
  const sz = { sm: 'w-5 h-5', md: 'w-8 h-8', lg: 'w-12 h-12' }[size]
  return (
    <div className="flex flex-col items-center gap-3 py-12">
      <div className={`${sz} border-2 border-navy-600 border-t-accent rounded-full animate-spin`} />
      {message && <p className="text-sm text-slate-500">{message}</p>}
    </div>
  )
}

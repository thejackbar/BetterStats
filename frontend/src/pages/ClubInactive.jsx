import { Link } from 'react-router-dom'

export default function ClubInactive() {
  return (
    <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4">
      <div className="text-center max-w-md">
        <div className="w-12 h-12 rounded-full bg-pb-surface2 border pb-hairline flex items-center justify-center mx-auto mb-6">
          <svg className="w-6 h-6 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h1 className="font-display font-bold text-2xl text-pb-text mb-3 tracking-tight">Page not available</h1>
        <p className="text-pb-dim leading-relaxed">
          This club page is currently not available. Contact your club executives to get access.
        </p>
        <div className="mt-8">
          <Link to="/" className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">
            ← BACK TO BETTERSTATS
          </Link>
        </div>
      </div>
    </div>
  )
}

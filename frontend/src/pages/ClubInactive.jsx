import { Link } from 'react-router-dom'

export default function ClubInactive() {
  return (
    <div className="min-h-screen bg-navy-950 flex items-center justify-center px-4">
      <div className="text-center max-w-md">
        <div className="w-12 h-12 rounded-full bg-navy-800 flex items-center justify-center mx-auto mb-6">
          <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h1 className="font-display font-bold text-2xl text-white mb-3">Page not available</h1>
        <p className="text-slate-400 leading-relaxed">
          This club page is currently not available. Contact your club executives to get access.
        </p>
        <div className="mt-8">
          <Link to="/" className="text-slate-500 text-sm hover:text-slate-300 transition-colors">
            ← Back to BetterStats
          </Link>
        </div>
      </div>
    </div>
  )
}

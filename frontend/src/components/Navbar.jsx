import { Link, useLocation } from 'react-router-dom'
import { useState } from 'react'

function useClubSlug() {
  const { pathname } = useLocation()
  const segments = pathname.split('/').filter(Boolean)
  const CLUB_SECTIONS = ['dashboard', 'players', 'leaderboard', 'records', 'compare']
  if (segments.length >= 2 && CLUB_SECTIONS.includes(segments[1])) {
    return segments[0]
  }
  if (segments[0] === 'players' || segments[0] === 'scorecards' || segments[0] === 'match' || segments[0] === 'games') {
    return sessionStorage.getItem('bs_last_slug') || null
  }
  return null
}

export default function Navbar() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const clubSlug = useClubSlug()

  const SKIP_PATHS = ['/admin', '/login', '/features', '/pricing', '/about', '/contact', '/terms', '/privacy']
  if (SKIP_PATHS.some(p => pathname.startsWith(p)) || pathname === '/') return null

  const navLinks = clubSlug ? [
    { to: `/${clubSlug}/dashboard`, label: 'Dashboard' },
    { to: `/${clubSlug}/players`, label: 'Players' },
    { to: `/${clubSlug}/leaderboard`, label: 'Leaderboard' },
    { to: `/${clubSlug}/records`, label: 'Records' },
    { to: `/${clubSlug}/compare`, label: 'Compare' },
  ] : []

  return (
    <nav className="bg-navy-900 border-b border-navy-700 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
        <Link to={clubSlug ? `/${clubSlug}/dashboard` : '/'} className="flex items-center gap-2 group">
          <span className="w-6 h-6 rounded bg-accent flex items-center justify-center">
            <svg viewBox="0 0 24 24" className="w-4 h-4 fill-navy-950" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="4" x2="12" y2="20" stroke="#070b14" strokeWidth="2" />
              <line x1="4" y1="12" x2="20" y2="12" stroke="#070b14" strokeWidth="2" />
            </svg>
          </span>
          <span className="font-display font-bold text-xl tracking-wider uppercase text-white group-hover:text-accent transition-colors">
            Better<span className="text-accent">Stats</span>
          </span>
          <span className="text-slate-600 text-xs font-mono">v3.0.2</span>
        </Link>

        <div className="hidden md:flex items-center gap-1">
          {navLinks.map(link => (
            <Link
              key={link.to}
              to={link.to}
              className={pathname.startsWith(link.to) ? 'btn-ghost text-accent' : 'btn-ghost'}
            >
              {link.label}
            </Link>
          ))}
        </div>

        <button
          className="md:hidden text-slate-400 hover:text-white p-2"
          onClick={() => setOpen(o => !o)}
          aria-label="Menu"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {open
              ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            }
          </svg>
        </button>
      </div>

      {open && (
        <div className="md:hidden border-t border-navy-700 bg-navy-900 px-4 py-3 flex flex-col gap-1">
          {navLinks.map(link => (
            <Link key={link.to} to={link.to} className="btn-ghost text-left" onClick={() => setOpen(false)}>
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  )
}

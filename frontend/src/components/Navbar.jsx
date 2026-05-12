import { Link, useLocation } from 'react-router-dom'
import { useState } from 'react'

function useClubSlug() {
  const { pathname } = useLocation()
  const segments = pathname.split('/').filter(Boolean)
  const CLUB_SECTIONS = ['dashboard', 'players', 'leaderboard', 'records', 'compare', 'statlab']
  if (segments.length >= 2 && CLUB_SECTIONS.includes(segments[1])) {
    return segments[0]
  }
  // Fall back to the last club the user visited (stored by useClub hook)
  return sessionStorage.getItem('bs_last_slug') || null
}

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false)
  const clubSlug = useClubSlug()

  const navLinks = clubSlug
    ? [
        { to: `/${clubSlug}/dashboard`,   label: 'Dashboard' },
        { to: `/${clubSlug}/players`,      label: 'Players' },
        { to: `/${clubSlug}/leaderboard`,  label: 'Leaderboard' },
        { to: `/${clubSlug}/records`,      label: 'Records' },
        { to: `/${clubSlug}/statlab`,      label: 'StatLab' },
      ]
    : []

  return (
    <nav className="sticky top-0 z-40 bg-navy-950/95 backdrop-blur border-b border-navy-800">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-14">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 group shrink-0">
            <svg className="h-7 w-7 shrink-0" viewBox="0 0 28 28" fill="none" aria-hidden="true">
              <circle cx="14" cy="14" r="13" stroke="#16c784" strokeWidth="2" fill="none"/>
              <path d="M3.5 14c0-5.799 4.701-10.5 10.5-10.5S24.5 8.201 24.5 14 19.799 24.5 14 24.5 3.5 19.799 3.5 14z" fill="#16c784" fillOpacity="0.08"/>
              <path d="M7 10.5c3.5 1.5 6.5 1.5 14 0M7 17.5c3.5-1.5 6.5-1.5 14 0" stroke="#16c784" strokeWidth="1.5" strokeLinecap="round"/>
              <path d="M14 3.5v21M8 5.5c2 4 2 13 0 17M20 5.5c-2 4-2 13 0 17" stroke="#16c784" strokeWidth="1" strokeLinecap="round" opacity="0.5"/>
            </svg>
            <span className="font-display font-bold text-xl tracking-wider uppercase text-white group-hover:text-accent transition-colors">
              Better<span className="text-accent">Stats</span>
            </span>
            <span className="text-slate-600 text-xs font-mono">v3.3.0</span>
          </Link>

          <div className="hidden md:flex items-center gap-1">
            {navLinks.map(l => (
              <Link
                key={l.to}
                to={l.to}
                className="px-3 py-1.5 rounded-md text-sm text-slate-400 hover:text-white hover:bg-navy-800 transition-colors"
              >
                {l.label}
              </Link>
            ))}
          </div>

          {/* Mobile menu button */}
          {navLinks.length > 0 && (
            <button
              className="md:hidden p-2 text-slate-400 hover:text-white"
              onClick={() => setMenuOpen(o => !o)}
              aria-label="Toggle menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {menuOpen
                  ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                }
              </svg>
            </button>
          )}
        </div>

        {/* Mobile dropdown */}
        {menuOpen && navLinks.length > 0 && (
          <div className="md:hidden border-t border-navy-800 py-2">
            {navLinks.map(l => (
              <Link
                key={l.to}
                to={l.to}
                onClick={() => setMenuOpen(false)}
                className="block px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-navy-800 rounded-md"
              >
                {l.label}
              </Link>
            ))}
          </div>
        )}
      </div>
    </nav>
  )
}

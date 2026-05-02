import { Link, useLocation } from 'react-router-dom'
import { useState } from 'react'

export default function Navbar() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)

  return (
    <nav className="bg-navy-900 border-b border-navy-700 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 group">
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
        </Link>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-1">
          <Link to="/onboard" className="btn-ghost">Join a Club</Link>
          <a
            href="https://playcricket.com.au"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost text-xs"
          >
            PlayHQ ↗
          </a>
        </div>

        {/* Mobile hamburger */}
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

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden border-t border-navy-700 bg-navy-900 px-4 py-3 flex flex-col gap-2">
          <Link to="/onboard" className="btn-ghost text-left" onClick={() => setOpen(false)}>Join a Club</Link>
        </div>
      )}
    </nav>
  )
}

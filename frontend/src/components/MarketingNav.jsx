import { Link, useLocation } from 'react-router-dom'
import { useState } from 'react'

const LINKS = [
  { to: '/features', label: 'Features' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
]

export default function MarketingNav() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)

  return (
    <nav className="bg-navy-950 border-b border-navy-800 sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 flex items-center justify-between h-16">
        <Link to="/" className="flex items-center gap-2 group">
          <span className="w-7 h-7 rounded bg-accent flex items-center justify-center">
            <svg viewBox="0 0 24 24" className="w-4 h-4 fill-navy-950">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="4" x2="12" y2="20" stroke="#070b14" strokeWidth="2" />
              <line x1="4" y1="12" x2="20" y2="12" stroke="#070b14" strokeWidth="2" />
            </svg>
          </span>
          <span className="font-display font-bold text-xl tracking-wider uppercase text-white group-hover:text-accent transition-colors">
            Better<span className="text-accent">Stats</span>
          </span>
        </Link>

        {/* Desktop */}
        <div className="hidden md:flex items-center gap-1">
          {LINKS.map(link => (
            <Link
              key={link.to}
              to={link.to}
              className={`px-3 py-2 rounded text-sm transition-colors ${
                pathname === link.to ? 'text-accent' : 'text-slate-300 hover:text-white'
              }`}
            >
              {link.label}
            </Link>
          ))}
          <Link to="/login" className="ml-2 btn-primary text-sm">
            Admin Login
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden text-slate-400 hover:text-white p-2"
          onClick={() => setOpen(o => !o)}
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
        <div className="md:hidden border-t border-navy-800 bg-navy-950 px-4 py-3 flex flex-col gap-1">
          {LINKS.map(link => (
            <Link key={link.to} to={link.to} className="text-slate-300 hover:text-white py-2 text-sm" onClick={() => setOpen(false)}>
              {link.label}
            </Link>
          ))}
          <Link to="/login" className="btn-primary text-sm mt-2 text-center" onClick={() => setOpen(false)}>
            Admin Login
          </Link>
        </div>
      )}
    </nav>
  )
}

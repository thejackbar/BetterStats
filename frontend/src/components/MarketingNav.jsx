import { Link, useLocation } from 'react-router-dom'
import { useState } from 'react'
import betterStatsLogo from '../assets/betterstatslogo_white.png'

const LINKS = [
  { to: '/features', label: 'Features' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/blog', label: 'Blog' },
  { to: '/faq', label: 'FAQ' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
]

export default function MarketingNav() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)

  return (
    <nav className="bg-pb-surface border-b pb-hairline-b sticky top-0 z-50">
      <div className="max-w-5xl mx-auto px-4 flex items-center justify-between h-16">
        <Link to="/" className="flex items-center gap-2.5 group">
          <img
            src={betterStatsLogo}
            alt="BetterStats"
            className="w-7 h-7 object-contain"
          />
          <span className="font-display font-bold text-base tracking-wider uppercase text-pb-text group-hover:text-pb-accent transition-colors">
            BetterStats
          </span>
        </Link>

        {/* Desktop */}
        <div className="hidden md:flex items-center gap-1">
          {LINKS.map(link => (
            <Link
              key={link.to}
              to={link.to}
              className={`px-3 py-2 rounded font-mono text-[11px] tracking-wide2 transition-colors ${
                pathname === link.to
                  ? 'text-pb-text'
                  : 'text-pb-faint hover:text-pb-text'
              }`}
            >
              {link.label.toUpperCase()}
            </Link>
          ))}
          <Link
            to="/login"
            className="ml-3 px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            ADMIN LOGIN
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden text-pb-faint hover:text-pb-text p-2"
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
        <div className="md:hidden border-t pb-hairline-t bg-pb-surface px-4 py-3 flex flex-col gap-1">
          {LINKS.map(link => (
            <Link
              key={link.to}
              to={link.to}
              className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text py-2 transition-colors"
              onClick={() => setOpen(false)}
            >
              {link.label.toUpperCase()}
            </Link>
          ))}
          <Link
            to="/login"
            className="mt-2 py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold text-center transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
            onClick={() => setOpen(false)}
          >
            ADMIN LOGIN
          </Link>
        </div>
      )}
    </nav>
  )
}

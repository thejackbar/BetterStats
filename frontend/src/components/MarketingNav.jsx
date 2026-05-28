import { Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import betterStatsLogo from '../assets/betterstatslogo_white.png'
import { FORM_URL } from '../data/marketing'

const LINKS = [
  { to: '/features', label: 'Features' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/compare', label: 'Compare' },
  { to: '/about', label: 'About' },
  { to: '/blog', label: 'Blog' },
  { to: '/faq', label: 'FAQ' },
  { to: '/contact', label: 'Contact' },
]

export default function MarketingNav() {
  const { pathname, hash } = useLocation()
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const isHome = pathname === '/'

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Home page gets a transparent nav until scrolled; other pages get a solid one.
  const navBg =
    isHome && !scrolled
      ? 'bg-transparent'
      : 'bg-pb-bg/85 backdrop-blur-md border-b pb-hairline'

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${navBg}`}>
      {/* Skip to main content — visible on focus for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[200] focus:px-4 focus:py-2 focus:rounded focus:bg-pb-surface focus:text-pb-text focus:font-mono focus:text-xs focus:border focus:pb-hairline focus:outline-none"
      >
        Skip to main content
      </a>

      <div className="max-w-[1280px] mx-auto px-4 sm:px-6 lg:px-10 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 group" aria-label="BetterStats home">
          <img src={betterStatsLogo} alt="BetterStats" className="w-7 h-7 object-contain" />
          <span className="font-bold text-base tracking-tight text-pb-text group-hover:text-accent transition-colors">
            Better<span className="text-accent">Stats</span>
          </span>
        </Link>

        {/* Desktop */}
        <div className="hidden md:flex items-center gap-1">
          {LINKS.map((link) => {
            const active = link.to === pathname || link.to === `${pathname}${hash}`
            return (
              <Link
                key={link.to}
                to={link.to}
                className={`px-3 py-2 rounded text-sm font-medium transition-colors whitespace-nowrap ${
                  active ? 'text-pb-text' : 'text-pb-dim hover:text-pb-text'
                }`}
              >
                {link.label}
              </Link>
            )
          })}
          <a
            href={FORM_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-3 cta-primary !text-[13px] !py-2.5 !px-4 whitespace-nowrap"
            aria-label="Request access for your club (opens in new tab)"
          >
            Request access
          </a>
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          className="md:hidden text-pb-dim hover:text-pb-text p-2"
          onClick={() => setOpen((o) => !o)}
          aria-label={open ? 'Close navigation' : 'Open navigation'}
          aria-expanded={open}
          aria-controls="mobile-nav"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            {open ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {open && (
        <div id="mobile-nav" className="md:hidden border-t pb-hairline bg-pb-surface px-4 py-3 flex flex-col gap-1">
          {LINKS.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="text-sm font-medium text-pb-dim hover:text-pb-text py-2 transition-colors"
              onClick={() => setOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          <a
            href={FORM_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 cta-primary !py-3 justify-center"
            onClick={() => setOpen(false)}
          >
            Request access
          </a>
        </div>
      )}
    </nav>
  )
}
